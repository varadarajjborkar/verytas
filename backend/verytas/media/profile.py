"""Intake profiling: is this submission shaped like social content at all?

Social posts are short. A 300-page PDF behind a two-line caption, a 60 MP
image, a 25-minute "reel" or a caption laced with invisible characters are
irregular. They are rarely innocent, and they are expensive to scan, which
makes them a cheap way to tie the pipeline up. Each irregularity is reported
at upload time with what was expected. The creator may still go ahead with a
written reason (the marketing team asked for it), and then the content is
scanned in full, up to the hard caps, and the irregularity is scored as a
finding of its own.

Two thresholds per measure:

  typical  beyond what the channel normally carries -> irregular, reason required
  limit    beyond what the platform accepts at all  -> irregular, and the post
           cannot be published as is

Channel figures as of October 2026, from platform help pages and the vendor
guides that track them (they disagree in places and change often, so they
live here as data, not code):
  https://www.socialync.io/blog/social-media-platform-limits-guide-2026
  https://publer.com/help/en/article/what-post-types-are-supported-and-what-are-their-limitations-1687rte/
  https://www.trymypost.com/blog/linkedin-pdf-carousel-specs  (LinkedIn documents: 100 MB, 300 pages)
  https://www.inro.social/blog/instagram-reels-can-now-be-20-minutes-long-new-time-limit-explained-2025
Hard caps below are Verytas's own, set by what a review can process safely.
"""

from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from PIL import Image

from verytas.checks.emoji import is_emoji
from verytas.config import Settings
from verytas.media.documents import MAX_PAGES
from verytas.security.terms import _invisible

# Processing caps (not channel rules): beyond these the rest is not scanned and
# the review says so. Taken from the extractors so the promise made at intake
# is the one the review keeps. Upload size caps live in media/files.py.
HARD_PAGES = MAX_PAGES
HARD_VIDEO_SECONDS = Settings.model_fields["video_max_seconds"].default

_DEFAULT = {
    "caption_typical": 2_200, "caption_limit": None,
    "hashtags_typical": 10, "hashtags_limit": 30,
    "images_typical": 10, "images_limit": 20,
    "pages_typical": 20, "pages_limit": 300,
    "video_typical_s": 180, "video_limit_s": 15 * 60,
}
CHANNELS: dict[str, dict[str, Any]] = {
    "instagram": {"caption_limit": 2_200, "caption_typical": 1_000, "hashtags_limit": 30, "images_limit": 20,
                  "images_typical": 10, "pages_limit": 0, "video_typical_s": 90, "video_limit_s": 20 * 60},
    "tiktok": {"caption_limit": 2_200, "caption_typical": 300, "images_limit": 35, "pages_limit": 0,
               "video_typical_s": 180, "video_limit_s": 10 * 60},
    "x": {"caption_limit": 25_000, "caption_typical": 280, "hashtags_typical": 3, "images_limit": 4,
          "images_typical": 4, "pages_limit": 0, "video_typical_s": 140, "video_limit_s": 4 * 3600},
    "linkedin": {"caption_limit": 3_000, "caption_typical": 1_300, "hashtags_typical": 5, "images_limit": 20,
                 "pages_typical": 15, "pages_limit": 300, "video_typical_s": 180, "video_limit_s": 15 * 60},
    "youtube": {"caption_limit": 5_000, "caption_typical": 2_000, "images_limit": 1, "pages_limit": 0,
                "video_typical_s": 15 * 60, "video_limit_s": 12 * 3600},
    "youtube_shorts": {"caption_limit": 5_000, "caption_typical": 500, "images_limit": 0, "pages_limit": 0,
                       "video_typical_s": 60, "video_limit_s": 180},
    "facebook": {"caption_typical": 1_000, "images_limit": 80, "video_typical_s": 180},
    "threads": {"caption_limit": 500, "caption_typical": 500, "images_limit": 20, "pages_limit": 0,
                "video_typical_s": 90, "video_limit_s": 5 * 60},
    "whatsapp": {"caption_limit": 65_536, "caption_typical": 1_000, "video_typical_s": 90},
    "email": {"caption_typical": 10_000, "pages_typical": 10},
    "blog": {"caption_typical": 30_000, "pages_typical": 40},
}


