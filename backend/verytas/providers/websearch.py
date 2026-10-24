"""Web search for claim research (prism/research.py): Ollama's search API, on the keys we already hold.

Verified 2026-10-24: POST https://ollama.com/api/web_search with the Ollama Cloud key returns titles,
URLs and page text, at no cost on the free plan. Same key handling as the model clients: a refused or
rate-limited key moves to the backup key for ten minutes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from verytas.providers.base import ProviderUnavailable

_KEY_REFUSED = {401, 402, 403, 429}
_FALLBACK_HOLD_S = 600.0
SNIPPET_CHARS = 600


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str

    @property
    def site(self) -> str:
        # The host alone: netloc would show "apple.com@evil.example" or a port as if it were the site's name.
        return (urlparse(self.url).hostname or "").removeprefix("www.")


class OllamaWebSearch:
    name = "ollama/web_search"

    def __init__(self, api_key: str, *, base_url: str = "https://ollama.com", fallback_key: str | None = None,
                 timeout: float = 20.0) -> None:
        self._keys = [api_key] + ([fallback_key] if fallback_key and fallback_key != api_key else [])
        self._fallback_until = 0.0
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, max_results: int = 3) -> list[WebResult]:
        first = 1 if len(self._keys) > 1 and time.monotonic() < self._fallback_until else 0
        last = "no key"
        for i in range(first, len(self._keys)):
            for attempt in range(2):
                try:
                    res = await self._client.post("/api/web_search", json={"query": query, "max_results": max_results},
                                                  headers={"Authorization": f"Bearer {self._keys[i]}"})
                except httpx.HTTPError as exc:
                    last = f"{type(exc).__name__}: {exc}"
                else:
                    if res.status_code == 200:
                        return _results(res)
                    last = f"HTTP {res.status_code}"
                    if res.status_code in _KEY_REFUSED:
                        break
                    if res.status_code < 500:
                        raise ProviderUnavailable(f"web search {last}: {res.text[:200]}")
                if attempt == 0:
                    await asyncio.sleep(1.0)
            if i + 1 < len(self._keys):
                self._fallback_until = time.monotonic() + _FALLBACK_HOLD_S
        raise ProviderUnavailable(f"web search unavailable ({last})")


def _results(res: httpx.Response) -> list[WebResult]:
    try:
        data = res.json()
    except ValueError as exc:
        raise ProviderUnavailable("web search returned a non-JSON body") from exc
    rows = data.get("results") if isinstance(data, dict) else None
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "")
        # Only web pages: a javascript: or data: link from a search result is never shown, nor is one that
        # has no host ("https:foo") or hides one behind credentials ("https://apple.com@evil.example/").
        try:
            parts = urlparse(url)
        except ValueError:  # e.g. an unclosed IPv6 bracket
            continue
        if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
            continue
        text = " ".join(str(r.get("content") or "").split())
        out.append(WebResult(" ".join(str(r.get("title") or url).split())[:200], url[:500], text[:SNIPPET_CHARS]))
    return out
