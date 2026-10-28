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
import statistics
from datetime import date
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from verytas.api.content import _content
from verytas.api.deps import CurrentUser, Session, require
from verytas.models import (
    Content,
    ContentStatus,
    ContentVersion,
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


def canonical(url: str) -> str:
    """The link as it identifies the post: https, lower-case host, no fragment and no tracking parameters,
    so the same post pasted twice (or once from a share sheet) is one address."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("a live post's link starts with https:// and names the site")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not (k.lower().startswith("utm_") or k.lower() in TRACKING)])
    host = parts.hostname.lower()
    netloc = host if parts.port in (None, 443) else f"{host}:{parts.port}"
    return urlunsplit(("https", netloc, parts.path.rstrip("/") or "/", query, ""))


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


def engagement(metrics: dict[str, int]) -> float | None:
    """Interactions per person reached (or per view when reach isn't known): the one number comparable
    across posts of different sizes. None when there is nothing to divide by."""
    base = metrics.get("reach") or metrics.get("views")
    if not base:
        return None
    acts = sum(metrics.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
    return round(acts / base, 4)


def _out(r: PostResult) -> ResultOut:
    return ResultOut(content_id=r.content_id, url=r.url, platform=r.platform, posted_on=r.posted_on,
                     metrics=r.metrics or {}, source=r.source, recorded_by=r.recorded_by,
                     engagement_rate=engagement(r.metrics or {}))


async def _may_record(session, user: User, content_id: int) -> Content:
    content = await _content(session, user, content_id)
    if user.role not in (Role.creator, Role.reviewer, Role.approver, Role.brand_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your role reads results but doesn't record them")
    if content.status not in LIVE_STATUSES:
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
    await session.flush()
    await append(session, workspace_id=content.workspace_id, actor=f"user:{user.id}", action="result.recorded",
                 object_type="content", object_id=content_id,
                 detail={"platform": row.platform, "metrics": sorted(metrics)})
    await session.commit()
    return _out(row)


@router.delete("/contents/{content_id}/result", status_code=status.HTTP_204_NO_CONTENT)
async def remove_result(content_id: int, session: Session, user: CurrentUser) -> Response:
    await _may_record(session, user, content_id)
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
    skipped: list[dict]


@router.post("/results/import", response_model=ImportOut)
async def import_results(body: ImportIn, session: Session, user: Brand) -> ImportOut:
    """A sheet of numbers, one post a row, matched by link to results already recorded: the export most
    platforms' insights pages give, trimmed to a url column and any of the metric columns."""
    reader = csv.DictReader(io.StringIO(body.csv))
    header = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if "url" not in header:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the sheet needs a url column")
    if not header & set(METRICS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"the sheet needs at least one of: {', '.join(METRICS)}")
    known = {r.url: r for r in (await session.scalars(select(PostResult).where(
        PostResult.workspace_id == user.workspace_id))).all()}
    updated, skipped = 0, []
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT_ROWS:
            skipped.append({"row": n, "reason": f"only the first {MAX_IMPORT_ROWS} rows are read"})
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
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
            numbers = {k: int(float(row[k].replace(",", ""))) for k in METRICS if row.get(k)}
        except ValueError:
            skipped.append({"row": n, "reason": "a number column has something that isn't a number"})
            continue
        if any(v < 0 or v > 10**12 for v in numbers.values()):
            skipped.append({"row": n, "reason": "a number is out of range"})
            continue
        result.metrics = {**(result.metrics or {}), **numbers}
        result.source, result.recorded_by = "csv", user.id
        updated += 1
    if updated:
        await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="result.imported",
                     object_type="workspace", object_id=user.workspace_id, detail={"rows": updated})
    await session.commit()
    return ImportOut(updated=updated, skipped=skipped[:50])


def _interval(a: list[float], b: list[float], seed: int) -> tuple[float, float]:
    """A 90% bootstrap interval for the difference in medians (a minus b), seeded so a page reload shows
    the same numbers."""
    rnd = random.Random(seed)
    diffs = sorted(statistics.median(rnd.choices(a, k=len(a))) - statistics.median(rnd.choices(b, k=len(b)))
                   for _ in range(1000))
    return round(diffs[50], 4), round(diffs[949], 4)


@router.get("/insights/performance")
async def performance(session: Session, user: Analyst) -> dict:
    """Per rule: how posts that needed its fix did against those that didn't, by engagement rate."""
    tiers = [t for t in Tier if t.rank <= user.clearance.rank]
    pieces = (await session.scalars(select(Content).where(
        Content.workspace_id == user.workspace_id, Content.tier.in_(tiers),
        Content.status.in_(LIVE_STATUSES)))).all()
    ids = [c.id for c in pieces]
    results = {r.content_id: r for r in (await session.scalars(
        select(PostResult).where(PostResult.content_id.in_(ids)))).all()} if ids else {}
    rates = {cid: e for cid, r in results.items() if (e := engagement(r.metrics or {})) is not None}
    # Which rules each live piece ran into, over every version's review: a fix made before posting counts.
    hit: dict[int, set[int]] = {}
    if rates:
        rows = (await session.execute(
            select(ContentVersion.content_id, Finding.rule_id)
            .join(Review, Review.version_id == ContentVersion.id).join(Finding, Finding.review_id == Review.id)
            .where(ContentVersion.content_id.in_(list(rates)), Finding.rule_id.is_not(None)))).all()
        for cid, rid in rows:
            hit.setdefault(rid, set()).add(cid)
    rules = {r.id: r for r in (await session.scalars(select(Rule).where(
        Rule.workspace_id == user.workspace_id, Rule.tier.in_(tiers)))).all()}
    out = []
    for rid, needed in hit.items():
        rule = rules.get(rid)
        if rule is None:
            continue
        a = [rates[c] for c in needed]
        b = [v for c, v in rates.items() if c not in needed]
        row = {"rule_id": rid, "code": rule.code, "title": rule.title, "needed": len(a), "clean": len(b)}
        if len(a) >= MIN_POSTS and len(b) >= MIN_POSTS:
            lo, hi = _interval(a, b, seed=rid)
            row |= {"median_needed": round(statistics.median(a), 4), "median_clean": round(statistics.median(b), 4),
                    "difference_90": [lo, hi]}
        out.append(row)
    out.sort(key=lambda r: (-(r["needed"] >= MIN_POSTS and r["clean"] >= MIN_POSTS), -r["needed"]))
    return {"live_pieces": len(pieces), "with_link": len(results), "with_numbers": len(rates),
            "min_posts": MIN_POSTS, "rules": out}
