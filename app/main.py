from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from app.agent.runner import AgentRunner
from app.api import admin, chat, dashboard, evals, meta
from app.api.telemetry import uptime_seconds
from app.config import get_settings, reset_settings_cache
from app.db import Database, LedgerLock
from app.evals.runner import GauntletRunner
from app.gateway.breaker import CircuitBreaker
from app.gateway.cache import build_cache
from app.gateway.chaos import Squall
from app.gateway.ledger import Ledger, now_ms
from app.gateway.pipeline import GatewayError, GatewayPipeline
from app.gateway.registry import ProviderRegistry
from app.models import EvalBatch, EvalRun
from app.rate_limit import RateLimiter

logger = logging.getLogger("switchyard")
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serve the built cockpit, and hand deep links back to index.html."""

    async def get_response(self, path: str, scope):
        normalized = path.replace("\\", "/").lstrip("/")
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            reserved = normalized.startswith(("api/", "v1/")) or normalized in {
                "health",
                "metrics/prometheus",
                "openapi.json",
            }
            if exc.status_code != 404 or reserved:
                raise
            response = await super().get_response("index.html", scope)
        if normalized in {"", ".", "index.html"} or response.headers.get("content-type", "").startswith(
            "text/html"
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        elif normalized.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def create_app() -> FastAPI:
    reset_settings_cache()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        await db.init()
        squall = Squall()
        registry = ProviderRegistry(settings, squall)
        cache = await build_cache(settings)
        breaker = CircuitBreaker(
            threshold=settings.breaker_threshold,
            window_s=settings.breaker_window_s,
            cooldown_s=settings.breaker_cooldown_s,
        )
        ledger = Ledger(settings.ledger_key, LedgerLock())
        pipeline = GatewayPipeline(
            settings=settings,
            registry=registry,
            cache=cache,
            breaker=breaker,
            ledger=ledger,
            session_factory=db.session_factory,
        )
        agent = AgentRunner(pipeline)
        gauntlet = GauntletRunner(
            pipeline=pipeline,
            registry=registry,
            agent=agent,
            session_factory=db.session_factory,
        )

        app.state.settings = settings
        app.state.db = db
        app.state.registry = registry
        app.state.cache = cache
        app.state.breaker = breaker
        app.state.ledger = ledger
        app.state.pipeline = pipeline
        app.state.agent = agent
        app.state.gauntlet = gauntlet
        app.state.limiter = RateLimiter(settings.rate_limit_rpm)
        app.state.squall = squall
        app.state.started_at = time.time()
        app.state.probes = {}
        app.state.chain_cache = None
        app.state.batch_jobs = {}
        app.state.active_batch = None

        logger.info(
            "Switchyard %s up in %s mode (db=%s)",
            settings.app_version,
            registry.mode,
            _db_label(settings.database_url),
        )
        try:
            yield
        finally:
            jobs = list(app.state.batch_jobs.values())
            for job in jobs:
                job.cancel()
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
            try:
                await _mark_incomplete(db, "The yard shut down while this gauntlet was in flight.")
            except Exception:  # shutdown must not raise
                logger.exception("could not mark interrupted gauntlets")
            await registry.close()
            await cache.close()
            await db.close()
            logger.info("Switchyard down after %.0fs", uptime_seconds(app))

    app = FastAPI(
        title="Switchyard",
        version=settings.app_version,
        description=(
            "One gate for many models. Explainable routing, failover, receipts and a "
            "policy gauntlet that proves the savings."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "Retry-After"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1200)

    app.include_router(meta.router)
    app.include_router(chat.router)
    app.include_router(dashboard.router)
    app.include_router(evals.router)
    app.include_router(admin.router)

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(_request: Request, exc: GatewayError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "type": exc.kind,
                    "code": exc.kind,
                    "request_id": exc.request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        issues = jsonable_encoder(exc.errors())
        first = issues[0] if issues else {}
        location = ".".join(str(part) for part in first.get("loc", []))
        message = first.get("msg", "Request validation failed")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": f"{location}: {message}" if location else message,
                    "type": "validation_error",
                    "code": "validation_error",
                    "details": issues,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": detail,
                    "type": "http_error",
                    "code": exc.status_code,
                }
            },
            headers=dict(exc.headers or {}),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception):
        logger.exception("unhandled fault", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "The yard hit an unexpected fault. The details are in the server log.",
                    "type": "internal_error",
                    "code": "internal_error",
                }
            },
        )

    if settings.serve_frontend and (WEB_DIST / "index.html").exists():
        app.mount("/", SPAStaticFiles(directory=str(WEB_DIST), html=True), name="cockpit")
    else:

        @app.get("/", include_in_schema=False)
        async def root():
            return {
                "name": "Switchyard",
                "version": settings.app_version,
                "docs": "/docs",
                "health": "/health",
                "note": "The cockpit is not built yet. Run `npm install && npm run build` in web/.",
            }

    return app


async def _mark_incomplete(db: Database, reason: str) -> None:
    async with db.session_factory() as session:
        batches = (
            await session.scalars(
                select(EvalBatch).where(EvalBatch.status.in_(("queued", "running", "cancelling")))
            )
        ).all()
        for batch in batches:
            batch.status = "cancelled"
            batch.error = reason
            batch.completed_ms = now_ms()
        runs = (await session.scalars(select(EvalRun).where(EvalRun.status.in_(("queued", "running"))))).all()
        for run in runs:
            run.status = "cancelled"
            run.error = reason
            run.completed_ms = now_ms()
        if batches or runs:
            await session.commit()


def _db_label(url: str) -> str:
    return url.split("://", 1)[0] if "://" in url else url


app = create_app()
