"""Presentation: the post as a viewer first sees it on the platform.

There is no public API that renders "this post on Instagram, on a phone".
But the rules that decide what a scrolling viewer sees are stable enough to
keep as data: where the caption is cut by "...more", how the feed and the
profile grid crop an image, and which edges of a full-screen video the app
covers with its own buttons and caption. They change a few times a year, so
they live here, dated, to be refreshed (the scout agent can watch for spec
changes). Mobile values are used where they differ, because they are the
stricter case and most viewing happens there.

From them Prism checks three things a reviewer looking only at the raw
upload would miss, and builds the "at a glance" view (cropped image plus the
caption before the cut) that the cross-modal context layer reads, so image
and caption are judged as one post.
"""

from __future__ import annotations

import re
from typing import Any

from verytas.checks.base import RawFinding
from verytas.prism.agents import AgentNode, ReviewRun

# As of October 2026, from platform help pages and the design guides that track
# them. fold: characters shown before "...more" on mobile. feed: the range of
# width/height the feed shows uncropped. grid: the profile-grid crop.
# vertical_ui: share of a full-screen frame covered by the app (top, bottom, right).
LAYOUTS: dict[str, dict[str, Any]] = {
    "instagram": {"fold": 125, "feed": (0.8, 1.91), "grid": 0.75, "vertical_ui": (0.14, 0.22, 0.12)},
    "tiktok": {"fold": 80, "feed": None, "grid": 0.75, "vertical_ui": (0.12, 0.25, 0.15)},
    "youtube_shorts": {"fold": 100, "feed": None, "grid": None, "vertical_ui": (0.10, 0.25, 0.15)},
    "facebook": {"fold": 125, "feed": (0.8, 1.91), "grid": None, "vertical_ui": (0.12, 0.22, 0.12)},
    "linkedin": {"fold": 110, "feed": (0.8, 1.91), "grid": None, "vertical_ui": None},
    "x": {"fold": None, "feed": (0.75, 2.0), "grid": None, "vertical_ui": None},
    "threads": {"fold": None, "feed": (0.75, 1.91), "grid": None, "vertical_ui": None},
    "youtube": {"fold": 100, "feed": None, "grid": None, "vertical_ui": None},
}
_DEFAULT = {"fold": 125, "feed": None, "grid": None, "vertical_ui": None}
_VERTICAL_CHANNELS = {"instagram", "tiktok", "youtube_shorts", "facebook"}
DISCLOSURE = re.compile(
    r"(?<!\w)#(?:ad|ads|sponsored|paidpartnership|partner|collab|gifted|madewithai|aigenerated|aiart)\b"
    r"|\bpaid partnership\b|\bsponsored\b|(?<!\w)ad:|\bai[- ]generated\b|\bmade (?:with|using) ai\b",
    re.IGNORECASE)


def layout_for(channel: str) -> dict[str, Any]:
    return {**_DEFAULT, **LAYOUTS.get(_key(channel), {})}


def visible_box(w: int, h: int, ratio_range: tuple[float, float] | None) -> tuple[float, float, float, float]:
    """The centred region a feed shows when it clamps width/height into `ratio_range`."""
    if not ratio_range:
        return 0, 0, w, h
    lo, hi = ratio_range
    r = w / max(1, h)
    if r < lo:  # taller than the feed allows: top and bottom are cut
        vh = w / lo
        return 0, (h - vh) / 2, w, (h + vh) / 2
    if r > hi:  # wider than allowed: the sides are cut
        vw = h * hi
        return (w - vw) / 2, 0, (w + vw) / 2, h
    return 0, 0, w, h


def _inside(box, region, slack: float = 2.0) -> bool:
    return (box[0] >= region[0] - slack and box[1] >= region[1] - slack and box[2] <= region[2] + slack
            and box[3] <= region[3] + slack)


def _key(channel: str) -> str:
    return channel.strip().lower().replace(" ", "_")


