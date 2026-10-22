"""The API's side of the vision worker: send scenes and artwork, get characters back.

Imports nothing heavy, so the API servers can use it without torch. Scenes are shrunk before they go
(the detector works at about 800 pixels anyway) and the boxes that come back are scaled to the
original image.
"""

from __future__ import annotations

import base64
import io
import ipaddress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
from PIL import Image

SEND_SIDE = 1280
# The worker caps one request at 24 scenes; a video's frames go in batches of this size.
BATCH = 12
CONNECT_S = 5.0


def _private_or_tls(url: str) -> bool:
    """Frames and the token travel in clear over http, so plain http is for loopback or a private network
    (the worker beside the API in one VPC) only."""
    parts = urlsplit(url)
    if parts.scheme == "https":
        return True
    if parts.scheme != "http" or not parts.hostname:
        return False
    if parts.hostname == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


class VisionUnavailable(RuntimeError):
    """The worker could not be reached or failed: the character check did not run."""


@dataclass
class Character:
    box: list[float]
    score: float
    likeness: dict[str, float]
    # Reference id -> differences from it; a reference missing here was not compared.
    differences: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    uncounted: list[str] = field(default_factory=list)  # compared by colour only (too small for parts)

    def best(self) -> tuple[str | None, float]:
        if not self.likeness:
            return None, 0.0
        ref = max(self.likeness, key=self.likeness.__getitem__)
        return ref, self.likeness[ref]


def _encode(img: Image.Image, *, keep_alpha: bool) -> tuple[str, float]:
    scale = min(1.0, SEND_SIDE / max(img.size))
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    if keep_alpha:
        img.convert("RGBA").save(buf, "PNG")
    else:
        # High-quality JPEG: a quarter of the PNG's size, and colour differences of a few units don't move
        # the fidelity check, whose colour tolerance is far wider.
        img.convert("RGB").save(buf, "JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode(), scale


class VisionClient:
    def __init__(self, url: str, token: str | None, timeout_s: float,
                 wake: Callable[[], Awaitable[None]] | None = None) -> None:
        if not _private_or_tls(url):
            raise ValueError("the vision worker needs https unless it is on this machine or a private network")
        self.url = url.rstrip("/")
        self.headers = {"X-Vision-Token": token} if token else {}
        self.timeout_s = timeout_s
        # Starts a stopped worker instance and waits for it (deploy/vision.sh); None for a worker that is
        # always on.
        self.wake = wake

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        # A stopped instance drops packets rather than refusing them: give up connecting in seconds, so the
        # wake starts at once instead of after the whole request timeout.
        timeout = httpx.Timeout(self.timeout_s, connect=CONNECT_S)
        async with httpx.AsyncClient(timeout=timeout, headers=self.headers) as client:
            res = await client.post(f"{self.url}/characters", json=body)
        if res.status_code != 200:
            raise VisionUnavailable(f"vision worker answered {res.status_code}")
        return res.json()

    async def characters(self, scenes: list[Image.Image],
                         references: list[tuple[str, Image.Image]]) -> list[list[Character]]:
        """For each scene, the characters in it, in the scene's own pixels."""
        refs = [{"id": rid, "image_base64": _encode(img, keep_alpha=True)[0]} for rid, img in references]
        out: list[list[Character]] = []
        for start in range(0, len(scenes), BATCH):
            encoded = [_encode(s, keep_alpha=False) for s in scenes[start:start + BATCH]]
            body = {"scenes": [b64 for b64, _ in encoded], "references": refs}
            try:
                try:
                    data = await self._post(body)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    # A stopped instance refuses or doesn't answer at all; either way, wake it once.
                    if self.wake is None:
                        raise
                    await self.wake()
                    data = await self._post(body)
                answered = data["scenes"]
                if len(answered) != len(encoded):
                    raise ValueError("the worker answered for a different number of scenes")
                for (_, scale), found in zip(encoded, answered, strict=True):
                    out.append([Character(box=[round(float(v) / scale, 1) for v in ch["box"]],
                                          score=float(ch["score"]), likeness=dict(ch["likeness"]),
                                          differences=dict(ch.get("differences") or {}),
                                          uncounted=list(ch.get("uncounted") or [])) for ch in found])
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise VisionUnavailable(f"vision worker unreachable or malformed ({type(exc).__name__})") from exc
        return out
