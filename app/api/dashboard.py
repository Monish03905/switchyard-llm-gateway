from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import case, func, or_, select

from app.api.deps import require_admin
from app.api.serialize import batch_full, request_detail, request_summary
from app.api.telemetry import chain_state, provider_health, uptime_seconds
from app.gateway.ledger import now_ms
from app.gateway.providers.base import ProviderError
from app.models import EvalBatch, EvalRun, GatewayRequest

router = APIRouter(tags=["dashboard"])


@router.get("/api/overview")
async def overview(request: Request, hours: int = Query(default=24, ge=1, le=168)):
    app = request.app
    settings = app.state.settings
    registry = app.state.registry
    end = now_ms()
    start = end - hours * 3_600_000
    window = GatewayRequest.created_ms >= start

    async with app.state.db.session_factory() as session:
        totals = (
            await session.execute(
                select(
                    func.count(GatewayRequest.seq),
                    func.coalesce(func.sum(GatewayRequest.cost_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.baseline_cost_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.total_tokens), 0),
                    func.coalesce(func.sum(GatewayRequest.co2e_g), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_co2e_g), 0.0),
                    func.coalesce(func.sum(case((GatewayRequest.cache_hit.is_(True), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((GatewayRequest.fallback_used.is_(True), 1), else_=0)), 0),
                ).where(window)
            )
        ).one()

        status_rows = (
            await session.execute(
                select(GatewayRequest.status, func.count(GatewayRequest.seq))
                .where(window)
                .group_by(GatewayRequest.status)
            )
        ).all()
        tier_rows = (
            await session.execute(
                select(GatewayRequest.tier, func.count(GatewayRequest.seq))
                .where(window, GatewayRequest.status == "ok", GatewayRequest.cache_hit.is_(False))
                .group_by(GatewayRequest.tier)
            )
        ).all()
        source_rows = (
            await session.execute(
                select(GatewayRequest.source, func.count(GatewayRequest.seq))
                .where(window)
                .group_by(GatewayRequest.source)
            )
        ).all()
        latency_rows = (
            await session.scalars(
                select(GatewayRequest.latency_ms)
                .where(window, GatewayRequest.status == "ok")
                .order_by(GatewayRequest.created_ms.desc())
                .limit(2000)
            )
        ).all()
        timeline_rows = (
            await session.execute(
                select(GatewayRequest.created_ms, GatewayRequest.cost_usd)
                .where(window, GatewayRequest.status == "ok")
                .order_by(GatewayRequest.created_ms.asc())
            )
        ).all()
        recent = (
            await session.scalars(select(GatewayRequest).order_by(GatewayRequest.created_ms.desc()).limit(12))
        ).all()
        lifetime = (
            await session.execute(
                select(
                    func.count(GatewayRequest.seq),
                    func.coalesce(func.sum(GatewayRequest.cost_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_usd), 0.0),
                    func.coalesce(func.sum(GatewayRequest.saved_co2e_g), 0.0),
                    func.coalesce(func.sum(GatewayRequest.total_tokens), 0),
                    func.min(GatewayRequest.created_ms),
                )
            )
        ).one()
        batch = await session.scalar(select(EvalBatch).order_by(EvalBatch.created_ms.desc()).limit(1))
        runs = []
        if batch is not None:
            runs = (
                await session.scalars(
                    select(EvalRun).where(EvalRun.batch_id == batch.id).order_by(EvalRun.started_ms.asc())
                )
            ).all()

    count, cost, baseline, saved, tokens, co2, saved_co2, cache_hits, fallbacks = totals
    statuses = {status: int(value) for status, value in status_rows}
    ok = statuses.get("ok", 0)

    stats = _window_stats(
        count=count,
        ok=ok,
        errors=statuses.get("error", 0),
        blocked=statuses.get("blocked", 0),
        cost=float(cost),
        baseline=float(baseline),
        saved=float(saved),
        tokens=int(tokens),
        co2=float(co2),
        saved_co2=float(saved_co2),
        cache_hits=int(cache_hits),
        fallbacks=int(fallbacks),
        latencies=[int(value) for value in latency_rows],
    )

    route_mix = {tier: int(value) for tier, value in tier_rows}
    route_mix["cache"] = int(cache_hits)
    route_mix["total"] = sum(route_mix.get(t, 0) for t in ("thrift", "prime", "cache"))

    points = _timeline(timeline_rows, start=start, end=end, hours=hours)
    budget = await app.state.pipeline._budget_state()
    cache = await app.state.cache.stats()
    chain = await chain_state(app)

    return {
        "meta": {
            "generated_ms": end,
            "window_hours": hours,
            "mode": registry.mode,
            "simulated": registry.mode == "simulated",
            "mode_note": registry.note,
            "version": settings.app_version,
            "environment": settings.app_env,
            "uptime_s": uptime_seconds(app),
            "privacy": {
                "store_prompts": settings.store_prompts,
                "default_ledger_key": settings.using_default_ledger_key,
            },
            "auth": {
                "gateway_key_required": bool(settings.gateway_api_key),
                "admin_token_required": bool(settings.admin_token),
            },
            "rate_limit_rpm": settings.rate_limit_rpm,
        },
        "stats": stats,
        "lifetime": {
            "requests": int(lifetime[0]),
            "cost_usd": round(float(lifetime[1]), 8),
            "saved_usd": round(float(lifetime[2]), 8),
            "saved_co2e_g": round(float(lifetime[3]), 6),
            "tokens": int(lifetime[4]),
            "first_ms": lifetime[5],
        },
        "timeline": {"bins": 24, "points": points},
        "route_mix": route_mix,
        "source_mix": [{"source": source, "count": int(value)} for source, value in source_rows],
        "guardrails": {
            "budget": budget,
            "cache": cache,
            "breakers": provider_health(app),
            "squall": app.state.squall.snapshot(),
            "limiter": app.state.limiter.snapshot(),
            "chain": chain,
        },
        "providers": registry.info(),
        "recent": [request_summary(row) for row in recent],
        "last_batch": batch_full(batch, runs) if batch is not None else None,
    }


@router.get("/api/requests")
async def list_requests(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    status: str = Query(default="", max_length=16),
    tier: str = Query(default="", max_length=16),
    source: str = Query(default="", max_length=16),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    conditions = _request_conditions(hours, status, tier, source, q)
    async with request.app.state.db.session_factory() as session:
        total = await session.scalar(select(func.count(GatewayRequest.seq)).where(*conditions))
        rows = (
            await session.scalars(
                select(GatewayRequest)
                .where(*conditions)
                .order_by(GatewayRequest.created_ms.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    return {
        "items": [request_summary(row) for row in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/requests/export.csv")
async def export_requests(
    request: Request,
    hours: int = Query(default=168, ge=1, le=8760),
    status: str = Query(default="", max_length=16),
    tier: str = Query(default="", max_length=16),
    source: str = Query(default="", max_length=16),
    q: str = Query(default="", max_length=120),
):
    conditions = _request_conditions(hours, status, tier, source, q)
    async with request.app.state.db.session_factory() as session:
        rows = (
            await session.scalars(
                select(GatewayRequest)
                .where(*conditions)
                .order_by(GatewayRequest.created_ms.desc())
                .limit(5000)
            )
        ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "id",
            "source",
            "policy",
            "tier",
            "provider",
            "model",
            "status",
            "cache_hit",
            "fallback_used",
            "attempts",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "baseline_cost_usd",
            "saved_usd",
            "co2e_g",
            "saved_co2e_g",
            "latency_ms",
            "route_confidence",
            "route_reason",
            "prompt_hash",
            "entry_hash",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at,
                row.id,
                row.source,
                row.policy,
                row.tier,
                row.provider,
                row.model,
                row.status,
                row.cache_hit,
                row.fallback_used,
                row.attempts,
                row.input_tokens,
                row.output_tokens,
                row.cost_usd,
                row.baseline_cost_usd,
                row.saved_usd,
                row.co2e_g,
                row.saved_co2e_g,
                row.latency_ms,
                row.route_confidence,
                row.route_reason,
                row.prompt_hash,
                row.entry_hash,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="switchyard-ledger.csv"'},
    )


@router.get("/api/requests/{request_id}")
async def get_request(request_id: str, request: Request):
    async with request.app.state.db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest).where(GatewayRequest.id == request_id))
    if row is None:
        raise HTTPException(status_code=404, detail=f"receipt {request_id} not found")
    return request_detail(row)


@router.get("/api/providers")
async def providers(request: Request):
    registry = request.app.state.registry
    return {
        **registry.info(),
        "health": provider_health(request.app),
        "fallback_provider": request.app.state.settings.fallback_provider or None,
        "chaos": request.app.state.squall.snapshot(),
    }


@router.post("/api/providers/{name}/probe", dependencies=[Depends(require_admin)])
async def probe_provider(name: str, request: Request):
    registry = request.app.state.registry
    provider = next((item for item in registry.providers if item.name == name), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"unknown provider '{name}'")
    try:
        result = await provider.probe()
        request.app.state.breaker.record_success(name)
    except ProviderError as exc:
        request.app.state.breaker.record_failure(name)
        result = {"ok": False, "provider": name, "error": exc.message}
    except Exception as exc:
        request.app.state.breaker.record_failure(name)
        result = {"ok": False, "provider": name, "error": f"{exc.__class__.__name__}"}
    result["checked_ms"] = now_ms()
    request.app.state.probes[name] = result
    return result


@router.get("/api/ledger/verify")
async def verify_ledger(request: Request):
    return await chain_state(request.app, force=True)


@router.get("/api/ledger/export.csv")
async def export_ledger(request: Request):
    async with request.app.state.db.session_factory() as session:
        rows = (
            await session.scalars(select(GatewayRequest).order_by(GatewayRequest.seq.asc()).limit(20_000))
        ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "seq",
            "id",
            "created_at",
            "source",
            "tier",
            "model",
            "status",
            "cost_usd",
            "saved_usd",
            "co2e_g",
            "latency_ms",
            "prompt_hash",
            "prev_hash",
            "entry_hash",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.seq,
                row.id,
                row.created_at,
                row.source,
                row.tier,
                row.model,
                row.status,
                row.cost_usd,
                row.saved_usd,
                row.co2e_g,
                row.latency_ms,
                row.prompt_hash,
                row.prev_hash,
                row.entry_hash,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="switchyard-chain.csv"'},
    )


def _request_conditions(hours: int, status: str, tier: str, source: str, q: str) -> list:
    start = now_ms() - hours * 3_600_000
    conditions = [GatewayRequest.created_ms >= start]
    if status:
        conditions.append(GatewayRequest.status == status)
    if tier:
        conditions.append(GatewayRequest.tier == tier)
    if source:
        conditions.append(GatewayRequest.source == source)
    if q:
        needle = f"%{q.strip()[:80]}%"
        conditions.append(
            or_(
                GatewayRequest.prompt_preview.like(needle),
                GatewayRequest.route_reason.like(needle),
                GatewayRequest.model.like(needle),
                GatewayRequest.id.like(needle),
            )
        )
    return conditions


def _window_stats(
    *,
    count: int,
    ok: int,
    errors: int,
    blocked: int,
    cost: float,
    baseline: float,
    saved: float,
    tokens: int,
    co2: float,
    saved_co2: float,
    cache_hits: int,
    fallbacks: int,
    latencies: list[int],
) -> dict:
    ordered = sorted(latencies)
    return {
        "requests": int(count),
        "ok": int(ok),
        "errors": int(errors),
        "blocked": int(blocked),
        "success_rate": round(ok / count, 4) if count else 0.0,
        "cache_hits": int(cache_hits),
        "cache_hit_rate": round(cache_hits / ok, 4) if ok else 0.0,
        "fallbacks": int(fallbacks),
        "tokens": int(tokens),
        "cost_usd": round(cost, 8),
        "baseline_cost_usd": round(baseline, 8),
        "saved_usd": round(saved, 8),
        "saved_pct": round(saved / baseline * 100, 1) if baseline else 0.0,
        "co2e_g": round(co2, 6),
        "saved_co2e_g": round(saved_co2, 6),
        "latency_avg_ms": round(sum(ordered) / len(ordered), 1) if ordered else 0.0,
        "latency_p50_ms": _percentile(ordered, 0.5),
        "latency_p95_ms": _percentile(ordered, 0.95),
    }


def _percentile(ordered: list[int], q: float) -> int:
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, int(q * len(ordered) + 0.999) - 1))
    return int(ordered[index])


def _timeline(rows, *, start: int, end: int, hours: int) -> list[dict]:
    bins = 24
    width = max(1, (end - start) // bins)
    points = []
    for index in range(bins):
        stamp = start + index * width
        points.append(
            {
                "t": stamp,
                "label": _stamp_label(stamp, hours),
                "requests": 0,
                "cost_usd": 0.0,
            }
        )
    for created_ms, cost in rows:
        index = min(bins - 1, max(0, (int(created_ms) - start) // width))
        points[index]["requests"] += 1
        points[index]["cost_usd"] = round(points[index]["cost_usd"] + float(cost or 0.0), 8)
    return points


def _stamp_label(ms: int, hours: int) -> str:
    moment = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return moment.strftime("%H:%M") if hours <= 24 else moment.strftime("%d %b %H:%M")
