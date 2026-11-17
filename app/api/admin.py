from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import require_admin
from app.api.serialize import batch_dict
from app.api.telemetry import chain_state, provider_health
from app.models import EvalBatch
from app.schemas import SquallRequest

router = APIRouter(prefix="/api/admin", tags=["switchboard"], dependencies=[Depends(require_admin)])


@router.get("/state")
async def admin_state(request: Request):
    app = request.app
    settings = app.state.settings
    registry = app.state.registry
    async with app.state.db.session_factory() as session:
        batch = await session.scalar(select(EvalBatch).order_by(EvalBatch.created_ms.desc()).limit(1))
    return {
        "mode": registry.mode,
        "simulated": registry.mode == "simulated",
        "version": settings.app_version,
        "levers": {
            "cache": await app.state.cache.stats(),
            "squall": app.state.squall.snapshot(),
            "limiter": app.state.limiter.snapshot(),
            "budget": await app.state.pipeline._budget_state(),
            "breakers": provider_health(app),
            "chain": await chain_state(app),
        },
        "flags": {
            "store_prompts": settings.store_prompts,
            "default_ledger_key": settings.using_default_ledger_key,
            "gateway_key_required": bool(settings.gateway_api_key),
            "admin_token_required": bool(settings.admin_token),
            "daily_budget_usd": settings.daily_budget_usd,
            "rate_limit_rpm": settings.rate_limit_rpm,
            "carbon_intensity_g_per_kwh": settings.carbon_intensity_g_per_kwh,
            "datacenter_pue": settings.datacenter_pue,
        },
        "batch": {
            "active_batch": app.state.active_batch,
            "jobs": list(app.state.batch_jobs.keys()),
            "latest": batch_dict(batch) if batch is not None else None,
        },
    }


@router.post("/squall")
async def arm_squall(body: SquallRequest, request: Request):
    state = request.app.state.squall.arm(body.fails)
    label = (
        f"Squall armed: the next {body.fails} simulated provider attempt(s) will fail."
        if body.fails
        else "Squall disarmed."
    )
    return {"squall": state, "detail": label}


@router.delete("/squall")
async def disarm_squall(request: Request):
    return {"squall": request.app.state.squall.arm(0), "detail": "Squall disarmed."}


@router.post("/cache/purge")
async def purge_cache(request: Request):
    return await request.app.state.cache.purge()


@router.post("/breakers/reset")
async def reset_breakers(request: Request):
    registry = request.app.state.registry
    for provider in registry.providers:
        request.app.state.breaker.record_success(provider.name)
    return {"ok": True, "breakers": provider_health(request.app)}