def channel_profile(channel: str) -> dict[str, Any]:
    key = channel.strip().lower().replace(" ", "_")
    return {**_DEFAULT, **CHANNELS.get(key, {})}


@dataclass
class Irregularity:
    code: str  # caption_length, page_count, image_pixels, hidden_characters, ...
    subject: str  # "caption", "image hero", "document brochure", "video promo"
    value: str
    expected: str
    why: str
    over_limit: bool = False  # the platform itself would refuse it


@dataclass
class Profile:
    channel: str
    irregularities: list[Irregularity] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "metrics": self.metrics,
                "irregularities": [asdict(i) for i in self.irregularities]}


_HASHTAG = re.compile(r"(?<!\w)#\w+")
_MENTION = re.compile(r"(?<!\w)@\w+")
_URL = re.compile(r"https?://\S+")


def hidden_characters(text: str) -> int:
    """Invisible characters that are not part of an emoji.

    Uses the same definition the term matcher reads through (format
    characters, variation selectors, CGJ, Hangul fillers, tag characters), so
    the intake gate can't be skipped with a character the matcher knows
    about. Emoji legitimately carry some of them: a variation selector after a
    symbol, a joiner between people in a family emoji, tag letters in a
    subdivision flag; those are not counted.
    """
    n = 0
    for i, ch in enumerate(text):
        if not _invisible(ch):
            continue
        o = ord(ch)
        prev = text[i - 1] if i else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if (o in (0xFE0E, 0xFE0F) and prev and (is_emoji(prev, ch) or prev in _KEYCAP_BASE)) \
                or (o == 0x200D and prev and nxt and (is_emoji(prev, ch) or prev == "\ufe0f")
                    and is_emoji(nxt, text[i + 2:i + 3])) \
                or (0xE0020 <= o <= 0xE007F and _in_tag_flag(text, i)):
            continue
        n += 1
    return n


_KEYCAP_BASE = set("0123456789#*")


def _in_tag_flag(text: str, i: int) -> bool:
    """Tag characters after a black flag (England, Scotland, Wales)."""
    j = i
    while j > 0 and 0xE0020 <= ord(text[j - 1]) <= 0xE007F:
        j -= 1
    return j > 0 and text[j - 1] == "\U0001f3f4"
_REPEAT = re.compile(r"(.)\1{14,}")


def profile_text(p: Profile, body: str) -> None:
    c = channel_profile(p.channel)
    n = len(body)
    tags = len(_HASHTAG.findall(body))
    invisible = hidden_characters(body)
    p.metrics.update(caption_chars=n, hashtags=tags, mentions=len(_MENTION.findall(body)),
                     links=len(_URL.findall(body)), invisible_chars=invisible)
    if c["caption_limit"] and n > c["caption_limit"]:
        p.irregularities.append(Irregularity("caption_length", "caption", f"{n:,} characters",
                                             f"at most {c['caption_limit']:,} on {p.channel}",
                                             "the platform will cut or refuse it", over_limit=True))
    elif n > c["caption_typical"]:
        p.irregularities.append(Irregularity("caption_length", "caption", f"{n:,} characters",
                                             f"usually under {c['caption_typical']:,} on {p.channel}",
                                             "much longer than posts on this channel normally are"))
    if tags > c["hashtags_limit"]:
        p.irregularities.append(Irregularity("hashtags", "caption", str(tags), f"at most {c['hashtags_limit']}",
                                             "over the platform's hashtag limit", over_limit=True))
    elif tags > c["hashtags_typical"]:
        p.irregularities.append(Irregularity("hashtags", "caption", str(tags), f"usually {c['hashtags_typical']} "
                                             "or fewer", "hashtag stuffing reads as spam"))
    if invisible:
        p.irregularities.append(Irregularity("hidden_characters", "caption", f"{invisible} invisible character(s)",
                                             "none", "invisible characters are a common way to slip words past "
                                             "filters; Verytas reads through them, but say why they are there"))
    if _REPEAT.search(body):
        p.irregularities.append(Irregularity("repeated_characters", "caption", "15+ repeats of one character",
                                             "normal text", "long runs pad the post and can hide content"))


