"""Prism's agent tree: delegation shaped by what the submission contains.

Prism does not run a fixed pipeline. It looks at a submission and spawns an
agent per part; each agent looks at its part and spawns its own children:

    Prism
    |- text agent (typed draft)            -> rule checks, claim verifier, semantic judge
    |- image agent (attached image)        -> OCR -> text agent ...
    |                                      -> brand-asset matcher, scene reader
    '- document agent (PDF / Word)         -> page agent per page
         '- page agent                     -> text agent (text layer)
                                           -> image agent (scanned page, rendered)
                                           -> image agent (each pasted screenshot) -> ...

So a screenshot inside page 3 of a brochure gets its own OCR, which gets its
own text agent, which runs the same checks as typed text. Depth and the total
number of agents are capped per review; anything cut off by a cap, a timeout
or a crash is recorded as "not checked" on its node, never as a pass. Work
that judges the submission as a whole (the typed draft, presentation, intake
policy, context layers, the creator's note) is marked essential and draws on
a reserve, so a 40-page PDF can't starve it.

Every node is kept (role, label, status, timing, findings) and returned with
the review, so the UI can show exactly how a piece of content was checked.
"""

from __future__ import annotations

import asyncio
import dataclasses
import difflib
import io
import itertools
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from PIL import Image

from verytas.checks import phonetic
from verytas.checks.base import CheckContext, RawFinding, RuleView, Source
from verytas.checks.claims import check_claims
from verytas.checks.crosscheck import figures
from verytas.checks.deterministic import run_deterministic
from verytas.checks.semantic import check_semantic
from verytas.ingest.segment import image_units, segment
from verytas.media import assets as asset_match
from verytas.media import ocr as local_ocr
from verytas.media import pixels
from verytas.media.documents import extract_docx, extract_html, extract_pdf, extract_pptx, extract_xlsx
from verytas.media.files import (
    MAX_DOC_BYTES,
    MAX_IMAGE_BYTES,
    MediaError,
    animation_frames,
    decode_b64,
    open_image,
    png_b64,
    shrink,
    sniff,
)
from verytas.prism.board import Board, Evidence, crosscheck_agent
from verytas.prism.characters import characters_agent, pick_frames
from verytas.prism.governor import Governor, TaskOutcome
from verytas.prism.people_agent import faces_agent
from verytas.providers.base import JudgeProvider, LLMProvider, ProviderError
from verytas.providers.vision import InspectTask, Reference, SceneReport, TranscribeTask
from verytas.security.terms import term_pattern

log = logging.getLogger("verytas.prism.agents")

# Which check families each text worker covers, for the coverage scorecard.
WORKER_COVERS = {
    "rule checks": {"terminology", "accessibility", "confidentiality", "visual", "legal"},
    "claim verifier": {"claims"},
    "semantic judge": {"tone", "messaging"},
}
# What an unreadable image or document leaves unchecked.
MEDIA_COVERS = {"terminology", "confidentiality", "claims", "visual"}
MAX_VISION_REFERENCES = 4  # reference images per vision call; more dilutes the comparison
# Similarity a retired version must lead the current artwork by, at the same spot, to be called the one
# that is there: versions differing in a detail score within a hair of each other on either.
RETIRED_LEAD = 0.02
SCANNED_FALLBACK_CHARS = 40  # a scanned page with less OCR text than this is re-read by the vision model
_EXTENDABLE_PARTS = {"face", "head", "icon", "wordmark"}


@dataclass
class AgentNode:
    id: str
    role: str
    label: str
    parent: str | None
    depth: int
    status: str = "running"  # ok | not_checked | failed | skipped
    note: str | None = None
    ms: int = 0
    findings: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    essential: bool = False


class AgentTree:
    def __init__(self, max_depth: int, max_nodes: int) -> None:
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        # Essential work may run past the normal budget, up to this ceiling, and
        # growth for long documents stops below it so the reserve stays free.
        self.hard_max = max_nodes * 4
        self._grow_max = max_nodes * 3
        self.nodes: dict[str, AgentNode] = {}
        self._ids = itertools.count(1)

    def grow(self, extra: int) -> None:
        """Widen the budget for a submission whose size is now known (pages of a document)."""
        self.max_nodes = min(self._grow_max, self.max_nodes + extra)

    async def spawn[T](self, parent: AgentNode | None, role: str, label: str,
                       work: Callable[[AgentNode], Awaitable[T]], *, essential: bool = False) -> T | None:
        depth = parent.depth + 1 if parent else 0
        essential = essential or bool(parent and parent.essential)
        node = AgentNode(f"a{next(self._ids)}", role, label, parent.id if parent else None, depth,
                         essential=essential)
        self.nodes[node.id] = node
        if depth > self.max_depth or len(self.nodes) > (self.hard_max if essential else self.max_nodes):
            node.status, node.note = "skipped", "agent budget for this review reached"
            return None
        started = time.monotonic()
        try:
            result = await work(node)
        except (ProviderError, MediaError, TimeoutError) as exc:
            node.status, node.note = "not_checked", (str(exc) or type(exc).__name__)[:300]
            return None
        except Exception as exc:  # noqa: BLE001, one bad part must not sink the review
            log.exception("agent %s (%s) crashed", node.id, role)
            node.status, node.note = "failed", f"{type(exc).__name__}: internal error"
            return None
        finally:
            node.ms = int((time.monotonic() - started) * 1000)
        if node.status == "running":
            node.status = "ok"
        return result

    def as_list(self) -> list[dict[str, Any]]:
        return [asdict(n) for n in self.nodes.values()]

    def gaps(self) -> list[AgentNode]:
        return [n for n in self.nodes.values() if n.status in ("not_checked", "failed", "skipped")]


@dataclass
class OfficialAsset:
    id: int
    name: str
    kind: str
    part: str
    restricted: bool  # tier above the content's: may not be shown to a model, and appearing at all is a leak
    image: Image.Image
    prepared: asset_match.PreparedAsset
    b64: str
    wordmark: str | None = None
    retired: bool = False  # an old version: finding it means the post uses out-of-date artwork

    @property
    def official(self) -> bool:
        """Current artwork of the brand's own: what the vision model is shown and copies are judged by."""
        return self.kind != "competitor" and not self.retired


