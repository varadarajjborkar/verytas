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
import itertools
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from PIL import Image

from verytas.checks.base import CheckContext, RawFinding, RuleView, Source
from verytas.checks.claims import check_claims
from verytas.checks.deterministic import run_deterministic
from verytas.checks.semantic import check_semantic
from verytas.ingest.segment import image_units, segment
from verytas.media import assets as asset_match
from verytas.media import ocr as local_ocr
from verytas.media import pixels
from verytas.media.documents import extract_docx, extract_pdf
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
from verytas.prism.governor import Governor, TaskOutcome
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
    asr_model: str = "base"
    video_max_seconds: int = 900
    media_timeout_s: float = 180.0
    rule_thresholds: dict[str, float] = field(default_factory=dict)
    # Where text and logos sit in each attached image or video frame, for the
    # presentation agent's crop and safe-zone checks, and the "at a glance" view.
    layouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    glance: list[str] = field(default_factory=list)
    # The caption is longer than the channel shows before "...more", so the first screen can read differently.
    caption_folded: bool = False
    sources: list[Source] = field(default_factory=list)
    findings: list[RawFinding] = field(default_factory=list)
    outcomes: list[TaskOutcome] = field(default_factory=list)
    rule_problems: list[tuple[str, str, str]] = field(default_factory=list)
    scenes: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Categories read only in part (sampled, truncated): reported as degraded, with a note.
    partial: set[str] = field(default_factory=set)
    worker_of: dict[int, str] = field(default_factory=dict)

    def add(self, node: AgentNode, worker: str, found: list[RawFinding]) -> None:
        for f in found:
            self.worker_of[id(f)] = worker
        self.findings.extend(found)
        node.findings += len(found)

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

    await run.tree.spawn(root, "presentation", "How it looks on the platform", lambda n: presentation_agent(run, n),
                         essential=True)
    await run.tree.spawn(root, "policy", "Intake and disclosure", lambda n: policy_agent(run, n), essential=True)


# --- text ---------------------------------------------------------------------------------------------

async def text_agent(run: ReviewRun, node: AgentNode, source: Source) -> None:
    """The three text workers on one source, as child agents."""
    run.sources.append(source)
    node.detail = {"source": source.id, "route": source.route, "chars": len(source.text),
                   "confidence": round(source.confidence, 3)}
    if not source.text.strip():
        node.note = "no text"
        return
    is_body = source.id == "body"
    ctx = run.base if is_body else CheckContext(
        body=source.text, units=segment(source.text), rules=run.base.rules, facts=run.base.facts,
        terms=run.base.terms, attachments={}, channel=run.base.channel, today=run.base.today,
        profile=run.base.profile, whole_post=False,
    )
    if is_body:
        ctx.units = segment(source.text) + image_units(run.base.attachments)

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
        worker("semantic judge", lambda: check_semantic(ctx, run.judge, threshold=run.semantic_threshold,
                                                        per_rule=run.rule_thresholds)),
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
    if image_id in run.layouts:
        names = {a.id: f"{a.kind} '{a.name}'" for a in run.assets}
        run.layouts[image_id]["lines"] = [(ln.text, ln.box) for ln in lines]
        run.layouts[image_id]["assets"] = [(names.get(m.asset_id, "official asset"), m.box)
                                          for m in matches or [] if m.found]

    # A second opinion on text: if the vision model read substantially more
    # than local OCR (stylised lettering, handwriting), check that text too.
    if scene and len(scene.text_in_image) > 20 and _novel(scene.text_in_image, ocr.text if ocr else ""):
        src = Source(f"{image_id}:vision-text", "ocr", scene.text_in_image, "ocr:vision", 0.7,
                     {**locator, "image": image_id}, parent=image_id)
        await run.tree.spawn(node, "text", "Text the vision model read", lambda n: text_agent(run, n, src))


async def ocr_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str, locator: dict[str, Any],
                    *, scanned: bool) -> local_ocr.OcrResult:
    result = await run.blocking(local_ocr.read, pil)
    text, route, confidence = result.text, "ocr:local", result.confidence
    # "Weak" needs real text read badly, not a stray fragment on a picture.
    weak = sum(ch.isalnum() for ch in text) >= 8 and confidence < run.ocr_min_confidence
    thin_scan = scanned and len(text) < SCANNED_FALLBACK_CHARS
    node.detail = {"engine": result.engine, "lines": len(result.lines), "confidence": round(confidence, 3)}

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
                     parent=image_id)
        await run.tree.spawn(node, "text", "Text found in image", lambda n: text_agent(run, n, src))
    return result


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