def profile_image(p: Profile, name: str, raw: bytes) -> None:
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
    except Exception:  # noqa: BLE001, unreadable images are reported by the review itself
        return
    mp = w * h / 1e6
    p.metrics.setdefault("images", []).append({"name": name, "width": w, "height": h, "megapixels": round(mp, 1),
                                               "bytes": len(raw), "format": img.format})
    subject = f"image {name}"
    # Feeds display at 1080 to 2048 px wide; 25 MP is a large camera original.
    if mp > 25:
        p.irregularities.append(Irregularity("image_pixels", subject, f"{w}x{h} ({mp:.0f} MP)", "under 25 MP",
                                             "far larger than any feed displays; usually an unexported original"))
    if min(w, h) < 200:
        p.irregularities.append(Irregularity("image_tiny", subject, f"{w}x{h}", "at least 200 px on each side",
                                             "too small to read on any feed, and too small to check reliably"))
    ratio = max(w, h) / max(1, min(w, h))
    # 4:1 is the widest common format (LinkedIn banners); feeds crop anything past it.
    if ratio > 4.0:
        p.irregularities.append(Irregularity("image_aspect", subject, f"{ratio:.1f}:1", "no wider than 4:1",
                                             "extreme strips are cropped by feeds and can hide content"))
    if len(raw) > 8 * 1024 * 1024:
        p.irregularities.append(Irregularity("image_bytes", subject, f"{len(raw) / 1e6:.1f} MB", "under 8 MB",
                                             "over most platforms' upload limit", over_limit=True))
    trailing = _trailing_bytes(raw, img.format)
    if trailing > 1024:
        p.irregularities.append(Irregularity(
            "image_appended_data", subject, f"{trailing:,} bytes after the image ends", "none",
            "data hidden after the end of an image file is a classic way to smuggle a payload"))
    if _has_gps(img):
        p.irregularities.append(Irregularity("image_location", subject, "GPS location in metadata", "none",
                                             "publishing it reveals where the photo was taken"))
    if getattr(img, "n_frames", 1) > 1:
        p.metrics["images"][-1]["frames"] = img.n_frames


def _trailing_bytes(raw: bytes, fmt: str | None) -> int:
    """Bytes after the image's real end. The end is found by walking the file's own structure, not by
    searching for the last end marker: a payload that finishes with a fake marker would hide itself."""
    end = _png_end(raw) if fmt == "PNG" else _jpeg_end(raw) if fmt == "JPEG" else None
    return max(0, len(raw) - end) if end is not None else 0


def _png_end(raw: bytes) -> int | None:
    """Offset just past the first IEND chunk, walking chunk by chunk (length, type, data, CRC)."""
    at = 8  # the signature
    while at + 12 <= len(raw):
        length = int.from_bytes(raw[at:at + 4], "big")
        kind = raw[at + 4:at + 8]
        at += 12 + length
        if kind == b"IEND":
            return at
    return None


def _jpeg_end(raw: bytes) -> int | None:
    """Offset just past the EOI marker that closes the first scan. Segments are walked up to the first
    start-of-scan, so a thumbnail's own markers in the EXIF block are skipped; inside scan data a 0xFF
    byte is always stuffed or a restart marker, so the first FF D9 after it is the real end."""
    at = 2  # SOI
    while at + 4 <= len(raw) and raw[at] == 0xFF:
        marker = raw[at + 1]
        if marker == 0xFF:  # fill byte before a marker
            at += 1
            continue
        length = int.from_bytes(raw[at + 2:at + 4], "big")
        if marker == 0xDA:  # start of scan: the entropy-coded data follows its header
            eoi = raw.find(b"\xff\xd9", at + 2 + length)
            return eoi + 2 if eoi >= 0 else None
        at += 2 + length
    return None


def _has_gps(img: Image.Image) -> bool:
    try:
        exif = img.getexif()
        return bool(exif and exif.get_ifd(0x8825))
    except Exception:  # noqa: BLE001, odd EXIF must not break profiling
        return False