@dataclass
class ReviewRun:
    """Shared state for one review's agents. Single event loop, so plain lists are safe."""

    base: CheckContext
    llm: LLMProvider
    judge: JudgeProvider
    vision: LLMProvider
    governor: Governor
    tree: AgentTree
    rule_by_code: dict[str, RuleView]
    assets: list[OfficialAsset]
    content_tier_rank: int
    allow_cloud_vision: bool
    semantic_threshold: float
    ocr_min_confidence: float
    blobs: dict[str, bytes] = field(default_factory=dict)
    # System-computed intake profile (media/profile.py) and the one creator
    # statement checks may use: a declaration that AI was used. It can only
    # add a duty to label, never clear a finding.
    profile: dict[str, Any] = field(default_factory=dict)
    declared_ai: bool = False
    asr_model: str = "small"
    asr_long_model: str = "base"
    asr_long_seconds: int = 180
    # The brand's public names for speech recognition (see video.transcribe); never confidential terms,
    # which a prompted Whisper can echo into silence and so report a leak that never happened.
    asr_vocabulary: str = ""
    # The same public names as a list: OCR lines are repaired against them (local_ocr.restore_names).
    brand_names: list[str] = field(default_factory=list)
    video_max_seconds: int = 900
    media_timeout_s: float = 180.0
    rule_thresholds: dict[str, float] = field(default_factory=dict)
    # Where text and logos sit in each attached image or video frame, for the
    # presentation agent's crop and safe-zone checks, and the "at a glance" view.
    layouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    glance: list[str] = field(default_factory=list)
    # The caption is longer than the channel shows before "...more", so the first screen can read differently.
    caption_folded: bool = False
    # The creator's own account of what the images and video contain (typed, or a transcribed voice
    # note): names the visual checks look for, and claims they verify.
    brief: str = ""
    # Approved people and their reference photos, for the faces check (prism/people_agent.py).
    people: Any = None
    # The vision worker's client (vision/client.py), for redrawn mascots (prism/characters.py); None when
    # no worker is configured.
    characters: Any = None
    sources: list[Source] = field(default_factory=list)
    findings: list[RawFinding] = field(default_factory=list)
    outcomes: list[TaskOutcome] = field(default_factory=list)
    rule_problems: list[tuple[str, str, str]] = field(default_factory=list)
    scenes: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Categories read only in part (sampled, truncated): reported as degraded, with a note.
    partial: set[str] = field(default_factory=set)
    worker_of: dict[int, str] = field(default_factory=dict)
    node_of: dict[int, AgentNode] = field(default_factory=dict)
    # Typed evidence every agent posts as it works (prism/board.py), compared across parts at the end.
    board: Board = field(default_factory=Board)
    # Must-rule questions also put to the larger judge (prism/second_look.py); None when off.
    second_look: Any = None
    # This workspace's past reviewer decisions (prism/precedent.py), and whether the judge gets them as examples.
    precedents: Any = None
    precedent_examples: bool = False

    def asr_for(self, pcm: Any) -> str:
        """The speech model for this much audio (16 kHz samples): the better one unless it is long."""
        return self.asr_long_model if len(pcm) / 16_000 > self.asr_long_seconds else self.asr_model

    def add(self, node: AgentNode, worker: str, found: list[RawFinding]) -> None:
        for f in found:
            self.worker_of[id(f)] = worker
            self.node_of[id(f)] = node
        self.findings.extend(found)
        node.findings += len(found)

    def drop(self, gone: list[RawFinding]) -> None:
        """Take findings back out, so the agent tree's counts match what the review reports."""
        ids = {id(f) for f in gone}
        self.findings[:] = [f for f in self.findings if id(f) not in ids]
        for i in ids:
            self.worker_of.pop(i, None)
            node = self.node_of.pop(i, None)
            if node is not None:
                node.findings -= 1

    async def blocking[T](self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run blocking media work in a thread, with a deadline.

        A thread can't be cancelled, so a decoder that hangs keeps its thread
        until it returns; the review stops waiting and records the part as
        not checked (spawn turns TimeoutError into not_checked).
        """
        return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), self.media_timeout_s)

    def leak_patterns(self):
        return [term_pattern(t.term, loose=True) for t in self.base.terms]

    def payload(self, item: dict[str, Any], limit: int) -> bytes:
        """An attachment's bytes, from an uploaded blob or inline base64."""
        if item.get("blob_id"):
            raw = self.blobs.get(item["blob_id"])
            if raw is None:
                raise MediaError(f"uploaded file {item['blob_id']} is missing")
            return raw
        if item.get("data_base64"):
            return decode_b64(item["data_base64"], limit)
        raise MediaError("attachment has no data")


# --- the plan ---------------------------------------------------------------------------------------

async def plan(run: ReviewRun, root: AgentNode) -> None:
    """Prism's own step: one child per part of the submission."""
    body = Source("body", "body", run.base.body, "typed")
    work = [run.tree.spawn(root, "text", "Typed draft", lambda n: text_agent(run, n, body), essential=True)]
    for img in run.base.attachments.get("images", []):
        if img.get("data_base64") or img.get("blob_id"):
            image_id = f"img:{img.get('id')}"
            work.append(run.tree.spawn(root, "image", f"Image {img.get('id')}",
                                       lambda n, img=img, iid=image_id: _attached_image(run, n, img, iid)))
    for doc in run.base.attachments.get("documents", []):
        work.append(run.tree.spawn(root, "document", doc.get("name") or f"Document {doc.get('id')}",
                                   lambda n, doc=doc: document_agent(run, n, doc)))
    for vid in run.base.attachments.get("videos", []):
        work.append(run.tree.spawn(root, "video", vid.get("name") or f"Video {vid.get('id')}",
                                   lambda n, vid=vid: video_agent(run, n, vid)))
    await asyncio.gather(*work)
    from verytas.prism.presentation import presentation_agent

    # Only now is every part read, so only now can the parts be compared with each other.
    await run.tree.spawn(root, "crosscheck", "Compare the parts with each other", lambda n: crosscheck_agent(run, n),
                         essential=True)

    await run.tree.spawn(root, "presentation", "How it looks on the platform", lambda n: presentation_agent(run, n),
                         essential=True)
    await run.tree.spawn(root, "policy", "Intake and disclosure", lambda n: policy_agent(run, n), essential=True)


# --- text ---------------------------------------------------------------------------------------------

async def text_agent(run: ReviewRun, node: AgentNode, source: Source,
                     attachments: dict[str, Any] | None = None) -> None:
    """The three text workers on one source, as child agents. `attachments` are pictures that belong to
    this source (a web page's), for the checks that read them."""
    run.sources.append(source)
    for fig in figures(source.id, source.text, source.timeline, source.kind):
        run.board.post(Evidence("figure", source.id, fig, fig.time))
    node.detail = {"source": source.id, "route": source.route, "chars": len(source.text),
                   "confidence": round(source.confidence, 3)}
    if not source.text.strip() and not attachments:
        node.note = "no text"
        return
    is_body = source.id == "body"
    ctx = run.base if is_body else CheckContext(
        body=source.text, units=segment(source.text), rules=run.base.rules, facts=run.base.facts,
        terms=run.base.terms, attachments=attachments or {}, channel=run.base.channel, today=run.base.today,
        profile=run.base.profile, whole_post=False, spoken=source.kind == "speech",
    )
    if is_body:
        ctx.units = segment(source.text) + image_units(run.base.attachments)

    judged = ctx
    if run.precedents is not None and run.precedent_examples:
        # The judge reads the rule with this workspace's nearest decided cases as extra examples.
        judged = dataclasses.replace(ctx, rules=[run.precedents.with_examples(r, source.text) for r in ctx.rules])

    async def worker(name: str, fn: Callable[[], Awaitable[list[RawFinding]]]) -> None:
        async def go(child: AgentNode) -> None:
            outcome = await run.governor.run(name, fn)
            run.outcomes.append(outcome)
            child.status = "ok" if outcome.status == "ok" else outcome.status
            child.note = outcome.note
            found = [_relocate(f, source) for f in outcome.findings]
            run.add(child, name, found)
            node.findings += len(found)

        await run.tree.spawn(node, "worker", name, go)

    await asyncio.gather(
        worker("rule checks", lambda: run.blocking(run_deterministic, ctx, run.rule_problems)),
        worker("claim verifier", lambda: check_claims(ctx, run.llm, run.judge)),
        worker("semantic judge", lambda: check_semantic(judged, run.judge, threshold=run.semantic_threshold,
                                                        per_rule=run.rule_thresholds,
                                                        second=run.second_look.at(source.id) if run.second_look
                                                        else None)),
    )


def _relocate(f: RawFinding, source: Source) -> RawFinding:
    if source.id != "body":
        f.source = source.id
        f.locator = dict(source.locator)
        f.unit_id = f"{source.id}/{f.unit_id}"[:200]
        if source.timeline and f.span_start is not None:
            hit = next(((t0, t1) for a, b, t0, t1 in source.timeline if a <= f.span_start < b + 1), None)
            if hit:
                f.locator["time"] = list(hit)
    return f


# --- images ---------------------------------------------------------------------------------------------

async def _attached_image(run: ReviewRun, node: AgentNode, img: dict[str, Any], image_id: str) -> None:
    raw = run.payload(img, MAX_IMAGE_BYTES)
    if not sniff(raw).startswith("image/"):
        raise MediaError("attachment is not an image")
    pil = await run.blocking(open_image, raw)
    run.layouts[image_id] = {"size": pil.size, "lines": [], "assets": []}
    locator = {"image": img.get("id")}
    await image_agent(run, node, pil, image_id, locator, context=run.base.body)
    if sniff(raw) in ("image/gif", "image/webp"):
        await _animation(run, node, raw, image_id, locator)


async def _animation(run: ReviewRun, node: AgentNode, raw: bytes, image_id: str, locator: dict[str, Any]) -> None:
    """Later frames of an animated image can carry their own text; read a sample of them."""
    try:
        count, extra = await run.blocking(animation_frames, raw)
    except MediaError as exc:
        # The first frame was already checked; only the later frames are lost.
        run.notes.append(f"{image_id}: later animation frames not read ({exc})")
        run.partial.add("visual")
        return
    if count <= 1:
        return
    node.detail["frames"] = count
    await asyncio.gather(*(
        run.tree.spawn(node, "ocr", f"Read text in a later frame ({k + 2} of {len(extra) + 1} sampled)",
                       lambda n, frame=frame, k=k: ocr_agent(run, n, frame, f"{image_id}@f{k + 2}",
                                                            {**locator, "frame": k + 2}, scanned=False))
        for k, frame in enumerate(extra)))
    run.notes.append(f"{image_id}: animated ({count} frames); text read on {len(extra) + 1} sampled frames, "
                     "artwork and scene on the first frame only")
    run.partial.add("visual")
    if count > len(extra) + 1:
        run.partial |= MEDIA_COVERS


async def image_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str,
                      locator: dict[str, Any], *, context: str = "", scanned: bool = False) -> None:
    node.detail = {"image": image_id, "size": list(pil.size), "scanned_page": scanned}
    ocr = await run.tree.spawn(node, "ocr", "Read text in image",
                               lambda n: ocr_agent(run, n, pil, image_id, locator, scanned=scanned))
    lines = ocr.lines if ocr else []
    # Redaction needs the OCR result: without it there is nothing to black
    # out, and the image would leave with every confidential word readable.
    send = run.allow_cloud_vision and ocr is not None

    async def nothing():
        return None

    matches, scene = await asyncio.gather(
        run.tree.spawn(node, "assets", "Match official assets", lambda n: _pixel_assets(run, n, pil))
        if run.assets else nothing(),
        run.tree.spawn(node, "scene", "Describe scene and compare assets",
                       lambda n: scene_agent(run, n, pil, image_id, ocr, context))
        if send else nothing(),
    )
    if not run.allow_cloud_vision:
        run.notes.append(f"{image_id}: not sent to a vision model (content tier or offline mode)")
    elif ocr is None:
        run.notes.append(f"{image_id}: not sent to a vision model because local OCR failed, so confidential "
                         "text in it could not be blacked out first")
    _asset_findings(run, node, image_id, locator, matches or [], scene, lines)
    _drop_artwork_lettering(run, f"{image_id}:ocr", lambda *_: _official_boxes(run, matches or []))
    if any(a.kind == "mascot" for a in run.assets):
        copies = {m.asset_id for m in matches or [] if m.found}
        await run.tree.spawn(node, "characters", "Look for redrawn mascots",
                             lambda n: characters_agent(run, n, [(None, pil)], image_id, locator, copies))
    if run.people is not None:
        await run.tree.spawn(node, "faces", "Identify faces", lambda n: faces_agent(run, n, pil, image_id, locator))
    contrast = run.rule_by_code.get("A11Y-CONTRAST")
    # A scan's contrast is the scanner's, not the author's.
    if contrast and lines and not scanned:
        await run.tree.spawn(node, "contrast", "Measure text contrast",
                             lambda n: _contrast_agent(run, n, pil, image_id, locator, lines, contrast))
    if image_id in run.layouts:
        # Only the brand's current artwork: a cropped rival logo or old version is not "our asset cut off".
        names = {a.id: f"{a.kind} '{a.name}'" for a in run.assets if a.official}
        run.layouts[image_id]["lines"] = [(ln.text, ln.box) for ln in lines]
        run.layouts[image_id]["assets"] = [(names[m.asset_id], m.box)
                                          for m in matches or [] if m.found and m.asset_id in names]

    # A second opinion on text: if the vision model read substantially more
    # than local OCR (stylised lettering, handwriting), check that text too.
    if scene and len(scene.text_in_image) > 20 and _novel(scene.text_in_image, ocr.text if ocr else ""):
        src = Source(f"{image_id}:vision-text", "ocr", scene.text_in_image, "ocr:vision", 0.7,
                     {**locator, "image": image_id}, parent=image_id)
        await run.tree.spawn(node, "text", "Text the vision model read", lambda n: text_agent(run, n, src))