async def scene_agent(run: ReviewRun, node: AgentNode, pil: Image.Image, image_id: str,
                      ocr: local_ocr.OcrResult, context: str) -> SceneReport:
    encoded, hidden = await run.blocking(_redacted_png, pil, ocr, run.leak_patterns(), 1400)
    shareable = [a for a in run.assets if not a.restricted]
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


def _novel(seen: str, known: str) -> bool:
    a = {w for w in seen.lower().split() if len(w) > 2}
    b = {w for w in known.lower().split() if len(w) > 2}
    return bool(a) and len(a - b) / len(a) > 0.4


def _asset_findings(run: ReviewRun, node: AgentNode, image_id: str, locator: dict[str, Any],
                    matches: list[asset_match.AssetMatch], scene: SceneReport | None,
                    lines: list[local_ocr.OcrLine] | None = None) -> None:
    """Fuse pixel evidence and the vision verdict, official artwork first.

    Pixel findings stand on their own. A vision-only finding is a model
    opinion: it is reported, but it can never block publication by itself.
    """
    verdicts = {}
    if scene:
        shown = [a for a in run.assets if not a.restricted][:MAX_VISION_REFERENCES]
        verdicts = {shown[v.reference - 1].id: v for v in scene.assets if 0 < v.reference <= len(shown)}
    vision_name = run.vision.name
    out: list[RawFinding] = []
    by_id = {m.asset_id: m for m in matches}

    def finding(code: str, title: str, why: str, confidence: float, box=None, model=None) -> None:
        rule = run.rule_by_code.get(code)
        if rule is None:
            return
        out.append(RawFinding(
            unit_id=image_id, category=rule.category, title=title, explanation=f"{rule.text} {why}".strip(),
            confidence=round(min(1.0, confidence), 4), checker="assets", rule_code=rule.code, source=image_id,
            locator={**locator, "image": image_id, **({"box": list(box)} if box else {})}, model=model,
        ))

    for asset in run.assets:
        m = by_id.get(asset.id)
        v = verdicts.get(asset.id)
        found = bool(m and m.found)
        label = f"official {asset.kind} '{asset.name}'"

        if asset.restricted and found:
            # Unreleased artwork in lower-tier content is a leak, whatever its quality.
            rule = run.rule_by_code.get("CONF-LEAK")
            if rule:
                # Generic on purpose: anyone who can read this content can read
                # the finding, and the asset's name may itself be a codename.
                out.append(RawFinding(
                    unit_id=image_id, category=rule.category, title="Unreleased brand artwork",
                    explanation=f"This image contains official artwork restricted above this content's tier "
                                f"(asset #{asset.id}; an approver can see which). {rule.text}", confidence=1.0,
                    checker="assets", rule_code=rule.code, source=image_id,
                    locator={**locator, "image": image_id, "box": list(m.box or [])},
                ))
            continue

        if found and m.altered:
            cells = ", ".join(f"r{c['row'] + 1}c{c['col'] + 1} ({c['change']})" for c in m.altered_cells[:6])
            extra = f" The vision model also notes: {'; '.join(v.changes[:3])}." if v and v.changes else ""
            finding("VIS-ASSET-ALTERED", f"{asset.name} differs from the official artwork",
                    f"Pixel comparison against {label} found changed regions: {cells}.{extra}",
                    0.9, m.box)

        elif found and v and v.present == "altered" and v.changes and v.confidence >= 0.7:
            finding("VIS-ASSET-ALTERED", f"{asset.name} may differ from the official artwork",
                    f"The pixels match {label}, and the vision model notes: {'; '.join(v.changes[:3])}.",
                    0.6 * v.confidence, m.box, model=vision_name)

        attached = found and asset.part in _EXTENDABLE_PARTS and (m.attached_ratio or 0) >= asset_match.ATTACHED_RATIO
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
    run.add(node, "assets", out)


# --- documents ---------------------------------------------------------------------------------------

async def document_agent(run: ReviewRun, node: AgentNode, doc: dict[str, Any]) -> None:
    raw = run.payload(doc, MAX_DOC_BYTES)
    kind = sniff(raw)
    doc_id = str(doc.get("id"))
    if kind == "application/pdf":
        extracted = await run.blocking(extract_pdf, raw)
    elif kind.endswith("wordprocessingml.document"):
        extracted = await run.blocking(extract_docx, raw)
    else:
        raise MediaError(f"{doc_id} is not a PDF or Word file (looks like {kind})")
    node.detail = {"kind": extracted.kind, "pages": extracted.page_count, "notes": extracted.notes}
    # A page with a text layer and one image needs about a dozen agents.
    run.tree.grow(12 * len(extracted.pages))
    run.notes.extend(f"{doc_id}: {n}" for n in extracted.notes)
    if extracted.partial:
        run.partial |= MEDIA_COVERS
    await asyncio.gather(*(
        run.tree.spawn(node, "page", f"Page {page.number}", lambda n, page=page: page_agent(run, n, doc_id, page,
                                                                                               extracted.kind))
        for page in extracted.pages
    ))


