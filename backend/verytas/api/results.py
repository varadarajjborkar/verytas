"""How pieces did once they went live: the post's link and its numbers, recorded by people.

The first step of performance feedback, with no platform integration: after a piece is approved and posted,
the creator (or the brand team) pastes the live link and, if they have them, the numbers the platform shows.
The brand team can also import a sheet of numbers by link. Nothing is fetched from the platform and nothing
of the post is stored but its address and its counts.

Insights compare the posts that needed a rule's fix with those that didn't, and say nothing until each side
has enough posts behind it. They are advice for the brand team; no rule changes because of them.
"""

from __future__ import annotations

import csv
import io
import random
import re
import statistics
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from verytas.api.content import _content
from verytas.api.deps import CurrentUser, Session, require
from verytas.models import (
    Content,
    ContentStatus,
    ContentVersion,
    Decision,
    DecisionAction,
    Finding,
    PostResult,
    Review,
    Role,
    Rule,
    Tier,
    User,
)
from verytas.security.audit import append

router = APIRouter(tags=["results"])
Brand = Annotated[User, Depends(require(Role.reviewer, Role.approver))]
Analyst = Annotated[User, Depends(require(Role.reviewer, Role.approver, Role.auditor))]

METRICS = ("views", "reach", "likes", "comments", "shares", "saves", "watch_seconds")
# Hosts by suffix, so m.youtube.com and www.instagram.com land on the same platform.
PLATFORMS = {
    "instagram.com": "instagram", "youtube.com": "youtube", "youtu.be": "youtube", "x.com": "x",
    "twitter.com": "x", "linkedin.com": "linkedin", "facebook.com": "facebook", "fb.watch": "facebook",
    "tiktok.com": "tiktok", "threads.net": "threads", "pinterest.com": "pinterest",
}
# Only a piece that has been cleared can have gone live.
LIVE_STATUSES = (ContentStatus.approved, ContentStatus.published)
# A comparison says nothing until each side has this many posts; below it, a pattern is noise.
MIN_POSTS = 5
MAX_IMPORT_ROWS = 2000
# Share-sheet parameters that say who shared, not which post; YouTube's v= and the like are kept.
TRACKING = {"si", "igsh", "igshid", "fbclid", "gclid", "ref", "ref_src", "s", "t", "feature", "mibextid"}
# An ASCII host name: an internationalised one arrives here as punycode or not at all, so a look-alike
# spelled in another script can't pass for a platform's address.
HOST = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
URL_MAX = 500  # the column's width
# Reasons that clear a finding as not a breach; a post whose only brush with a rule was one of these didn't
# run into it.
CLEARED = ("false_positive", "not_applicable")