async def ocr_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str, locator: dict[str, Any],
                    *, scanned: bool) -> local_ocr.OcrResult:
    result = await run.blocking(local_ocr.read, pil)
    text, restored = local_ocr.restore_names(result.text, run.brand_names)
    route, confidence = "ocr:local", result.confidence
    # "Weak" needs real text read badly, not a stray fragment on a picture.
    weak = sum(ch.isalnum() for ch in text) >= 8 and confidence < run.ocr_min_confidence
    thin_scan = scanned and len(text) < SCANNED_FALLBACK_CHARS
    node.detail = {"engine": result.engine, "lines": len(result.lines), "confidence": round(confidence, 3)}
    if restored:
        node.detail["restored_names"] = restored
    if result.foreign:
        # Text in a script local OCR has no model for (Hindi, most likely): the vision model reads it, or
        # the review says it went unread.
        node.detail["unreadable_script_lines"] = len(result.foreign)
        weak = True
        if not run.allow_cloud_vision:
            _unreadable(run, node, image_id, locator,
                        "text in a script local OCR cannot read (likely Devanagari or another Indic script)")

    if (weak or thin_scan) and run.allow_cloud_vision:
        encoded, hidden = await run.blocking(_redacted_png, pil, result, run.leak_patterns(), None)
        node.detail["redacted_regions"] = hidden
        transcript = await run.tree.spawn(node, "ocr-fallback", "Vision transcription",
                                          lambda n: run.vision.run(TranscribeTask(encoded)))
        if transcript is not None and transcript.text.strip():
            # Merge, never replace: the vision model saw a copy with confidential
            # terms blacked out, so its text lacks exactly what local OCR found
            # (black-box finding: a scanned page's codename went unflagged).
            novel = [ln for ln in transcript.text.splitlines() if ln.strip() and _novel(ln, text)]
            if novel:
                text = (text + "\n" if text else "") + "\n".join(novel)
                route = "ocr:local+vision"
                confidence = max(confidence, 0.85 if transcript.legible else 0.6)
            if not transcript.legible:
                _unreadable(run, node, image_id, locator, "the vision model reports parts it could not read")

    if weak and route == "ocr:local" and confidence < 0.6:
        _unreadable(run, node, image_id, locator, f"local OCR confidence {confidence:.0%} and no fallback")
    elif thin_scan and route == "ocr:local":
        # Could be a blank or photo-only page; say it wasn't double-checked
        # rather than raising a finding on every empty page.
        run.notes.append(f"{image_id}: scanned page with little readable text, not re-read by a vision model")

    if text.strip():
        src = Source(f"{image_id}:ocr", "ocr", text, route, confidence, {**locator, "image": image_id},
                     parent=image_id, regions=_line_regions(result.lines))
        await run.tree.spawn(node, "text", "Text found in image", lambda n: text_agent(run, n, src))
    return result


# Text is sized as it shows when telling large text (WCAG: 18pt, 24 CSS px) from body text: a post at a
# phone's width, where most are seen, and a document page at a letter page's width (8.5 in at 96 px/in).
# An OCR box is about 1.2 times the font size tall, or about the cap height for a line in capitals.
_PHONE_CSS_WIDTH = 390
_PAGE_CSS_WIDTH = 816
_LARGE_TEXT_PX = 24
_CONTRAST_MAX_FINDINGS = 5
# A measured ratio this close under the minimum is reported as a warning: the measurement is good to
# about this much on compressed, small or anti-aliased text.
_CONTRAST_MARGIN = 0.85


def _low_contrast_lines(pil: Image.Image, lines: list[local_ocr.OcrLine], min_ratio: float, min_large: float,
                        *, page: bool = False) -> list[tuple[local_ocr.OcrLine, tuple, tuple, float, float, bool]]:
    """Lines whose text is below the contrast minimum, with (text colour, background, ratio, needed, busy),
    worst first."""
    import numpy as np

    from verytas.checks.color import text_contrast

    # Transparent pixels have no colour of their own until something is drawn behind them; flattening
    # them would invent a background, so lines over transparency are not measured.
    alpha = np.asarray(pil.getchannel("A")) if "A" in pil.getbands() else None
    arr = np.asarray(pil.convert("RGB"))
    height, width = arr.shape[:2]
    scale = min(1.0, (_PAGE_CSS_WIDTH if page else _PHONE_CSS_WIDTH) / width)
    out = []
    for ln in lines:
        x0, y0, x1, y1 = ln.box
        h = y1 - y0
        # Stray marks and badly read fragments say nothing about legibility.
        if h < 8 or ln.confidence < 0.6 or sum(ch.isalnum() for ch in ln.text) < 3:
            continue
        pad = max(3, h // 4)
        box = (slice(max(0, y0 - pad), min(height, y1 + pad)), slice(max(0, x0 - pad), min(width, x1 + pad)))
        if alpha is not None and (alpha[box] < 250).mean() > 0.05:
            continue
        measured = text_contrast(arr[box])
        if measured is None:
            continue
        fg, bg, ratio, busy = measured
        letters = [ch for ch in ln.text if ch.isalpha()]
        caps = bool(letters) and all(ch.isupper() for ch in letters)
        font_px = h * scale / (1.0 if caps else 1.2)
        needed = min_large if font_px >= _LARGE_TEXT_PX else min_ratio
        if ratio < needed:
            out.append((ln, fg, bg, ratio, needed, busy))
    return sorted(out, key=lambda t: t[3] / t[4])


async def _contrast_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str, locator: dict[str, Any],
                          lines: list[local_ocr.OcrLine], rule: RuleView) -> None:
    from verytas.checks.color import rgb_to_hex

    low = await run.blocking(_low_contrast_lines, pil, lines, float(rule.pattern.get("min_ratio", 4.5)),
                             float(rule.pattern.get("min_ratio_large", 3.0)), page="page" in locator)
    node.detail = {"lines": len(lines), "low": len(low)}
    found = []
    for i, (ln, fg, bg, ratio, needed, busy) in enumerate(low[:_CONTRAST_MAX_FINDINGS], start=1):
        over = "a busy background (median colour)" if busy else rgb_to_hex(bg)
        found.append(RawFinding(
            unit_id=f"{image_id}:contrast{i}", category=rule.category,
            title=f'Low contrast text "{ln.text[:60]}": {ratio:.1f}:1 (needs {needed:g}:1)',
            explanation=f"Measured from the image: text {rgb_to_hex(fg)} on {over}, {ratio:.2f}:1. {rule.text}",
            # Over a photo the background colour is an estimate, and just under the line the measurement
            # is too close to call: both are warnings, never blockers.
            confidence=0.6 if busy or ratio >= needed * _CONTRAST_MARGIN else 0.95,
            checker="contrast", rule_code=rule.code, source=image_id,
            locator={**locator, "image": image_id, "box": list(ln.box)},
        ))
    if len(low) > _CONTRAST_MAX_FINDINGS:
        run.notes.append(f"{image_id}: {len(low)} lines are below the contrast minimum; the "
                         f"{_CONTRAST_MAX_FINDINGS} lowest are reported")
    run.add(node, "media", found)


