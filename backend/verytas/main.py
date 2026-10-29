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
    results,
    search,
    tokens,
)
from verytas.config import Settings, get_settings
from verytas.db import Database
from verytas.intake import pipeline as intake_pipeline
from verytas.mcpserver import mount_mcp
from verytas.media import storage
from verytas.memory.embed import embedder_for
from verytas.memory.personal import PersonalMemory
from verytas.prism.orchestrator import Prism
from verytas.services.messages import MessageHub, MessageSeal
from verytas.services.workspace import backfill_system_rule_tiers, backfill_system_rules

log = logging.getLogger("verytas")


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


async def _warm(embedder) -> None:
    try:
        await asyncio.to_thread(embedder.warm)
    except Exception:  # noqa: BLE001 - Inki answers without its memory until the model loads
        log.warning("embedding model did not load; Inki's memory is off until it does", exc_info=True)


async def _lapse_forever(personal) -> None:
    """Hourly: a shared demo sign-in's facts are deleted a day after they were kept (memory/personal.py)."""
    while True:
        try:
            if n := await personal.sweep():
                log.info("inki forgot %d facts kept on shared sign-ins over a day ago", n)
        except Exception:  # noqa: BLE001 - the next hour tries again; reads skip lapsed facts meanwhile
            log.warning("inki memory sweep failed", exc_info=True)
        await asyncio.sleep(3600)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _init_sentry(settings)
    db = Database(settings.database_url, guard_reads=settings.db_guard_reads)
    prism = Prism(settings, db.sessionmaker)
    hub = MessageHub(settings.redis_url, settings.message_cache_size, settings.redis_namespace)
    seal = MessageSeal(settings.keys_dir)

    mcp_manager = None

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
        if settings.memory_enabled:
            # The embedding model loads now, off the event loop, rather than inside the first question asked.
            warming = asyncio.create_task(_warm(app.state.embedder))
            lapsing = asyncio.create_task(_lapse_forever(app.state.personal))
        try:
            if mcp_manager is None:
                yield
            else:
                # The SDK's session manager owns a task group that must live as long as the app does.
                async with mcp_manager.run():
                    yield
        finally:
            # Stopped and finished before the database closes under it.
            sweep.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep
            if settings.memory_enabled:
                warming.cancel()
                lapsing.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await warming
                with contextlib.suppress(asyncio.CancelledError):
                    await lapsing
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
    # One embedding model for all of Inki's memory, loaded on first use (verytas/memory/embed.py).
    app.state.embedder = embedder_for(settings.memory_embed_model, settings.memory_dir / "models")
    app.state.personal = PersonalMemory(settings.memory_dir / "personal", app.state.embedder,
                                        settings.memory_dir / "models", settings.memory_shared_hours)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # An id past 64 bits passes int validation but can't be bound to SQLite. Nothing has such an id, so
    # it is the same answer as any unknown one, given once here rather than capped on every route.
    @app.exception_handler(OverflowError)
    async def _too_big(request: Request, exc: OverflowError) -> JSONResponse:
        # Logged, so an overflow from anything other than an id still reaches the logs and Sentry.
        log.warning("overflow on %s %s answered as not found: %s", request.method, request.url.path, exc)
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
    routers = (admin, accounts, knowledge, people, media, intake, content, results, governance, insights, chats,
               assistant, assist, search, onboarding, messages, tokens)
    for module in routers:
        app.include_router(module.router)
    if settings.mcp_enabled:
        mcp_manager = mount_mcp(app)
    return app


app = create_app()
