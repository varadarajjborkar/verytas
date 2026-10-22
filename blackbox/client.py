"""The only door into the system under test: its public HTTP API.

`Server` starts a throwaway Verytas process per reality (fresh database, fresh
signing keys) using nothing but the documented env vars, so realities can't
leak into each other. `Api` is a thin client over the documented endpoints.
Any 5xx is recorded as a failure in its own right.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, review_mode: str) -> None:
        self.review_mode = review_mode
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self._tmp = Path(tempfile.mkdtemp(prefix="verytas-bb-"))
        self._proc: subprocess.Popen | None = None

    async def __aenter__(self) -> Server:
        env = {**os.environ, "VERYTAS_DATABASE_URL": f"sqlite+aiosqlite:///{self._tmp / 'bb.db'}",
               "VERYTAS_KEYS_DIR": str(self._tmp / "keys"), "VERYTAS_LLM_MODE": self.review_mode,
               "VERYTAS_ENVIRONMENT": "blackbox"}
        # Blocking calls are fine here: once per reality, before any load.
        log = open(self._tmp / "server.log", "wb")  # noqa: SIM115, ASYNC230
        # cwd=backend so a live server reads its own .env; the simulator never does.
        self._proc = subprocess.Popen(  # noqa: ASYNC220
            [str(BACKEND / ".venv" / "bin" / "uvicorn"), "verytas.main:app", "--port", str(self.port),
             "--log-level", "warning"], cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
        async with httpx.AsyncClient() as client:
            for _ in range(100):
                try:
                    if (await client.get(f"{self.url}/health")).status_code == 200:
                        return self
                except httpx.HTTPError:
                    pass
                if self._proc.poll() is not None:
                    break
                await asyncio.sleep(0.2)
        raise RuntimeError(f"server did not start; see {self._tmp / 'server.log'}")

    async def __aexit__(self, *exc: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        # Keep the server's own log: a 500 seen from outside is only actionable
        # with the traceback the server wrote.
        logs = Path(__file__).resolve().parent / ".runs" / "logs"  # noqa: ASYNC240, once at shutdown
        logs.mkdir(parents=True, exist_ok=True)
        if (self._tmp / "server.log").exists():
            shutil.copy(self._tmp / "server.log", logs / f"server-{self.port}.log")
        shutil.rmtree(self._tmp, ignore_errors=True)


class ServerError(Exception):
    """A 5xx from the system under test."""


class Api:
    def __init__(self, url: str) -> None:
        self._client = httpx.AsyncClient(base_url=url, timeout=120.0)
        self.server_errors: list[str] = []

    async def aclose(self) -> None:
        await self._client.aclose()

    def auth(self, token: str) -> None:
        self._client.headers["Authorization"] = f"Bearer {token}"

    async def call(self, method: str, path: str, *, token: str | None = None, **kw: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        res = await self._client.request(method, path, headers=headers, **kw)
        if res.status_code >= 500:
            self.server_errors.append(f"{method} {path} -> {res.status_code}: {res.text[:300]}")
            raise ServerError(self.server_errors[-1])
        return res

    async def ok(self, method: str, path: str, **kw: Any) -> Any:
        res = await self.call(method, path, **kw)
        if res.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {res.status_code}: {res.text[:300]}")
        return res.json()

    async def wait_review(self, review_id: int, timeout_s: float) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_s
        delay = 0.1
        while True:
            review = await self.ok("GET", f"/reviews/{review_id}")
            if review["status"] in ("done", "failed"):
                return review
            if asyncio.get_running_loop().time() > deadline:
                return review
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 2.0)