def _unreadable(run: ReviewRun, node: AgentNode, image_id: str, locator: dict[str, Any], why: str) -> None:
    rule = run.rule_by_code.get("MEDIA-UNREAD")
    if rule is None:
        run.notes.append(f"{image_id}: {why}")
        return
    run.add(node, "media", [RawFinding(
        unit_id=image_id, category=rule.category, title=f"Part of {image_id} could not be read reliably",
        explanation=f"{rule.text} ({why}.)", confidence=1.0, checker="media", rule_code=rule.code,
        source=image_id, locator={**locator, "image": image_id},
    )])


async def _pixel_assets(run: ReviewRun, node: AgentNode, pil: Image.Image) -> list[asset_match.AssetMatch]:
    feats = await run.blocking(asset_match.scene_features, pil)
    results = await asyncio.gather(*(run.blocking(asset_match.match, a.prepared, feats) for a in run.assets))
    node.detail = {"assets": len(run.assets), "found": sum(m.found for m in results)}
    return list(results)


def _redacted_png(img: Image.Image, ocr: local_ocr.OcrResult, patterns, side: int | None) -> tuple[str, int]:
    """Black out, shrink and encode in one blocking step (run it in a thread)."""
    hidden_img, hidden = pixels.redact(img, ocr, patterns)
    return png_b64(shrink(hidden_img, side) if side else shrink(hidden_img)), hidden


def _shareable(run: ReviewRun) -> list[OfficialAsset]:
    """The artwork the vision model compares against. Retired versions and competitors' marks are found
    by pixels only: shown to the model as references, they would be judged as if they were the brand's
    approved artwork."""
    return [a for a in run.assets if not a.restricted and a.official]


async def scene_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str,
                      ocr: local_ocr.OcrResult, context: str) -> SceneReport:
    encoded, hidden = await run.blocking(_redacted_png, pil, ocr, run.leak_patterns(), 1400)
    shareable = _shareable(run)
    refs = [Reference(a.name, a.kind, a.part, a.b64) for a in shareable[:MAX_VISION_REFERENCES]]
    node.detail = {"redacted_regions": hidden, "references": len(refs)}
    if len(shareable) > len(refs):
        note = (f"the vision model compared the first {len(refs)} of {len(shareable)} official assets; "
                "the rest were matched by pixels only")
        if note not in run.notes:
            run.notes.append(note)
    report = await run.vision.run(InspectTask(encoded, refs, context))
    run.scenes[image_id] = {**report.model_dump(), "references": [r.name for r in refs]}
    node.detail["tone"] = report.tone
    return report


_WORDS = re.compile(r"[^\W_]+")
DRAWN_MIN_CONFIDENCE = 0.7


def _drawn_only(line: str, known: set[str]) -> bool:
    """Whether a line read from the page render says something its text layer doesn't: any word of four or
    more letters the layer lacks. A word one OCR slip from a layer word ("leamer") is the layer's."""
    for word in _WORDS.findall(line.lower()):
        if len(word) >= 4 and word not in known and not difflib.get_close_matches(word, known, n=1, cutoff=0.75):
            return True
    return False


def _novel(seen: str, known: str) -> bool:
    a = {w for w in seen.lower().split() if len(w) > 2}
    b = {w for w in known.lower().split() if len(w) > 2}
    return bool(a) and len(a - b) / len(a) > 0.4


def _line_regions(lines: list[local_ocr.OcrLine]) -> list[tuple[int, int, tuple[int, int, int, int], None, None]]:
    """Where each OCR line sits, by its character range in the lines joined with newlines (OcrResult.text)."""
    out, pos = [], 0
    for ln in lines:
        out.append((pos, pos + len(ln.text), ln.box, None, None))
        pos += len(ln.text) + 1
    return out


def _within(line: tuple[int, int, int, int], art: tuple[int, int, int, int], share: float = 0.6) -> bool:
    """Whether most of an OCR line's box lies inside a piece of artwork's box."""
    w = max(0, min(line[2], art[2]) - max(line[0], art[0]))
    h = max(0, min(line[3], art[3]) - max(line[1], art[1]))
    area = max(1, (line[2] - line[0]) * (line[3] - line[1]))
    return w * h / area >= share


def _drop_artwork_lettering(run: ReviewRun, source_id: str,
                            art_at: Callable[[float | None, float | None], list[tuple[int, int, int, int]]]) -> None:
    """Drop casing findings for lettering that is part of matched official artwork.

    A logo's own lettering ("KITEPATH" in capitals, a wordmark set in lowercase) is read by OCR like any
    text, and the casing rule then judges artwork as if someone had typed it. The asset checks own that
    artwork: if it differs from the approved version they say so, and if it matches it is correct as drawn.
    `art_at` gives the matched artwork boxes for a line's time span (None, None for a still image)."""
    src = next((s for s in run.sources if s.id == source_id), None)
    codes = {r.code for r in run.base.rules if r.pattern.get("type") == "casing"}
    if src is None or not src.regions or not codes:
        return

    def on_artwork(at: int) -> bool:
        return any(a <= at < b and any(_within(box, art) for art in art_at(t0, t1))
                   for a, b, box, t0, t1 in src.regions)

    run.drop([f for f in run.findings if f.source == source_id and f.rule_code in codes
              and f.span_start is not None and on_artwork(f.span_start)])


