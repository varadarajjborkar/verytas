from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import StatementError

from verytas import __version__
from verytas.api import (
    accounts,
    admin,
    assist,
    assistant,
    chats,
    content,
    governance,
    insights,
    intake,
    knowledge,
    media,
    messages,
    onboarding,
    people,
    search,
)
from verytas.config import Settings, get_settings
from verytas.db import Database
from verytas.intake import pipeline as intake_pipeline
from verytas.media import storage
from verytas.prism.orchestrator import Prism
from verytas.services.messages import MessageHub, MessageSeal
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
    hub = MessageHub(settings.redis_url, settings.message_cache_size, settings.redis_namespace)
    seal = MessageSeal(settings.keys_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.create_all()
        async with db.sessionmaker() as session:
            await backfill_system_rule_tiers(session)
            await backfill_system_rules(session)
        await intake_pipeline.recover(db.sessionmaker)
        await prism.recover()
        sweep = asyncio.create_task(storage.sweep_forever(db.sessionmaker, settings.orphan_upload_ttl_h))
        seal.ensure_key()
        await hub.start()
        try:
            yield
        finally:
            # Stopped and finished before the database closes under it.
            sweep.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep
            await hub.close()
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
    app.state.messages = hub
    app.state.message_seal = seal
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # An id past 64 bits passes int validation but can't be bound to SQLite. Nothing has such an id, so
    # it is the same answer as any unknown one, given once here rather than capped on every route.
    @app.exception_handler(OverflowError)
    async def _too_big(_: Request, __: OverflowError) -> JSONResponse:
        return JSONResponse({"detail": "not found"}, status_code=404)

    @app.exception_handler(StatementError)
    async def _unbindable(request: Request, exc: StatementError) -> JSONResponse:
        if isinstance(exc.orig, OverflowError):
            return JSONResponse({"detail": "not found"}, status_code=404)
        raise exc

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "llm_mode": settings.llm_mode,
                "llm_backend": settings.llm_backend}

    # media before content: /contents/precheck must not be read as a content id.
    routers = (admin, accounts, knowledge, people, media, intake, content, governance, insights, chats, assistant,
               assist, search, onboarding, messages)
    for module in routers:
        app.include_router(module.router)
    return app


app = create_app()