def profile_document(p: Profile, name: str, raw: bytes, pages: int | None, flags: list[str]) -> None:
    c = channel_profile(p.channel)
    p.metrics.setdefault("documents", []).append({"name": name, "pages": pages, "bytes": len(raw)})
    subject = f"document {name}"
    if pages is not None:
        if c["pages_limit"] == 0:
            p.irregularities.append(Irregularity("document_on_channel", subject, f"{pages} page(s)",
                                                 f"{p.channel} does not take document posts",
                                                 "it will have to be posted another way", over_limit=True))
        elif pages > c["pages_limit"]:
            p.irregularities.append(Irregularity("page_count", subject, f"{pages} pages",
                                                 f"at most {c['pages_limit']}", "over the platform's limit",
                                                 over_limit=True))
        elif pages > c["pages_typical"]:
            p.irregularities.append(Irregularity("page_count", subject, f"{pages} pages",
                                                 f"usually {c['pages_typical']} or fewer for {p.channel}",
                                                 "much longer than social documents normally are"))
        if pages > HARD_PAGES:
            p.irregularities.append(Irregularity("page_count_processing", subject, f"{pages} pages",
                                                 f"Verytas checks the first {HARD_PAGES}",
                                                 "the rest will be reported as not checked"))
    for flag in flags:
        p.irregularities.append(Irregularity("document_active_content", subject, flag, "none",
                                             "scripts and embedded files have no place in a post and can carry "
                                             "malware"))


def profile_video(p: Profile, name: str, meta: dict[str, Any]) -> None:
    c = channel_profile(p.channel)
    p.metrics.setdefault("videos", []).append({"name": name, **meta})
    subject = f"video {name}"
    seconds = meta.get("duration") or 0
    if seconds > c["video_limit_s"]:
        p.irregularities.append(Irregularity("video_length", subject, f"{seconds:.0f} s",
                                             f"at most {c['video_limit_s']} s on {p.channel}",
                                             "the platform won't take it", over_limit=True))
    elif seconds > c["video_typical_s"]:
        p.irregularities.append(Irregularity("video_length", subject, f"{seconds:.0f} s",
                                             f"usually under {c['video_typical_s']} s on {p.channel}",
                                             "much longer than video on this channel normally is"))
    if seconds > HARD_VIDEO_SECONDS:
        p.irregularities.append(Irregularity("video_length_processing", subject, f"{seconds:.0f} s",
                                             f"Verytas checks the first {HARD_VIDEO_SECONDS // 60} minutes",
                                             "the rest will be reported as not checked"))
    w, h = meta.get("width") or 0, meta.get("height") or 0
    if w and h:
        if w * h > 3840 * 2160:
            p.irregularities.append(Irregularity("video_resolution", subject, f"{w}x{h}", "up to 4K",
                                                 "beyond 4K is downscaled by every platform"))
        if min(w, h) < 360:
            p.irregularities.append(Irregularity("video_resolution", subject, f"{w}x{h}", "at least 360p",
                                                 "too small to read on screen, or to check reliably"))
    fps = meta.get("fps") or 0
    if fps > 120:
        p.irregularities.append(Irregularity("video_fps", subject, f"{fps:.0f} fps", "60 fps or less",
                                             "unusual frame rate; single frames can hide content"))
    bitrate = meta.get("bitrate") or 0
    if bitrate > 60_000_000:
        p.irregularities.append(Irregularity("video_bitrate", subject, f"{bitrate / 1e6:.0f} Mbps", "under 60 Mbps",
                                             "far above what any platform streams"))


def profile_counts(p: Profile) -> None:
    """Whole-post checks, run once every part has been profiled."""
    c = channel_profile(p.channel)
    n = len(p.metrics.get("images", []))
    if c["images_limit"] is not None and n > c["images_limit"]:
        p.irregularities.append(Irregularity("image_count", "post", f"{n} images",
                                             f"at most {c['images_limit']} on {p.channel}",
                                             "the platform won't take that many", over_limit=True))
    elif n > c["images_typical"]:
        p.irregularities.append(Irregularity("image_count", "post", f"{n} images",
                                             f"usually {c['images_typical']} or fewer", "unusually many images"))