def _changed_areas(cells: list[dict]) -> str:
    """Grid cells that differ, said the way a reviewer would: "the colour differs at the top left and
    centre, the shape at the bottom right". The artwork is compared on a grid; its cell names (r3c4)
    mean nothing to a person looking at a poster."""
    def where(c: dict) -> str:
        third = lambda i: min(2, i * 3 // asset_match.GRID)  # noqa: E731
        row, col = ("top", "middle", "bottom")[third(c["row"])], ("left", "centre", "right")[third(c["col"])]
        return "centre" if (row, col) == ("middle", "centre") else f"{row} {col}" if row != "middle" else f"{col}"
    parts = []
    for change in ("colour", "shape"):
        spots = list(dict.fromkeys(where(c) for c in cells if c.get("change") == change))
        if spots:
            places = ", ".join(spots[:-1]) + (" and " if len(spots) > 1 else "") + spots[-1]
            parts.append(f"the {change} at the {places}" if parts else f"the {change} differs at the {places}")
    return ", and ".join(parts) or "parts of it differ"


def _palette_swap(swap: list[tuple[str, str]]) -> str:
    """The recolouring in words: the shape is the official one, so what a reader needs is which colours moved."""
    pairs = ", ".join(f"{old} is now {new}" for old, new in swap[:3])
    return f" The outline matches, but the palette was swapped ({pairs})."


def _official_boxes(run: ReviewRun, matches: list[asset_match.AssetMatch]) -> list[tuple[int, int, int, int]]:
    official = {a.id for a in run.assets if a.official}
    return [m.box for m in matches if m.found and m.box and m.asset_id in official]


def _asset_findings(run: ReviewRun, node: AgentNode, image_id: str, locator: dict[str, Any],
                    matches: list[asset_match.AssetMatch], scene: SceneReport | None,
                    lines: list[local_ocr.OcrLine] | None = None) -> None:
    run.add(node, "assets", [f for _, f in _judge_assets(run, image_id, locator, matches, scene, lines)])


def _judge_assets(run: ReviewRun, image_id: str, locator: dict[str, Any],
                  matches: list[asset_match.AssetMatch], scene: SceneReport | None,
                  lines: list[local_ocr.OcrLine] | None = None) -> list[tuple[int, RawFinding]]:
    """Fuse pixel evidence and the vision verdict, official artwork first, as (asset id, finding).

    Pixel findings stand on their own. A vision-only finding is a model
    opinion: it is reported, but it can never block publication by itself.
    """
    verdicts = {}
    if scene:
        shown = _shareable(run)[:MAX_VISION_REFERENCES]
        verdicts = {shown[v.reference - 1].id: v for v in scene.assets if 0 < v.reference <= len(shown)}
    vision_name = run.vision.name
    out: list[tuple[int, RawFinding]] = []
    cur = 0  # the asset being judged
    by_id = {m.asset_id: m for m in matches}

    def finding(code: str, title: str, why: str, confidence: float, box=None, model=None) -> None:
        rule = run.rule_by_code.get(code)
        if rule is None:
            return
        out.append((cur, RawFinding(
            unit_id=image_id, category=rule.category, title=title, explanation=f"{rule.text} {why}".strip(),
            confidence=round(min(1.0, confidence), 4), checker="assets", rule_code=rule.code, source=image_id,
            locator={**locator, "image": image_id, **({"box": list(box)} if box else {})}, model=model,
        )))

    # An old version shares most of its keypoints with the current artwork, so both can match the same
    # spot. Where a retired version fits better there, the image shows the old one: report that, not the
    # current artwork as "altered" into it.
    stale = [(by_id[a.id], a) for a in run.assets if a.retired and by_id.get(a.id) and by_id[a.id].found]
    current = [by_id[a.id] for a in run.assets if a.official and by_id.get(a.id) and by_id[a.id].found]

    found_matches = [(by_id[a.id], a) for a in run.assets if by_id.get(a.id) and by_id[a.id].found]

    def explained(m: asset_match.AssetMatch, restricted: bool) -> bool:
        # A leak is a must; artwork above the content's tier is explained away only by public artwork
        # fitting far better there, never by other restricted artwork.
        if restricted:
            return _explained(m, [o for o, a in found_matches if o is not m and not a.restricted],
                              lead=RESTRICTED_EXPLAINED_LEAD)
        return _explained(m, [o for o, _ in found_matches if o is not m])

    def superseded(m: asset_match.AssetMatch) -> bool:
        return any(_iou(m.box, old.box) >= 0.5 and (old.similarity or 0) > (m.similarity or 0) for old, _ in stale)

    def outdated(old: asset_match.AssetMatch) -> bool:
        """The retired version is what's there, not the current one matching it nearly as well: two
        versions that differ in a detail both match either, and only a clear lead says which it is."""
        return not any(_iou(old.box, m.box) >= 0.5 and (m.similarity or 0) >= (old.similarity or 0) - RETIRED_LEAD
                       for m in current)

    for asset in run.assets:
        cur = asset.id
        m = by_id.get(asset.id)
        v = verdicts.get(asset.id)
        found = bool(m and m.found)
        label = f"official {asset.kind} '{asset.name}'"

        # Another registered artwork is what's there and this one only shares parts with it: nothing
        # judged from this match's pixels is reported. Lettering read by OCR is judged on its own.
        exp = found and explained(m, asset.restricted)
        if not asset.official:
            # Old versions and other brands' marks are not unreleased artwork, whatever their tier; above
            # the content's tier they are reported by number, like anything else the reader can't see.
            name = f"asset #{asset.id}" if asset.restricted else asset.name
            if exp:
                continue
            if found and asset.kind == "competitor":
                finding("VIS-COMPETITOR-MARK", f"{name} appears in this image" if not asset.restricted
                        else "Another brand's registered mark appears in this image",
                        f"The pixels match the registered mark of {name}, another brand.", 0.9, m.box)
            elif found and outdated(m):
                finding("VIS-ASSET-RETIRED", f"Old version of the artwork: {name}",
                        f"This image uses {name}, a version the brand has retired.", 0.9, m.box)
            continue
        if found and not asset.restricted and superseded(m):
            continue

        if asset.restricted and found and not exp:
            # Unreleased artwork in lower-tier content is a leak, whatever its quality.
            rule = run.rule_by_code.get("CONF-LEAK")
            if rule:
                # Generic on purpose: anyone who can read this content can read
                # the finding, and the asset's name may itself be a codename.
                out.append((asset.id, RawFinding(
                    unit_id=image_id, category=rule.category, title="Unreleased brand artwork",
                    explanation=f"This image contains official artwork restricted above this content's tier "
                                f"(asset #{asset.id}; an approver can see which). {rule.text}", confidence=1.0,
                    checker="assets", rule_code=rule.code, source=image_id,
                    locator={**locator, "image": image_id, "box": list(m.box or [])},
                )))
            continue
        if asset.restricted:
            continue

        if found and not exp and m.distortions:
            finding("VIS-ASSET-DISTORTED", f"{asset.name} is {m.distortions[0].split(':')[0]}",
                    f"Compared with {label}, this copy is {'; '.join(m.distortions)}.", 0.9, m.box)

        if found and not exp and m.altered:
            extra = f" The vision model also notes: {'; '.join(v.changes[:3])}." if v and v.changes else ""
            recoloured = m.by_shape and m.palette_swap
            finding("VIS-ASSET-ALTERED",
                    f"{asset.name} is in changed colours" if recoloured
                    else f"{asset.name} differs from the official artwork",
                    f"Compared with {label}, {_changed_areas(m.altered_cells)} (marked on the image)."
                    f"{_palette_swap(m.palette_swap) if recoloured else ''}{extra}", 0.9, m.box)

        elif found and not exp and v and v.present == "altered" and v.changes and v.confidence >= 0.7:
            finding("VIS-ASSET-ALTERED", f"{asset.name} may differ from the official artwork",
                    f"The pixels match {label}, and the vision model notes: {'; '.join(v.changes[:3])}.",
                    0.6 * v.confidence, m.box, model=vision_name)

        attached = (found and not exp and asset.part in _EXTENDABLE_PARTS
                    and (m.attached_ratio or 0) >= asset_match.ATTACHED_RATIO)
        vision_extra = bool(v and v.extra_parts and v.present in ("exact", "altered") and v.confidence >= 0.5)
        if attached or (vision_extra and (found or asset.part in _EXTENDABLE_PARTS)):
            parts = ", ".join(v.extra_parts) if v and v.extra_parts else "parts joined to it"
            both = attached and vision_extra
            finding("VIS-ASSET-EXTENDED", f"Unapproved additions to {asset.name}: {parts}",
                    f"The brand has approved {label} as {asset.part} only; this image adds {parts}.",
                    0.95 if both else 0.85 if attached else 0.85 * (v.confidence if v else 0.5),
                    m.box if found else None, model=None if attached else vision_name)

        if asset.wordmark and lines:
            near = [ln for ln in lines if not found or _overlaps(ln.box, m.box, pad=0.35)]
            bad = _misspelled(asset.wordmark, near)
            if bad:
                finding("VIS-ASSET-ALTERED", f"Wordmark misspelled: '{bad}' instead of '{asset.wordmark}'",
                        f"Text in the image reads '{bad}' where {label} spells '{asset.wordmark}'. Logo generators "
                        "often garble lettering.", 0.9, m.box if found else None)

        if not found and v and v.present in ("imitation", "altered", "exact") and v.confidence >= 0.6:
            what = "an imitation of" if v.present == "imitation" else "a redrawn version of"
            finding("VIS-ASSET-IMITATION", f"Looks like {what} {asset.name}",
                    f"The vision model sees {what} {label} that does not match the official artwork"
                    + (f" ({'; '.join(v.changes[:3])})." if v.changes else "."),
                    0.75 * v.confidence, model=vision_name)
    return out


# --- documents ---------------------------------------------------------------------------------------

def _first_up(s: str) -> str:
    return s[:1].upper() + s[1:]  # "sheet Prices" -> "Sheet Prices", keeping the sheet's own name


_DOCUMENT_READERS = {
    "application/pdf": extract_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": extract_docx,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": extract_pptx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": extract_xlsx,
    "text/html": extract_html,
}


async def document_agent(run: ReviewRun, node: AgentNode, doc: dict[str, Any]) -> None:
    raw = run.payload(doc, MAX_DOC_BYTES)
    kind = sniff(raw)
    doc_id = str(doc.get("id"))
    reader = _DOCUMENT_READERS.get(kind)
    if reader is None:
        raise MediaError(f"{doc_id} is not a PDF, Word, PowerPoint, Excel or HTML file (looks like {kind})")
    extracted = await run.blocking(reader, raw)
    node.detail = {"kind": extracted.kind, "pages": extracted.page_count, "notes": extracted.notes}
    # A page with a text layer and one image needs about a dozen agents.
    run.tree.grow(12 * len(extracted.pages))
    run.notes.extend(f"{doc_id}: {n}" for n in extracted.notes)
    if extracted.partial:
        run.partial |= MEDIA_COVERS
    await asyncio.gather(*(
        run.tree.spawn(node, "page", _first_up(page.label or f"page {page.number}"),
                       lambda n, page=page: page_agent(run, n, doc_id, page,
                                                                                               extracted.kind))
        for page in extracted.pages
    ))


async def page_agent(run: ReviewRun, node: AgentNode, doc_id: str, page, kind: str) -> None:
    base = f"doc:{doc_id}:p{page.number}"
    locator = {"document": doc_id, "page": page.number} | ({"label": page.label} if page.label else {})
    node.detail = {"scanned": page.scanned, "images": len(page.images), "text_chars": len(page.text)}
    work = []
    # A web page's pictures go through the same alt-text rule as a post's images.
    pictures = {"images": page.alts} if page.alts else None
    if page.text.strip() or pictures:
        src = Source(f"{base}:text", f"{kind}_text", page.text, "pdf-text-layer" if kind == "pdf" else kind, 1.0,
                     locator, parent=doc_id)
        work.append(run.tree.spawn(node, "text", "Text layer",
                                   lambda n: text_agent(run, n, src, attachments=pictures)))
    # Renders and images stay compressed until here, and decode off the loop.
    if page.scanned and page.render_jpeg is not None:
        async def scan(n: AgentNode) -> None:
            render = await run.blocking(lambda: page.render)
            await image_agent(run, n, render, f"{base}:scan", locator, context=page.text, scanned=True)

        work.append(run.tree.spawn(node, "image", "Scanned page (no text layer)", scan))

    async def embedded(n: AgentNode, img) -> None:
        pil = await run.blocking(lambda: img.image)
        await image_agent(run, n, pil, f"{base}:img{img.index}", locator, context=page.text)

    for img in page.images:
        work.append(run.tree.spawn(node, "image", f"Embedded image {img.index}",
                                   lambda n, img=img: embedded(n, img)))
    if page.graphics_jpeg is not None:
        work.append(run.tree.spawn(node, "ocr", "Text drawn as shapes",
                                   lambda n: _drawn_text(run, n, page, base, locator, doc_id)))
    await asyncio.gather(*work)


async def _drawn_text(run: ReviewRun, node: AgentNode, page, base: str, locator: dict[str, Any], doc_id: str) -> None:
    """Read the rendered page and check what it shows that the text layer doesn't: text converted to
    outlines, or lettering drawn as artwork. Lines the layer already has were checked as text."""
    render = await run.blocking(lambda: Image.open(io.BytesIO(page.graphics_jpeg)).convert("RGB"))
    result = await run.blocking(local_ocr.read, render)
    known = set(_WORDS.findall(page.text.lower()))
    # A chart's tick labels or a map's squiggles read as low-confidence noise, not text someone drew.
    drawn = [ln for ln in result.lines if ln.confidence >= DRAWN_MIN_CONFIDENCE and _drawn_only(ln.text, known)]
    node.detail = {"lines_read": len(result.lines), "only_drawn": len(drawn)}
    # Lettering in a script OCR can't read is only in the drawing when the text layer has no such script
    # either; Hindi in the layer was checked as text already.
    if result.foreign and not any("\u0900" <= ch <= "\u0dff" for ch in page.text):
        node.detail["unreadable_script_lines"] = len(result.foreign)
        _unreadable(run, node, f"{base}:drawn", locator,
                    "drawn lettering in a script local OCR cannot read (likely Devanagari or another Indic script)")
    if not drawn:
        return
    text = "\n".join(ln.text for ln in drawn)
    confidence = sum(ln.confidence for ln in drawn) / len(drawn)
    src = Source(f"{base}:drawn", "ocr", text, "ocr:page-render", confidence, {**locator, "image": f"{base}:drawn"},
                 parent=doc_id)
    run.glance.append(f"page {page.number} of {doc_id} has text drawn as shapes, not in its text layer")
    await run.tree.spawn(node, "text", "Text found only in the drawing", lambda n: text_agent(run, n, src))


# A match is explained by another when this share of its evidence lies inside the other's match and the
# other fits clearly better there. Brand libraries nest their artwork: the logo lockup holds the icon's
# emblem and the wordmark's lettering, the pack front holds the logo. A post showing the logo then partly
# matches the pack and the icon, and without this each was reported as an altered copy (83% false alarms
# on correct use in evals/assets).
EXPLAINED_SHARE = 0.7
EXPLAINED_LEAD = 0.03
RESTRICTED_EXPLAINED_LEAD = 0.1


def _explained(m: asset_match.AssetMatch, others: list[asset_match.AssetMatch],
               lead: float = EXPLAINED_LEAD) -> bool:
    core = m.core or m.box
    if core is None:
        return False
    area = max(1, (core[2] - core[0]) * (core[3] - core[1]))
    for o in others:
        if o.box is None:
            continue
        w = max(0, min(core[2], o.box[2]) - max(core[0], o.box[0]))
        h = max(0, min(core[3], o.box[3]) - max(core[1], o.box[1]))
        if w * h / area >= EXPLAINED_SHARE and (o.similarity or 0) > (m.similarity or 0) + lead:
            return True
    return False


def _iou(a: tuple[int, int, int, int] | None, b: tuple[int, int, int, int] | None) -> float:
    if a is None or b is None:
        return 0.0
    w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h
    return w * h / union if union > 0 else 0.0


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int] | None, pad: float = 0.0) -> bool:
    if b is None:
        return True
    w, h = b[2] - b[0], b[3] - b[1]
    bx0, by0, bx1, by1 = b[0] - w * pad, b[1] - h * pad, b[2] + w * pad, b[3] + h * pad
    return a[0] < bx1 and bx0 < a[2] and a[1] < by1 and by0 < a[3]


