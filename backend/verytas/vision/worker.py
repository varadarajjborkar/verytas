"""The vision worker: an HTTP service around the model chain, for the API to call.

    cd backend && .venv-vision/bin/python -m verytas.vision.worker --port 8100

It holds no brand data. Each request brings the scenes and the official artwork; prepared artwork is
cached by content hash, so a brand's mascots are described once per worker, not once per frame. The
worker measures and returns numbers; the review decides what they mean.

Requests carry `X-Vision-Token` matching VERYTAS_VISION_TOKEN. Without a token set, the worker only
listens on the loopback address.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import hmac
import io
import os
import threading
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from verytas.vision.chain import PROMPT, Chain, Reference

MAX_SCENES = 24
MAX_REFERENCES = 12
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_SIDE = 4096
# Base64 adds a third; this bounds a full request before it is read.
MAX_BODY_BYTES = (MAX_SCENES + MAX_REFERENCES) * MAX_IMAGE_BYTES * 4 // 3 + 64 * 1024
FORMATS = ["PNG", "JPEG", "WEBP"]
CACHED_REFERENCES = 64


class ArtworkIn(BaseModel):
    id: str = Field(max_length=64)
    image_base64: str


class CharactersIn(BaseModel):
    scenes: list[str] = Field(min_length=1, max_length=MAX_SCENES)  # base64 PNG or JPEG
    references: list[ArtworkIn] = Field(default_factory=list, max_length=MAX_REFERENCES)
    prompt: str = Field(default=PROMPT, max_length=200)


def _image(b64: str) -> Image.Image:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "an image is not valid base64") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "an image is too large")
    try:
        # Only what the client sends: other decoders (EPS, TIFF) are attack surface with no use here.
        img = Image.open(io.BytesIO(raw), formats=FORMATS)
        if max(img.size) > MAX_SIDE:
            raise HTTPException(413, "an image is too large")
        img.load()
    except Image.DecompressionBombError:
        raise HTTPException(413, "an image is too large") from None
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "an image could not be read") from None
    return img


def create_app(models_dir: Path, token: str | None) -> FastAPI:
    app = FastAPI(title="Verytas vision worker", docs_url=None, redoc_url=None, openapi_url=None)
    state: dict[str, object] = {"chain": None, "last_used": time.time()}
    refs: OrderedDict[str, Reference] = OrderedDict()
    loading = threading.Lock()

    def chain() -> Chain:
        # Loaded on first use, not at start: the instance answers /health while the models load. Two first
        # requests at once must not load the models twice.
        with loading:
            if state["chain"] is None:
                state["chain"] = Chain(models_dir)
        return state["chain"]  # type: ignore[return-value]

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Before the body is read or parsed: an unauthorised or oversized request costs nothing.
        if request.url.path != "/health":
            given = request.headers.get("x-vision-token", "").encode()
            if token and not hmac.compare_digest(given, token.encode()):
                return JSONResponse({"detail": "bad token"}, status_code=401)
            try:
                size = int(request.headers.get("content-length", ""))
            except ValueError:
                return JSONResponse({"detail": "a length is required"}, status_code=411)
            if size > MAX_BODY_BYTES:
                return JSONResponse({"detail": "request too large"}, status_code=413)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "models_loaded": state["chain"] is not None,
                "idle_s": round(time.time() - state["last_used"])}

    def run(body: CharactersIn) -> dict:
        c = chain()
        with c.lock:
            prepared = []
            for art in body.references:
                key = hashlib.sha256(f"{art.id}\0{art.image_base64}".encode()).hexdigest()
                if key not in refs:
                    refs[key] = c.reference(art.id, _image(art.image_base64))
                    if len(refs) > CACHED_REFERENCES:
                        refs.popitem(last=False)
                refs.move_to_end(key)
                prepared.append(refs[key])
            t = time.perf_counter()
            scenes = [[asdict(ch) for ch in c.characters(_image(s), prepared, body.prompt)] for s in body.scenes]
        state["last_used"] = time.time()
        return {"scenes": scenes, "seconds": round(time.perf_counter() - t, 2)}

    @app.post("/characters")
    async def characters(body: CharactersIn) -> dict:
        state["last_used"] = time.time()
        return await asyncio.to_thread(run, body)

    return app


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(prog="verytas.vision.worker")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--models", type=Path, default=Path(os.environ.get("VERYTAS_VISION_MODELS_DIR", ".models")))
    args = p.parse_args()
    token = os.environ.get("VERYTAS_VISION_TOKEN") or None
    host = args.host or ("0.0.0.0" if token else "127.0.0.1")
    if host not in ("127.0.0.1", "localhost") and not token:
        raise SystemExit("set VERYTAS_VISION_TOKEN before listening beyond this machine")
    uvicorn.run(create_app(args.models, token), host=host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