async def presentation_agent(run: ReviewRun, node: AgentNode) -> None:
    channel = run.base.channel
    layout = layout_for(channel)
    out: list[RawFinding] = []
    body = run.base.body
    fold = layout["fold"]

    def finding(code: str, title: str, why: str, *, start=None, end=None, source="body", locator=None,
                quote=None, unit="presentation") -> None:
        rule = run.rule_by_code.get(code)
        if rule is None:
            return
        out.append(RawFinding(
            unit_id=unit, category=rule.category, title=title, explanation=f"{why} {rule.text}", confidence=0.9,
            checker="presentation", rule_code=rule.code, quote=quote if quote is not None else (
                body[start:end] if start is not None else None),
            span_start=start, span_end=end, source=source, locator=locator,
        ))

    # 1. Disclosures that only appear after the caption is cut.
    if fold and len(body) > fold:
        hits = list(DISCLOSURE.finditer(body))
        if hits and all(m.start() >= fold for m in hits):
            m = hits[0]
            finding("PRES-FOLD", f"“{m.group(0)}” is hidden behind “…more” on {channel}",
                    f"{channel.title()} shows about the first {fold} characters before cutting the caption on a "
                    f"phone; this label starts at character {m.start() + 1}.", start=m.start(), end=m.end())

    glance = [f"On {channel}, a viewer scrolling on a phone first sees"
              + (f" this caption before “…more”: “{body[:fold].strip()}”" if fold and len(body) > fold
                 else f" the whole caption: “{body.strip()[:400]}”")]

    # 2. Text and logos cut by the feed or grid crop. 3. Text under the app's buttons.
    for media_id, info in run.layouts.items():
        w, h = info["size"]
        is_video = info.get("video", False)
        loc = {"video" if is_video else "image": media_id}
        regions = []
        if layout["feed"] and not is_video:
            regions.append(("feed", visible_box(w, h, layout["feed"])))
        if layout["grid"]:
            regions.append(("profile grid", visible_box(w, h, (layout["grid"], layout["grid"]))))
        for where, region in regions:
            cut_text = [t for t, box in info.get("lines", []) if len(t) >= 3 and not _inside(box, region)]
            cut_assets = [n for n, box in info.get("assets", []) if box and not _inside(box, region)]
            if cut_text or cut_assets:
                what = "; ".join([*(f"text “{t[:50]}”" for t in cut_text[:3]),
                                  *(f"the {n}" for n in cut_assets[:2])])
                finding("PRES-CROP", f"Cut off in the {channel} {where}: {what}",
                        f"The {where} shows only the centre {region[2] - region[0]:.0f}x{region[3] - region[1]:.0f} "
                        f"of this {w}x{h} {'video' if is_video else 'image'}.", source=media_id,
                        locator={**loc, "box": [round(v) for v in region], "view": where},
                        quote=", ".join(cut_text[:3]) or None, unit=media_id)
                break  # the tighter crop is reported once
        if layout["vertical_ui"] and _key(channel) in _VERTICAL_CHANNELS and h / max(1, w) >= 1.6:
            top, bottom, right = layout["vertical_ui"]
            covered = [t for t, (x0, y0, x1, y1) in info.get("lines", []) if len(t) >= 3 and (
                y0 < h * top or y1 > h * (1 - bottom) or x1 > w * (1 - right))]
            if covered:
                finding("PRES-SAFEZONE", f"Text under the {channel} buttons: “{covered[0][:60]}”",
                        f"Full-screen {channel} covers roughly the top {top:.0%}, bottom {bottom:.0%} and right "
                        f"{right:.0%} of the frame with its own controls and caption.", source=media_id,
                        locator=loc, quote=", ".join(covered[:3]), unit=media_id)
        shown = [t for t, box in info.get("lines", []) if not regions or _inside(box, regions[0][1])]
        glance.append(f"{'The video' if is_video else 'The image'} {media_id}"
                      + (f" shows the text “{' / '.join(shown[:6])}”" if shown else " shows no readable text")
                      + (f" in the {regions[0][0]} crop" if regions else ""))

    run.glance = glance
    run.caption_folded = bool(fold) and len(body) > fold
    node.detail = {"channel": channel, "fold": fold, "media": len(run.layouts), "findings": len(out)}
    run.add(node, "presentation", out)