def _misspelled(wordmark: str, lines: list[local_ocr.OcrLine]) -> str | None:
    """A token close to the wordmark but not it ("Inkl00m" for "Inkloom"), or None.

    Exact matches pass (case aside: casing is the casing rule's job), and
    tokens that are nothing like it are ignored, so ordinary words nearby
    don't trip it.
    """
    import difflib

    target = wordmark.casefold()
    n = len(target.split())
    for line in lines:
        words = line.text.split()
        for i in range(len(words)):
            cand = " ".join(words[i:i + n]).strip(".,!?:;\"'()")
            c = cand.casefold()
            # The wordmark used as a hashtag, a handle, a possessive or a plural is spelled right.
            if not c or c == target or target in _brand_forms(c):
                continue
            # Digits and look-alike letters standing in for the real ones
            # ("Inkl00m", "Nlke", "Arnazon") are the commonest garble, in
            # generated logos and in impersonation alike.
            if _shape(c) == _shape(target):
                return cand
            # Short wordmarks are a letter away from ordinary words ("Nike" and
            # "Mike", "Acme" and "Acne"), so they need a much closer match.
            floor = 0.75 if len(target) >= 8 else 0.86
            if difflib.SequenceMatcher(None, c.translate(_DIGIT_LETTERS), target).ratio() >= floor \
                    and abs(len(c) - len(target)) <= (3 if len(target) >= 8 else 1) or _transposed(c, target):
                return cand
    return None


def _brand_forms(token: str) -> set[str]:
    """What a token could be the wordmark of: itself without a #/@ prefix, and that without a possessive
    or plural ending. Every reading is kept, so "nikes" offers both "nike" and "nik"."""
    bare = token[1:] if token[:1] in "#@" else token
    return {bare} | {bare[:-len(end)] for end in ("'s", "\u2019s", "'", "\u2019", "es", "s") if bare.endswith(end)}


