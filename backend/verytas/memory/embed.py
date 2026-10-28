"""One local text embedder for everything Inki remembers: earlier turns of a conversation, and what a person
has told Ask Inki about how they work.

The model runs on this server's CPU (fastembed, ONNX), so the words being embedded never leave it; the hosted
model only ever sees the few turns or facts picked. It loads on first use and once per process, and a lock
keeps two requests from loading it twice. "hash" is a model-free stand-in with the same interface: tests and
offline runs use it, and it still ranks a turn that shares words with the question above one that doesn't.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from pathlib import Path

import numpy as np

# bge models are trained to embed a question with this instruction in front and the passages without it.
_BGE_QUERY = "Represent this sentence for searching relevant passages: "
_WORD = re.compile(r"[\w']+", re.UNICODE)
RETRY_AFTER = 300  # seconds
KNOWN_DIMS = {"BAAI/bge-small-en-v1.5": 384}


class HashEmbedder:
    """Words and character trigrams hashed into a fixed vector: overlap without meaning. Deterministic."""

    model = "hash"
    dims = 384

    def _one(self, text: str) -> np.ndarray:
        v = np.zeros(self.dims, dtype=np.float32)
        words = _WORD.findall(text.lower())
        grams = [w[i:i + 3] for w in words for i in range(max(1, len(w) - 2))]
        for token, weight in [(w, 1.0) for w in words] + [(g, 0.5) for g in grams]:
            v[int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "little") % self.dims] += weight
        n = float(np.linalg.norm(v))
        return v / n if n else v

    def passages(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._one(t) for t in texts]) if texts else np.zeros((0, self.dims), np.float32)

    def query(self, text: str) -> np.ndarray:
        return self._one(text)

    def warm(self) -> None:
        pass


class LocalEmbedder:
    """A fastembed model, loaded on first use. Vectors come back unit length, so a dot product is the cosine."""

    def __init__(self, model: str, cache_dir: Path | None = None) -> None:
        self.model = model
        self._cache = str(cache_dir) if cache_dir else None
        self._engine = None
        self._lock = threading.Lock()
        self._failed_at: float | None = None
        # Known up front for the models we name, so the memory store opens (to list or forget) without loading one.
        self.dims = KNOWN_DIMS.get(model, 0)

    def _ready(self):
        if self._engine is None:
            # A load that failed (no model files, no network to fetch them) is not tried again on every
            # question for a while: each try can take as long as a download times out.
            if self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_AFTER:
                raise RuntimeError(f"embedding model {self.model} failed to load; next try in a few minutes")
            with self._lock:
                if self._engine is None:
                    if self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_AFTER:
                        raise RuntimeError(f"embedding model {self.model} failed to load just now")
                    from fastembed import TextEmbedding

                    try:
                        engine = TextEmbedding(model_name=self.model, cache_dir=self._cache, threads=1)
                    except Exception:
                        self._failed_at = time.monotonic()
                        raise
                    self.dims = engine.embedding_size
                    self._engine = engine
        return self._engine

    def warm(self) -> None:
        """Load now (at startup), not inside the first question someone asks."""
        self.query("warm")

    def _embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims or 384), np.float32)
        v = np.asarray(list(self._ready().embed([t.replace("\n", " ")[:2000] for t in texts], batch_size=32)),
                       dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def passages(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)

    def query(self, text: str) -> np.ndarray:
        return self._embed([(_BGE_QUERY if "bge" in self.model.lower() else "") + text])[0]


Embedder = HashEmbedder | LocalEmbedder

_shared: dict[tuple[str, str | None], Embedder] = {}
_shared_lock = threading.Lock()


def embedder_for(model: str, cache_dir: Path | None = None) -> Embedder:
    """The process-wide embedder for a model: one copy in memory however many callers ask."""
    key = (model, str(cache_dir) if cache_dir else None)
    with _shared_lock:
        if key not in _shared:
            _shared[key] = HashEmbedder() if model == "hash" else LocalEmbedder(model, cache_dir)
        return _shared[key]