async def page_agent(run: ReviewRun, node: AgentNode, doc_id: str, page, kind: str) -> None:
    base = f"doc:{doc_id}:p{page.number}"
    locator = {"document": doc_id, "page": page.number}
    node.detail = {"scanned": page.scanned, "images": len(page.images), "text_chars": len(page.text)}
    work = []
    if page.text.strip():
        src = Source(f"{base}:text", "pdf_text" if kind == "pdf" else "docx_text", page.text,
                     "pdf-text-layer" if kind == "pdf" else "docx", 1.0, locator, parent=doc_id)
        work.append(run.tree.spawn(node, "text", "Text layer", lambda n: text_agent(run, n, src)))
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
    await asyncio.gather(*work)


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
            if not c or c == target or _BRAND_FORMS.sub("", c) == target:
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


_BRAND_FORMS = re.compile(r"^[#@]|(?:['\u2019]s?|e?s)$")


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
    signals: dict[str, Any] = {"speech": False, "burned_in": False, "track": False, "music_only": False}

    async def captions(n: AgentNode) -> None:
        cues, passes, cut_at = await run.blocking(video.caption_cues, samples, local_ocr.read)
        n.detail = {"ocr_passes": passes, "cues": len(cues), "read_until_s": cut_at}
        if cut_at is not None:
            n.status, n.note = "not_checked", f"on-screen text read only up to {cut_at:.0f} s (OCR budget reached)"
        if samples:
            run.layouts[video_id] = {"size": samples[0][1].size, "video": True,
                                     "lines": [(c.text, c.box) for c in cues if c.box], "assets": []}
        if cues:
            signals["burned_in"] = True
            text, timeline = video.cue_text(cues)
            conf = sum(c.confidence for c in cues) / len(cues)
            src = Source(f"{video_id}:captions", "captions", text, "ocr:frames", conf, locator, video_id, timeline)
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
        cues, language, prob = await run.blocking(video.transcribe, pcm, run.asr_model)
        level = video.loudness(pcm)
        n.detail = {"segments": len(cues), "language": language, "language_probability": round(prob, 2),
                    "loudness_dbfs": level, "model": f"whisper-{run.asr_model} (local)"}
        if not cues:
            signals["music_only"] = bool(level > -45)
            n.note = "no speech: music or ambient sound only" if level > -45 else "silent"
            return
        signals["speech"] = True
        text, timeline = video.cue_text(cues)
        conf = sum(c.confidence for c in cues) / len(cues)
        src = Source(f"{video_id}:speech", "speech", text, f"asr:whisper-{run.asr_model}", conf,
                     {**locator, "language": language}, video_id, timeline)
        await run.tree.spawn(n, "text", "What is said", lambda c: text_agent(run, c, src))

    async def visuals(n: AgentNode) -> None:
        keys = await run.blocking(video.keyframes, samples)
        n.detail = {"keyframes": [t for t, _ in keys]}
        best: dict[int, tuple[asset_match.AssetMatch, float]] = {}
        if run.assets:
            for t, img in keys:
                feats = await run.blocking(asset_match.scene_features, img)
                for m in await asyncio.gather(*(run.blocking(asset_match.match, a.prepared, feats)
                                               for a in run.assets)):
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
        matches = [m for m, _ in best.values()]
        times = {m.asset_id: t for m, t in best.values()}
        before = len(run.findings)
        _asset_findings(run, n, video_id, locator, matches, scene)
        for f in run.findings[before:]:
            for m in matches:
                if f.locator and f.locator.get("box") == list(m.box or []) and m.asset_id in times:
                    f.locator["time"] = [times[m.asset_id], times[m.asset_id]]

    await asyncio.gather(
        run.tree.spawn(node, "captions", "Read burned-in captions", captions),
        run.tree.spawn(node, "subtitles", "Read subtitle tracks", subtitles) if meta["subtitle_streams"]
        else asyncio.sleep(0),
        run.tree.spawn(node, "speech", "Transcribe speech (local)", speech) if meta["has_audio"]
        else asyncio.sleep(0),
        run.tree.spawn(node, "keyframes", "Check keyframes", visuals),
    )
    node.detail["signals"] = signals
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
