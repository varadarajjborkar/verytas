"""Model files the visual checks need, fetched once from a pinned address and checked by hash.

The servers pull code from GitHub and nothing else is copied onto them, so a model that isn't there is
downloaded on first use into the vision models folder. Every file has a SHA-256 pinned here: a file that
doesn't match (a swapped upstream, a truncated download) is deleted and refused, never loaded.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

PINNED: dict[str, tuple[str, str]] = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
    "sam2.1_hiera_tiny.pt": (
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt",
        "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"),
}
_LOCK = threading.Lock()


class ModelUnavailable(RuntimeError):
    """A model file is missing and could not be fetched intact."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure(name: str, folder: Path, *, timeout: float = 300) -> Path:
    """The path of a pinned model file, downloading it first if it isn't there yet."""
    url, expected = PINNED[name]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    with _LOCK:
        if path.is_file() and _sha256(path) == expected:
            return path
        partial = path.with_suffix(path.suffix + ".part")
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as res:
                res.raise_for_status()
                with partial.open("wb") as fh:
                    for chunk in res.iter_bytes(1 << 20):
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            partial.unlink(missing_ok=True)
            raise ModelUnavailable(f"couldn't download {name}: {exc}") from exc
        if _sha256(partial) != expected:
            partial.unlink(missing_ok=True)
            raise ModelUnavailable(f"{name} did not match its pinned hash; refused")
        partial.replace(path)
        log.info("downloaded %s", name)
        return path
