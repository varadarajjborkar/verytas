"""Faces in content: where they are, and whose they are.

Two small models from the OpenCV model zoo, run by OpenCV itself on the CPU:
- YuNet (MIT licence, 0.2 MB) finds faces and their five landmarks;
- SFace (Apache-2.0, 37 MB) turns an aligned face into a 128-number description, and two descriptions of
  the same person are close (cosine similarity). OpenCV's published threshold for SFace is 0.363.

Identification only: whether an identified person may appear is the brand's record (checks/likeness.py).
The model files live in the vision models folder (`vision_models_dir`); without them the face check is
reported as not run, never as a pass.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DETECTOR = "face_detection_yunet_2023mar.onnx"
RECOGNISER = "face_recognition_sface_2021dec.onnx"
# OpenCV's SFace threshold for "same person" by cosine similarity (opencv_zoo, face_recognition_sface).
SAME_PERSON = 0.363
# Below this a face is too small to identify reliably (a crowd in the background).
MIN_FACE_SIDE = 40
DETECT_SCORE = 0.8
_LOCK = threading.Lock()
_MODELS: dict[Path, tuple] = {}


class FacesUnavailable(RuntimeError):
    """The model files are missing: the face check did not run."""


@dataclass
class Face:
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in the image's pixels
    score: float
    row: np.ndarray  # YuNet's raw row (box, landmarks, score), which SFace aligns from
    embedding: np.ndarray | None = None

    @property
    def side(self) -> int:
        return min(self.box[2] - self.box[0], self.box[3] - self.box[1])


def _models(folder: Path):
    folder = folder.resolve()
    with _LOCK:
        if folder not in _MODELS:
            det, rec = folder / DETECTOR, folder / RECOGNISER
            if not det.is_file() or not rec.is_file():
                raise FacesUnavailable(f"face models not found in {folder}")
            _MODELS[folder] = (cv2.FaceDetectorYN.create(str(det), "", (320, 320), DETECT_SCORE, 0.3, 50),
                               cv2.FaceRecognizerSF.create(str(rec), ""))
        return _MODELS[folder]


def find(img: Image.Image, folder: Path, *, min_side: int = MIN_FACE_SIDE) -> list[Face]:
    """Faces at least `min_side` pixels across, each with its description, largest first.

    The detector and recogniser are shared and not thread-safe, so one image is processed at a time."""
    detector, recogniser = _models(folder)
    bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    with _LOCK:
        detector.setInputSize((w, h))
        _, rows = detector.detect(bgr)
        faces = []
        for row in rows if rows is not None else []:
            x, y, fw, fh = (int(round(v)) for v in row[:4])
            face = Face((max(0, x), max(0, y), min(w, x + fw), min(h, y + fh)), float(row[-1]), row)
            if face.side < min_side:
                continue
            aligned = recogniser.alignCrop(bgr, row)
            face.embedding = recogniser.feature(aligned).flatten().astype(np.float32)
            faces.append(face)
    return sorted(faces, key=lambda f: -f.side)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def describe(img: Image.Image, folder: Path) -> np.ndarray | None:
    """The description of the main (largest) face in a reference photo, or None when it has no face."""
    faces = find(img, folder)
    return faces[0].embedding if faces else None