def _transposed(a: str, b: str) -> bool:
    """Two adjacent letters swapped ("Inkolom"), a common lettering garble."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]


def _shape(text: str) -> str:
    """Text reduced to how it looks: look-alike letters and digits collapse to one form."""
    text = text.translate(_DIGIT_LETTERS).replace("rn", "m").replace("vv", "w").replace("cl", "d")
    return text.replace("i", "l").replace("!", "l")


_DIGIT_LETTERS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a",
                                "$": "s", "|": "l"})


# The matcher costs about 0.9 s a frame with six assets (evals/results/assets.md): a base cost for the
# frame's features plus a share per asset. A video may spend this share of the media deadline matching.
MATCH_BUDGET_SHARE = 0.5
MATCH_FRAME_BASE_S, MATCH_FRAME_PER_ASSET_S = 0.3, 0.1
MAX_MATCH_FRAMES = 60


async def _match_video_frames(run: ReviewRun, node: AgentNode, video_id: str,
                              keys: list[tuple[float, Image.Image]],
                              samples: list[tuple[float, Image.Image]]) -> dict[float, list[asset_match.AssetMatch]]:
    """Official artwork matches for each sampled frame the time budget allows, by frame time.

    Frames not matched (over the cap, over the time budget, or a decode that timed out) are reported as
    partial visual coverage in a note: an overlay in one of them would be missed, so it is never a pass.
    They are also kept, with no matches, so a defect seen either side of an unchecked frame is two
    findings rather than one range that claims the gap was checked."""
    from verytas.media import video as video_media

    per_asset = MATCH_FRAME_BASE_S + MATCH_FRAME_PER_ASSET_S * len(run.assets)
    budget = run.media_timeout_s * MATCH_BUDGET_SHARE
    cap = max(len(keys), min(MAX_MATCH_FRAMES, int(budget / per_asset)))
    frames_, left_out = video_media.match_frames(keys, samples, cap)
    deadline = time.monotonic() + budget
    # Shot starts first, then the rest in time order: if time runs out, what goes unmatched is mid-shot
    # samples spread over the clip, not every frame after some point.
    key_times = {t for t, _ in keys}
    ordered = [f for f in frames_ if f[0] in key_times] + [f for f in frames_ if f[0] not in key_times]
    matched: dict[float, list[asset_match.AssetMatch]] = {}
    unmatched = list(left_out)
    for t, img in ordered:
        if time.monotonic() > deadline:
            unmatched.append(t)
            continue
        try:
            feats = await run.blocking(asset_match.scene_features, img)
            matched[t] = list(await asyncio.gather(*(run.blocking(asset_match.match, a.prepared, feats)
                                                     for a in run.assets)))
        except TimeoutError:
            unmatched.append(t)
    skipped = len(unmatched)
    node.detail.update(frames_matched=len(matched), frames_not_matched=skipped)
    if skipped:
        run.notes.append(f"{video_id}: official artwork was matched in {len(matched)} of "
                         f"{len(matched) + skipped} distinct frames, so a brief mark could be missed")
        run.partial.add("visual")
    return {**matched, **dict.fromkeys(unmatched, [])}


def _frame_findings(run: ReviewRun, video_id: str, locator: dict[str, Any],
                    per_frame: dict[float, list[asset_match.AssetMatch]]) -> list[RawFinding]:
    """Each frame's matches judged together, as one image, then merged over time."""
    return _merge_over_time([(t, _judge_assets(run, video_id, {**locator, "time": [t, t]}, found, None))
                             for t, found in sorted(per_frame.items())])


def _merge_over_time(per_frame: list[tuple[float, list[tuple[int, RawFinding]]]]) -> list[RawFinding]:
    """One finding per run of consecutive matched frames showing the same defect of the same artwork,
    with the time range it spans. A frame without it ends the run, so the same mark shown at 6 s and
    again at 40 s is two findings, as with redrawn mascots."""
    done: list[RawFinding] = []
    live: dict[tuple, tuple[RawFinding, float, float]] = {}
    for t, found in per_frame:
        seen: set[tuple] = set()
        for aid, f in found:
            key = (f.rule_code, aid, f.title)
            if key in seen:
                continue
            seen.add(key)
            if key in live:
                best, t0, _ = live[key]
                live[key] = (f if f.confidence > best.confidence else best, t0, t)
            else:
                live[key] = (f, t, t)
        for key in [k for k in live if k not in seen]:
            done.append(_stamp(*live.pop(key)))
    done.extend(_stamp(*v) for v in live.values())
    return sorted(done, key=lambda f: (f.locator or {}).get("time", [0.0])[0])


# Pixel differences seen in one sampled frame only. On evals/video they were 44 of 89 false alarms and 2 of
# 32 real catches: a compressed or moving frame looks "altered" for an instant, a real change stays on
# screen. So they stay in the review, at advisory, saying why. Retired, competitor and distorted artwork
# are kept at full weight from one frame: those were most of the real catches of brief appearances.
_ONE_FRAME_ADVISORY = {"VIS-ASSET-ALTERED", "VIS-ASSET-EXTENDED"}


def _stamp(f: RawFinding, t0: float, t1: float) -> RawFinding:
    f.locator = {**(f.locator or {}), "time": [t0, t1]}
    if t1 - t0 < 1e-6 and f.rule_code in _ONE_FRAME_ADVISORY:
        f.level_cap = "advisory"
        f.explanation = (f"{f.explanation} Seen in one sampled frame only, so it may be a compression or motion "
                         "artefact; check that moment.")
    return f


# --- video ---------------------------------------------------------------------------------------

