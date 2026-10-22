from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from verytas import __version__
from verytas.api import admin, assistant, chats, content, governance, insights, knowledge, media, people
from verytas.config import Settings, get_settings
from verytas.db import Database
from verytas.media import storage
from verytas.prism.orchestrator import Prism
from verytas.services.workspace import backfill_system_rule_tiers, backfill_system_rules


def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=f"verytas@{__version__}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Content under review can be confidential: errors only, never payloads.
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _init_sentry(settings)
    db = Database(settings.database_url)
    prism = Prism(settings, db.sessionmaker)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.create_all()
        async with db.sessionmaker() as session:
            await backfill_system_rule_tiers(session)
            await backfill_system_rules(session)
        sweep = asyncio.create_task(storage.sweep_forever(db.sessionmaker, settings.orphan_upload_ttl_h))
        try:
            yield
        finally:
            # Stopped and finished before the database closes under it.
            sweep.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep
        await prism.drain()
        await db.dispose()

    app = FastAPI(
        title="Verytas",
        version=__version__,
        description="Pre-publication brand governance with cited findings and human review.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.prism = prism
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "llm_mode": settings.llm_mode,
                "llm_backend": settings.llm_backend}

    # media before content: /contents/precheck must not be read as a content id.
    for module in (admin, knowledge, people, media, content, governance, insights, chats, assistant):
        app.include_router(module.router)
    return app


app = create_app()