def canonical(url: str) -> str:
    """The link as it identifies the post: https, lower-case host, no fragment and no tracking parameters,
    so the same post pasted twice (or once from a share sheet) is one address. A platform's www. and
    mobile hosts are the platform, and a YouTube short link or Short is its watch page."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("a live post's link starts with https:// and names the site")
    host = parts.hostname.lower().rstrip(".")
    if not HOST.fullmatch(host):
        raise ValueError("that link's site name isn't a plain web address")
    bare = re.sub(r"^(www|m|mobile)\.", "", host)
    if bare in PLATFORMS:
        host = bare
    path = parts.path.rstrip("/") or "/"
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not (k.lower().startswith("utm_") or k.lower() in TRACKING)]
    short = host == "youtube.com" and path.startswith("/shorts/")
    video = path[1:] if host == "youtu.be" else path[len("/shorts/"):] if short else ""
    if video and "/" not in video:
        host, path = "youtube.com", "/watch"
        pairs = [("v", video), *(p for p in pairs if p[0] != "v")]
    netloc = host if parts.port in (None, 443) else f"{host}:{parts.port}"
    out = urlunsplit(("https", netloc, path, urlencode(sorted(pairs)), ""))
    if len(out) > URL_MAX:
        raise ValueError("that link is too long to be a post's address")
    return out


def platform_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return next((p for suffix, p in PLATFORMS.items() if host == suffix or host.endswith("." + suffix)), "other")


Count = Annotated[int, Field(ge=0, le=10**12)]


class Metrics(BaseModel):
    views: Count | None = None
    reach: Count | None = None
    likes: Count | None = None
    comments: Count | None = None
    shares: Count | None = None
    saves: Count | None = None
    watch_seconds: Count | None = None


class ResultIn(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    posted_on: date | None = None
    metrics: Metrics = Field(default_factory=Metrics)

    @field_validator("url")
    @classmethod
    def _link(cls, v: str) -> str:
        return canonical(v)


class ResultOut(BaseModel):
    content_id: int
    url: str
    platform: str
    posted_on: date | None
    metrics: dict[str, int]
    source: Literal["manual", "csv"]
    recorded_by: int
    engagement_rate: float | None


def engagement(metrics: dict[str, int], basis: str | None = None) -> float | None:
    """Interactions per person reached (or per view when reach isn't known): the one number comparable
    across posts of different sizes. None when there is nothing to divide by. With a basis, only that
    denominator is used, so a comparison never sets per-reach rates against per-view ones."""
    base = metrics.get(basis) if basis else metrics.get("reach") or metrics.get("views")
    if not base:
        return None
    acts = sum(metrics.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
    return round(acts / base, 4)


def _out(r: PostResult) -> ResultOut:
    return ResultOut(content_id=r.content_id, url=r.url, platform=r.platform, posted_on=r.posted_on,
                     metrics=r.metrics or {}, source=r.source, recorded_by=r.recorded_by,
                     engagement_rate=engagement(r.metrics or {}))


async def _may_record(session, user: User, content_id: int, *, live: bool = True) -> Content:
    content = await _content(session, user, content_id)
    if user.role not in (Role.creator, Role.reviewer, Role.approver, Role.brand_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your role reads results but doesn't record them")
    if live and content.status not in LIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "only an approved piece can have gone live")
    return content


@router.get("/contents/{content_id}/result", response_model=ResultOut | None)
async def get_result(content_id: int, session: Session, user: CurrentUser) -> ResultOut | None:
    await _content(session, user, content_id)
    row = await session.scalar(select(PostResult).where(PostResult.content_id == content_id))
    return _out(row) if row else None


@router.put("/contents/{content_id}/result", response_model=ResultOut)
async def record_result(content_id: int, body: ResultIn, session: Session, user: CurrentUser) -> ResultOut:
    content = await _may_record(session, user, content_id)
    # One post, one piece: the same link recorded against two pieces would count it twice.
    other = await session.scalar(select(PostResult.content_id).where(
        PostResult.workspace_id == content.workspace_id, PostResult.url == body.url,
        PostResult.content_id != content_id))
    if other is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that link is already recorded for another piece")
    metrics = body.metrics.model_dump(exclude_none=True)
    row = await session.scalar(select(PostResult).where(PostResult.content_id == content_id))
    if row is None:
        row = PostResult(content_id=content_id, workspace_id=content.workspace_id, url=body.url,
                         platform=platform_of(body.url), posted_on=body.posted_on, metrics=metrics,
                         source="manual", recorded_by=user.id)
        session.add(row)
    else:
        row.url, row.platform, row.posted_on = body.url, platform_of(body.url), body.posted_on
        row.metrics, row.source, row.recorded_by = metrics, "manual", user.id
    try:
        await session.flush()
    except IntegrityError:
        # Two first saves for one piece at once: the other one won.
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "this piece's link was saved at the same moment; reload") from None
    await append(session, workspace_id=content.workspace_id, actor=f"user:{user.id}", action="result.recorded",
                 object_type="content", object_id=content_id,
                 detail={"platform": row.platform, "metrics": sorted(metrics)})
    await session.commit()
    return _out(row)


@router.delete("/contents/{content_id}/result", status_code=status.HTTP_204_NO_CONTENT)
async def remove_result(content_id: int, session: Session, user: CurrentUser) -> Response:
    # Not gated on the status: a mistaken link must stay removable after the piece goes back to review.
    await _may_record(session, user, content_id, live=False)
    row = await session.scalar(select(PostResult).where(PostResult.content_id == content_id))
    if row is not None:
        await session.delete(row)
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="result.removed",
                     object_type="content", object_id=content_id, detail={})
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=500_000)


class ImportOut(BaseModel):
    updated: int
    skipped: list[dict]  # the first 50
    skipped_total: int


def _count(raw: str, european: bool = False) -> int:
    """A count as a sheet writes it: "2,400", "2400" or "2400.0", or "2.400" and "2400,0" in a semicolon
    sheet, where the comma is the decimal mark. Anything else, including 1e999, inf and negatives, is not
    a count."""
    thousands, decimal = (".", ",") if european else (",", ".")
    text = raw.replace(thousands, "").replace(" ", "").replace("\u00a0", "").replace(decimal, ".")
    if not re.fullmatch(r"\d{1,13}(\.\d*)?", text):
        raise ValueError(raw)
    try:
        return int(Decimal(text))
    except InvalidOperation:
        raise ValueError(raw) from None


@router.post("/results/import", response_model=ImportOut)
async def import_results(body: ImportIn, session: Session, user: Brand) -> ImportOut:
    """A sheet of numbers, one post a row, matched by link to results already recorded: the export most
    platforms' insights pages give, trimmed to a url column and any of the metric columns."""
    text = body.csv.lstrip("\ufeff")  # Excel's byte-order mark would otherwise stick to the first header
    first = text.split("\n", 1)[0]
    # Excel in much of Europe writes semicolons; a tab-separated paste is the other common shape.
    delimiter = max((",", ";", "\t"), key=first.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if "url" not in header:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the sheet needs a url column")
    if not header & set(METRICS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"the sheet needs at least one of: {', '.join(METRICS)}")
    # Only results on pieces this reviewer may see, and that are still live: a sheet must not write to a
    # restricted piece, nor say by "updated" that a restricted piece has a given link.
    tiers = [t for t in Tier if t.rank <= user.clearance.rank]
    known = {r.url: r for r in (await session.scalars(
        select(PostResult).join(Content, Content.id == PostResult.content_id).where(
            PostResult.workspace_id == user.workspace_id, Content.tier.in_(tiers),
            Content.status.in_(LIVE_STATUSES)))).all()}
    updated, skipped = 0, []
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT_ROWS:
            skipped.append({"row": n, "reason": f"only the first {MAX_IMPORT_ROWS} rows are read"})
            break
        # A row longer than the header puts its extra cells under None, as a list; they belong to no column.
        row = {k.strip().lower(): (v if isinstance(v, str) else "").strip() for k, v in raw.items() if k is not None}
        try:
            url = canonical(row.get("url", ""))
        except ValueError as exc:
            skipped.append({"row": n, "reason": str(exc)})
            continue
        result = known.get(url)
        if result is None:
            skipped.append({"row": n, "reason": "no piece has this link yet; record it on the piece first"})
            continue
        try:
            numbers = {k: _count(row[k], european=delimiter == ";") for k in METRICS if row.get(k)}
        except ValueError:
            skipped.append({"row": n, "reason": "a number column has something that isn't a whole, positive number"})
            continue
        if any(v > 10**12 for v in numbers.values()):
            skipped.append({"row": n, "reason": "a number is out of range"})
            continue
        result.metrics = {**(result.metrics or {}), **numbers}
        result.source, result.recorded_by = "csv", user.id
        updated += 1
    if updated:
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="result.imported",
                     object_type="workspace", object_id=user.workspace_id, detail={"rows": updated})
    await session.commit()
    return ImportOut(updated=updated, skipped=skipped[:50], skipped_total=len(skipped))


def _interval(a: list[float], b: list[float], seed: int) -> tuple[float, float]:
    """A 90% bootstrap interval for the difference in medians (a minus b), seeded so a page reload shows
    the same numbers."""
    # Sorted first: the draws then depend on the numbers alone, not on the order a query returned them in.
    a, b = sorted(a), sorted(b)
    rnd = random.Random(seed)
    diffs = sorted(statistics.median(rnd.choices(a, k=len(a))) - statistics.median(rnd.choices(b, k=len(b)))
                   for _ in range(1000))
    return round(diffs[50], 4), round(diffs[949], 4)


@router.get("/insights/performance")
async def performance(session: Session, user: Analyst) -> dict:
    """Per rule: how posts that ran into it did against posts that didn't, by engagement rate.

    Three things keep the comparison honest without a model of the audience. Every rate uses the same
    denominator (reach where most posts have it, else views). A finding cleared as not a breach doesn't
    count as running into the rule. And the posts that didn't are drawn only from the platforms the posts
    that did went out on, so a rule hit mostly on one platform isn't measured against another's numbers.
    """
    tiers = [t for t in Tier if t.rank <= user.clearance.rank]
    pieces = (await session.scalars(select(Content).where(
        Content.workspace_id == user.workspace_id, Content.tier.in_(tiers),
        Content.status.in_(LIVE_STATUSES)))).all()
    ids = [c.id for c in pieces]
    results = {r.content_id: r for r in (await session.scalars(
        select(PostResult).where(PostResult.content_id.in_(ids)))).all()} if ids else {}
    with_reach = sum(1 for r in results.values() if (r.metrics or {}).get("reach"))
    with_views = sum(1 for r in results.values() if (r.metrics or {}).get("views"))
    basis = "reach" if with_reach >= with_views else "views"
    rates = {cid: e for cid, r in results.items() if (e := engagement(r.metrics or {}, basis)) is not None}
    platform = {cid: results[cid].platform for cid in rates}
    # Which rules each live piece ran into, over every version's review: a fix made before posting counts,
    # since the question is whether what the rule catches costs engagement.
    hit: dict[int, set[int]] = {}
    if rates:
        cleared = select(Decision.finding_id).where(
            Decision.action == DecisionAction.rejected, Decision.reason_code.in_(CLEARED))
        rows = (await session.execute(
            select(ContentVersion.content_id, Finding.rule_id)
            .join(Review, Review.version_id == ContentVersion.id).join(Finding, Finding.review_id == Review.id)
            .where(ContentVersion.content_id.in_(list(rates)), Finding.rule_id.is_not(None),
                   Finding.id.not_in(cleared)))).all()
        for cid, rid in rows:
            hit.setdefault(rid, set()).add(cid)
    rules = {r.id: r for r in (await session.scalars(select(Rule).where(
        Rule.workspace_id == user.workspace_id, Rule.tier.in_(tiers)))).all()}
    out = []
    for rid, needed in hit.items():
        rule = rules.get(rid)
        if rule is None:
            continue
        where = {platform[c] for c in needed}
        a = [rates[c] for c in needed]
        b = [v for c, v in rates.items() if c not in needed and platform[c] in where]
        row = {"rule_id": rid, "code": rule.code, "title": rule.title, "needed": len(a), "clean": len(b),
               "platforms": sorted(where)}
        if len(a) >= MIN_POSTS and len(b) >= MIN_POSTS:
            lo, hi = _interval(a, b, seed=rid)
            row |= {"median_needed": round(statistics.median(a), 4), "median_clean": round(statistics.median(b), 4),
                    "difference_90": [lo, hi]}
        out.append(row)
    out.sort(key=lambda r: (-(r["needed"] >= MIN_POSTS and r["clean"] >= MIN_POSTS), -r["needed"]))
    return {"live_pieces": len(pieces), "with_link": len(results), "with_numbers": len(rates),
            "basis": basis, "min_posts": MIN_POSTS, "rules": out}
