from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from verytas import __version__
from verytas.config import Settings, get_settings
from verytas.db import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.create_all()
        yield
        await db.dispose()

    app = FastAPI(title="Verytas", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "llm_mode": settings.llm_mode}

    return app


app = create_app()
