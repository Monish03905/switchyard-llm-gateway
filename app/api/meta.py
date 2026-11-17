from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select

from app.api.telemetry import uptime_seconds
from app.models import EvalBatch, EvalRun, GatewayRequest

router = APIRouter(tags=["system"])

BREAKER_VALUE = {"closed": 0, "half-open": 1, "open": 2}


@router.get("/health")
async def health(request: Request):
    app = request.app
    checks = {"database": "ok"}
    try:
        async with app.state.db.session_factory() as session:
            await session.execute(select(1))
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
    registry = app.state.registry
    body = {
        "status": "ok" if checks["database"] == "ok" else "degraded",
        "version": app.state.settings.app_version,
        "environment": app.state.settings.app_env,
        "mode": registry.mode,
        "simulated": registry.mode == "simulated",
        "uptime_s": uptime_seconds(app),
        "checks": checks,
    }
    return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)


@router.get("/api/health")
async def api_health(request: Request):
    return await health(request)


@router.get("/metrics/prometheus")
async def prometheus(request: Request):
    app = request.app
    lines = [
        "# HELP switchyard_requests_total Receipts in the ledger by status.",
        "# TYPE switchyard_requests_total counter",
    ]
    tokens_total = 0
    async with app.state.db.session_factory() as session:
        rows = (
            await session.execute(
                select(
                    GatewayRequest.status,
                    func.count(GatewayRequest.seq),
                    func.coalesce(func.sum(GatewayRequest.cost_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.total_tokens), 0),
                    func.coalesce(func.sum(GatewayRequest.co2e_g), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_co2e_g), 0.0),
                ).group_by(GatewayRequest.status)
            )
        ).all()
        cost_total = saved_total = co2_total = saved_co2_total = 0.0
        for status, count, cost, saved, tokens, co2, saved_co2 in rows:
            lines.append(f'switchyard_requests_total{{status="{_escape(status)}"}} {int(count)}')
            cost_total += float(cost)
            saved_total += float(saved)
            tokens_total += int(tokens)
            co2_total += float(co2)
            saved_co2_total += float(saved_co2)

        cache_hits = await session.scalar(
            select(func.count(GatewayRequest.seq)).where(GatewayRequest.cache_hit.is_(True))
        )
        fallbacks = await session.scalar(
            select(func.count(GatewayRequest.seq)).where(GatewayRequest.fallback_used.is_(True))
        )
        batch = await session.scalar(select(EvalBatch).order_by(EvalBatch.created_ms.desc()).limit(1))
        runs = []
        if batch is not None:
            runs = (
                await session.scalars(
                    select(EvalRun).where(EvalRun.batch_id == batch.id).order_by(EvalRun.policy)
                )
            ).all()

    lines += [
        "# HELP switchyard_cost_usd_total Recorded provider spend.",
        "# TYPE switchyard_cost_usd_total counter",
        f"switchyard_cost_usd_total {cost_total:.8f}",
        "# HELP switchyard_saved_usd_total Spend avoided against the prime baseline.",
        "# TYPE switchyard_saved_usd_total counter",
        f"switchyard_saved_usd_total {saved_total:.8f}",
        "# HELP switchyard_tokens_total Input plus output tokens.",
        "# TYPE switchyard_tokens_total counter",
        f"switchyard_tokens_total {tokens_total}",
        "# HELP switchyard_co2e_grams_total Estimated emissions.",
        "# TYPE switchyard_co2e_grams_total counter",
        f"switchyard_co2e_grams_total {co2_total:.6f}",
        "# HELP switchyard_saved_co2e_grams_total Emissions avoided against the prime baseline.",
        "# TYPE switchyard_saved_co2e_grams_total counter",
        f"switchyard_saved_co2e_grams_total {saved_co2_total:.6f}",
        "# HELP switchyard_cache_hits_total Receipts answered from cache.",
        "# TYPE switchyard_cache_hits_total counter",
        f"switchyard_cache_hits_total {int(cache_hits or 0)}",
        "# HELP switchyard_fallbacks_total Receipts that failed over to another candidate.",
        "# TYPE switchyard_fallbacks_total counter",
        f"switchyard_fallbacks_total {int(fallbacks or 0)}",
        "# HELP switchyard_uptime_seconds Process uptime.",
        "# TYPE switchyard_uptime_seconds gauge",
        f"switchyard_uptime_seconds {uptime_seconds(app)}",
        "# HELP switchyard_provider_mode 1 when live providers are connected, 0 for the simulator.",
        "# TYPE switchyard_provider_mode gauge",
        f"switchyard_provider_mode {0 if app.state.registry.mode == 'simulated' else 1}",
    ]
    for provider in app.state.registry.providers:
        state = app.state.breaker.state(provider.name)
        lines.append(
            f'switchyard_breaker_state{{provider="{_escape(provider.name)}"}} {BREAKER_VALUE[state]}'
        )
    if batch is not None:
        lines.append(f'switchyard_gauntlet_progress{{batch="{_escape(batch.id)}"}} {batch.tasks_done}')
        for run in runs:
            lines.append(
                f'switchyard_gauntlet_pass_rate{{policy="{_escape(run.policy)}"}} {run.pass_rate:.4f}'
            )
            lines.append(
                f'switchyard_gauntlet_cost_usd{{policy="{_escape(run.policy)}"}} {run.total_cost_usd:.8f}'
            )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
