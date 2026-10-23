"""The three models, and one pass over a scene. Runs in the vision worker's environment only."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from verytas.media.fidelity import compare, official_reference

PROMPT = "a cartoon mascot character."
# Hugging Face models at a fixed commit, like the SAM checkpoint's pinned hash: an upstream change can't
# alter what the benchmark measured.
GDINO = ("IDEA-Research/grounding-dino-tiny", "a2bb814dd30d776dcf7e30523b00659f4f141c71")
DINO = ("facebook/dinov2-small", "ed25f3a31f01632728cabb09d1542f84ab7b0056")
SAM_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"
SAM_CHECKPOINT = "sam2.1_hiera_tiny.pt"
BOX_THRESHOLD = 0.25
TEXT_THRESHOLD = 0.2
MAX_CHARACTERS = 4
# A character is compared, colour by colour and part by part, with every reference at least this alike
# (up to COMPARED): the review decides who it is, and must find that reference's comparison there.
COMPARE_FROM = 0.78  # prism.characters.PROBABLE: a heavy redraw the brief names is compared too
COMPARED = 3
# Grounding DINO returns overlapping boxes for one character; above this overlap they are the same one.
SAME_BOX_IOU = 0.7


@dataclass
class Reference:
    """An official artwork, prepared once: its description and its fidelity reference."""

    id: str
    vector: np.ndarray
    fidelity: tuple[np.ndarray, np.ndarray]


@dataclass
class Character:
    box: list[float]  # x0, y0, x1, y1 in the scene's pixels
    score: float  # detector confidence
    likeness: dict[str, float]  # reference id -> cosine similarity of the descriptions
    # Reference id -> differences from it, as media.fidelity names them, for each reference compared.
    # A reference missing here was not compared; an empty list means compared and faithful.
    differences: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    # Reference ids compared by colour only: the character was too small to count its parts.
    uncounted: list[str] = field(default_factory=list)


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def on_white(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    bg = Image.new("RGB", rgba.size, "white")
    bg.paste(rgba, mask=rgba.getchannel("A"))
    return bg


class Chain:
    """Grounding DINO, SAM2 and DINOv2, loaded once. Not thread-safe: callers hold `lock`."""

    def __init__(self, models_dir: Path, device: str = "cpu") -> None:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        from transformers import AutoImageProcessor, AutoModel, AutoModelForZeroShotObjectDetection, AutoProcessor

        from verytas.media.model_store import ensure

        self.torch, self.device = torch, device
        self.lock = threading.Lock()
        self.proc = AutoProcessor.from_pretrained(GDINO[0], revision=GDINO[1])
        self.gdino = AutoModelForZeroShotObjectDetection.from_pretrained(GDINO[0], revision=GDINO[1])
        self.gdino = self.gdino.to(device).eval()
        checkpoint = ensure(SAM_CHECKPOINT, models_dir)
        self.sam = SAM2ImagePredictor(build_sam2(SAM_CONFIG, str(checkpoint), device=device))
        self.dproc = AutoImageProcessor.from_pretrained(DINO[0], revision=DINO[1])
        self.dino = AutoModel.from_pretrained(DINO[0], revision=DINO[1]).to(device).eval()

    def detect_all(self, scene: Image.Image, prompt: str = PROMPT,
                   limit: int = MAX_CHARACTERS) -> list[tuple[list[float], float]]:
        """Boxes for the prompt, most confident first, one per character."""
        inp = self.proc(images=scene, text=prompt, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.gdino(**inp)
        res = self.proc.post_process_grounded_object_detection(
            out, inp.input_ids, threshold=BOX_THRESHOLD, text_threshold=TEXT_THRESHOLD,
            target_sizes=[scene.size[::-1]])[0]
        ranked = sorted(zip(res["boxes"].tolist(), res["scores"].tolist(), strict=True), key=lambda p: -p[1])
        kept: list[tuple[list[float], float]] = []
        for box, score in ranked:
            if all(iou(box, k) < SAME_BOX_IOU for k, _ in kept):
                kept.append(([float(v) for v in box], float(score)))
            if len(kept) == limit:
                break
        return kept

    def detect(self, scene: Image.Image, prompt: str = PROMPT) -> tuple[list[float], float] | None:
        found = self.detect_all(scene, prompt, limit=1)
        return found[0] if found else None

    def segment(self, scene: Image.Image, box: list[float]) -> np.ndarray:
        self.sam.set_image(np.asarray(scene))
        masks, _, _ = self.sam.predict(box=np.array(box), multimask_output=False)
        return masks[0].astype(bool)

    def embed(self, img: Image.Image) -> np.ndarray:
        with self.torch.no_grad():
            v = self.dino(**self.dproc(images=img.convert("RGB"), return_tensors="pt").to(self.device))
        return self.torch.nn.functional.normalize(v.last_hidden_state[:, 0], dim=-1)[0].cpu().numpy()

    def reference(self, ref_id: str, artwork: Image.Image) -> Reference:
        return Reference(ref_id, self.embed(on_white(artwork)), official_reference(artwork))

    def cut_out(self, scene: Image.Image, box: list[float]) -> tuple[np.ndarray, np.ndarray, Image.Image] | None:
        """The scene's pixels, the character's mask, and the character on white, cropped to the mask."""
        mask = self.segment(scene, box)
        ys, xs = np.nonzero(mask)
        if not len(ys):
            return None
        rgb = np.asarray(scene)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = rgb[y0:y1, x0:x1].copy()
        crop[~mask[y0:y1, x0:x1]] = 255
        return rgb, mask, Image.fromarray(crop)

    def characters(self, scene: Image.Image, refs: list[Reference], prompt: str = PROMPT) -> list[Character]:
        """Every character in the scene, with its likeness to each reference and its differences from
        each reference it resembles."""
        scene = scene.convert("RGB")
        out = []
        for box, score in self.detect_all(scene, prompt):
            cut = self.cut_out(scene, box)
            if cut is None:
                continue
            rgb, mask, crop = cut
            vec = self.embed(crop)
            likeness = {r.id: round(float(vec @ r.vector), 4) for r in refs}
            ch = Character([round(v, 1) for v in box], round(score, 3), likeness)
            alike = sorted((r for r in refs if likeness[r.id] >= COMPARE_FROM), key=lambda r: -likeness[r.id])
            for r in alike[:COMPARED]:
                try:
                    fid = compare(r.fidelity, (rgb, mask))
                except ValueError:
                    continue  # a cut-out too small to compare: left uncompared, never called faithful
                ch.differences[r.id] = [{"kind": d.kind, "text": d.text} for d in fid.differences]
                if not fid.parts_checked:
                    ch.uncounted.append(r.id)
            out.append(ch)
        return out