async def video_agent(run: ReviewRun, node: AgentNode, vid: dict[str, Any]) -> None:
    from verytas.media import video

    raw = run.payload(vid, 150 * 1024 * 1024)
    if not sniff(raw).startswith("video/"):
        raise MediaError("attachment is not a video")
    video_id = f"vid:{vid.get('id')}"
    meta = await run.blocking(video.probe, raw)
    node.detail = {**meta, "checked_seconds": min(meta["duration"], run.video_max_seconds)}
    if meta["duration"] > run.video_max_seconds:
        run.notes.append(f"{video_id}: only the first {run.video_max_seconds // 60} minutes were checked")
    every = video.sample_every(meta["duration"], run.video_max_seconds)
    samples = await run.blocking(video.frames, raw, max_seconds=run.video_max_seconds, every_s=every)
    node.detail.update(frames_sampled=len(samples), sample_every_s=round(every, 2))
    if every > video.SAMPLE_EVERY_S:
        run.notes.append(f"{video_id}: long video, frames sampled every {every:.1f} s instead of every second")
        run.partial.add("visual")
    locator = {"video": video_id}
    matched_frames: dict[float, list[asset_match.AssetMatch]] = {}
    signals: dict[str, Any] = {"speech": False, "burned_in": False, "track": False, "music_only": False}

    async def captions(n: AgentNode) -> None:
        unread = [0]

        def read(img: Image.Image) -> local_ocr.OcrResult:
            result = local_ocr.read(img)
            unread[0] += len(result.foreign)
            return result

        cues, passes, cut_at = await run.blocking(video.caption_cues, samples, read)
        n.detail = {"ocr_passes": passes, "cues": len(cues), "read_until_s": cut_at}
        if unread[0]:
            n.detail["unreadable_script_lines"] = unread[0]
            _unreadable(run, n, video_id, locator,
                        "on-screen text in a script local OCR cannot read (likely Devanagari or another Indic script)")
        if cut_at is not None:
            n.status, n.note = "not_checked", f"on-screen text read only up to {cut_at:.0f} s (OCR budget reached)"
        if samples:
            run.layouts[video_id] = {"size": samples[0][1].size, "video": True,
                                     "lines": [(c.text, c.box) for c in cues if c.box], "assets": []}
        if cues:
            signals["burned_in"] = True
            text, timeline = video.cue_text(cues)
            conf = sum(c.confidence for c in cues) / len(cues)
            src = Source(f"{video_id}:captions", "captions", text, "ocr:frames", conf, locator, video_id, timeline,
                         regions=video.cue_regions(cues))
            await run.tree.spawn(n, "text", "Burned-in captions and on-screen text", lambda c: text_agent(run, c, src))

    async def subtitles(n: AgentNode) -> None:
        cues = await run.blocking(video.subtitle_cues, raw)
        n.detail = {"cues": len(cues)}
        if cues:
            signals["track"] = True
            text, timeline = video.cue_text(cues)
            src = Source(f"{video_id}:subtitles", "subtitles", text, "subtitle-track", 1.0, locator, video_id,
                         timeline)
            await run.tree.spawn(n, "text", "Subtitle track", lambda c: text_agent(run, c, src))

    async def speech(n: AgentNode) -> None:
        pcm = await run.blocking(video.audio_pcm, raw, max_seconds=run.video_max_seconds)
        if pcm is None:
            n.note = "no audio"
            return
        model = run.asr_for(pcm)
        cues, language, prob = await run.blocking(video.transcribe, pcm, model, run.asr_vocabulary)
        level = video.loudness(pcm)
        n.detail = {"segments": len(cues), "language": language, "language_probability": round(prob, 2),
                    "loudness_dbfs": level, "model": f"whisper-{model} (local)"}
        if not cues:
            signals["music_only"] = bool(level > -45)
            n.note = "no speech: music or ambient sound only" if level > -45 else "silent"
            return
        signals["speech"] = True
        # Prices and percentages said in Hindi come back as words; write them as digits so the claim checks
        # and the evidence board can read them. Per cue, so the time map stays exact.
        cues = await run.blocking(lambda: [dataclasses.replace(c, text=phonetic.write_figures(c.text)) for c in cues])
        text, timeline = video.cue_text(cues)
        conf = sum(c.confidence for c in cues) / len(cues)
        src = Source(f"{video_id}:speech", "speech", text, f"asr:whisper-{model}", conf,
                     {**locator, "language": language}, video_id, timeline)
        await run.tree.spawn(n, "text", "What is said", lambda c: text_agent(run, c, src))

    async def visuals(n: AgentNode) -> None:
        keys = await run.blocking(video.keyframes, samples)
        n.detail = {"keyframes": [t for t, _ in keys]}
        if run.people is not None:
            for t, img in keys:
                await run.tree.spawn(n, "faces", f"Identify faces at {t:.1f}s",
                                     lambda c, img=img, t=t: faces_agent(run, c, img, video_id,
                                                                         {**locator, "time": [t, t]}))
        # Matches per frame: a frame is judged on its own, because artwork on screen at different times
        # is not in one picture (a rival's mark at 6 s is not "explained" by the logo shown at 3 s).
        per_frame: dict[float, list[asset_match.AssetMatch]] = {}
        if run.assets:
            per_frame = await _match_video_frames(run, n, video_id, keys, samples)
        matched_frames.update(per_frame)
        best: dict[int, tuple[asset_match.AssetMatch, float]] = {}
        for t, found in per_frame.items():
            for m in found:
                if m.found and (m.asset_id not in best or m.inliers > best[m.asset_id][0].inliers):
                    best[m.asset_id] = (m, t)
        scene = None
        if run.allow_cloud_vision and keys:
            # Burned-in text is blacked out on each frame from its own full-size
            # OCR before tiling: shrunk into a sheet cell, a caption is too small
            # to read reliably. The sheet is then read again as a second pass.
            patterns = run.leak_patterns()

            def build_sheet():
                frames_ = [(t, pixels.redact(img, local_ocr.read(img), patterns)[0]) for t, img in keys]
                sheet_ = video.contact_sheet(frames_)
                return sheet_, local_ocr.read(sheet_)

            sheet, sheet_ocr = await run.blocking(build_sheet)
            scene = await run.tree.spawn(n, "scene", "Describe keyframes and compare assets",
                                         lambda c: scene_agent(run, c, sheet, video_id, sheet_ocr,
                                                               "Contact sheet of frames from a video, times shown. "
                                                               + run.base.body[:1000]))
        if any(a.kind == "mascot" for a in run.assets):
            frames = pick_frames(keys, samples)
            await run.tree.spawn(n, "characters", "Look for redrawn mascots",
                                 lambda c: characters_agent(run, c, frames, video_id, locator, set(best)))
        out = _frame_findings(run, video_id, locator, per_frame)
        if scene:
            # The vision model saw one contact sheet, so its verdicts are not tied to a frame: they are
            # judged against each artwork's best match, and only what the model itself said is taken
            # from this pass (the pixel findings are the per-frame ones above).
            for aid, f in _judge_assets(run, video_id, locator, [m for m, _ in best.values()], scene):
                if f.model is not None:
                    if aid in best:
                        f.locator = {**(f.locator or {}), "time": [best[aid][1]] * 2}
                    out.append(f)
        run.add(n, "assets", out)

    await asyncio.gather(
        run.tree.spawn(node, "captions", "Read burned-in captions", captions),
        run.tree.spawn(node, "subtitles", "Read subtitle tracks", subtitles) if meta["subtitle_streams"]
        else asyncio.sleep(0),
        run.tree.spawn(node, "speech", "Transcribe speech (local)", speech) if meta["has_audio"]
        else asyncio.sleep(0),
        run.tree.spawn(node, "keyframes", "Check keyframes", visuals),
    )
    node.detail["signals"] = signals
    # Burned-in text is read before the artwork is matched, and the two run side by side, so lettering that
    # belongs to a matched logo is set aside now that both are known.
    _drop_artwork_lettering(run, f"{video_id}:captions", lambda t0, t1: [
        box for t, found in matched_frames.items() if t0 is None or t0 - 1e-6 <= t <= (t1 or t0)
        for box in _official_boxes(run, found)])
    _caption_findings(run, node, video_id, locator, signals)


def _caption_findings(run: ReviewRun, node: AgentNode, video_id: str, locator: dict[str, Any],
                      s: dict[str, Any]) -> None:
    rule = run.rule_by_code.get("A11Y-CAPTIONS")
    if rule is None or not s["speech"] or s["track"]:
        return
    if s["burned_in"]:
        title, why, conf = ("Captions are burned in only", "Add a caption file or transcript as well.", 0.7)
    else:
        title, why, conf = ("Speech has no captions", "Add captions for the spoken part.", 0.9)
    run.add(node, "media", [RawFinding(
        unit_id=video_id, category=rule.category, title=title, explanation=f"{rule.text} {why}", confidence=conf,
        checker="media", rule_code=rule.code, source=video_id, locator=dict(locator),
    )])


# --- intake and disclosure ---------------------------------------------------------------------

_AI_LABEL = re.compile(
    r"#(?:ai|aiart|aigenerated|madewithai|generatedwithai|aigen)\b|\bai[- ]generated\b|\bmade (?:with|using) ai\b"
    r"|\bcreated (?:with|using) ai\b|\bai[- ]assisted\b|\bsynthetic (?:image|video|media)\b", re.IGNORECASE)


async def policy_agent(run: ReviewRun, node: AgentNode) -> None:
    """Findings about the submission as a whole: irregular intake and AI labelling."""
    out: list[RawFinding] = []
    rule = run.rule_by_code.get("INPUT-IRREGULAR")
    for irr in (run.profile or {}).get("irregularities", []):
        if rule is None:
            break
        out.append(RawFinding(
            unit_id="intake", category=rule.category, title=f"Irregular {irr['subject']}: {irr['value']}",
            explanation=f"Expected {irr['expected']}; {irr['why']}. The creator gave a reason, shown with the "
                        f"submission. {rule.text}",
            confidence=0.95 if irr.get("over_limit") else 0.8, checker="intake", rule_code=rule.code,
            locator={"intake": irr["code"]},
        ))

    disclosure = run.rule_by_code.get("AI-DISCLOSURE")
    labelled = any(_AI_LABEL.search(s.text) for s in run.sources if s.id == "body" or s.kind in ("captions",
                                                                                                  "subtitles"))
    likely = max((s.get("ai_generated") or 0.0 for s in run.scenes.values()), default=0.0)
    if disclosure and not labelled and (run.declared_ai or likely >= 0.7):
        if run.declared_ai:
            out.append(RawFinding(
                unit_id="disclosure", category=disclosure.category, title="AI-made content without an AI label",
                explanation=f"The creator says generative AI was used, and the caption has no label such as "
                            f"'AI-generated' or #MadeWithAI. {disclosure.text}",
                confidence=0.9, checker="intake", rule_code=disclosure.code,
            ))
        else:
            out.append(RawFinding(
                unit_id="disclosure", category=disclosure.category, title="Looks AI-generated, with no AI label",
                explanation=f"The vision model sees signs of AI generation ({likely:.0%}). If AI was used, label "
                            f"it. {disclosure.text}",
                confidence=round(0.8 * likely, 4), checker="intake", rule_code=disclosure.code,
                model=run.vision.name,
            ))
    node.detail = {"irregularities": len((run.profile or {}).get("irregularities", [])), "ai_label": labelled,
                   "declared_ai": run.declared_ai, "ai_likelihood": round(likely, 2)}
    run.add(node, "intake", out)
