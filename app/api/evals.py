from __future__ import annotations

import asyncio
import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import require_admin
from app.api.serialize import batch_dict, batch_full, result_dict, run_dict
from app.evals.dataset import CATEGORIES, TASKS, TASKS_BY_ID
from app.evals.runner import POLICIES, POLICY_TITLES
from app.gateway.router import choose_tier
from app.models import EvalBatch, EvalResult, EvalRun
from app.schemas import EvalBatchRequest

logger = logging.getLogger("switchyard.api.evals")

router = APIRouter(prefix="/api/evals", tags=["gauntlet"])


@router.get("/tasks")
async def tasks():
    return {
        "tasks": [task.public() for task in TASKS],
        "categories": CATEGORIES,
        "policies": list(POLICIES),
        "policy_titles": POLICY_TITLES,
        "total": len(TASKS),
    }


@router.get("/route-map")
async def route_map(policy: str = Query(default="auto", max_length=16)):
    rows = []
    counts = {"thrift": 0, "prime": 0}
    for task in TASKS:
        decision = choose_tier([{"role": "user", "content": task.prompt}], policy=policy)
        counts[decision.tier] += 1
        rows.append(
            {
                "task_id": task.id,
                "category": task.category,
                "difficulty": task.difficulty,
                "prompt": task.prompt,
                "tier": decision.tier,
                "score": decision.score,
                "threshold": decision.features.get("threshold", 0.33),
                "confidence": decision.confidence,
                "summary": decision.summary,
                "reasons": decision.reasons,
            }
        )
    return {
        "policy": policy,
        "threshold": 0.33,
        "counts": counts,
        "tasks": rows,
        "note": "This map is computed from the human turn only, exactly as live traffic is routed.",
    }


@router.post("/batches", status_code=202, dependencies=[Depends(require_admin)])
async def create_batch(body: EvalBatchRequest, request: Request):
    app = request.app
    if app.state.batch_jobs:
        raise HTTPException(
            status_code=409,
            detail="A gauntlet is already running. Wait for it to finish or cancel it first.",
        )
    try:
        batch, tasks, policies = await app.state.gauntlet.create_batch(
            body.policies, body.label, body.task_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = asyncio.create_task(_run_batch(app, batch.id, policies, tasks))
    app.state.batch_jobs[batch.id] = job
    app.state.active_batch = batch.id
    return {"batch": batch_dict(batch), "tasks_per_policy": len(tasks), "policies": policies}


async def _run_batch(app, batch_id: str, policies: list[str], tasks) -> None:
    try:
        await app.state.gauntlet.execute(batch_id, policies, tasks)
    except asyncio.CancelledError:
        await _mark_interrupted(app, batch_id, "The yard stopped while this gauntlet was in flight.")
        raise
    except Exception as exc:
        logger.exception("gauntlet job %s crashed", batch_id)
        await _mark_interrupted(app, batch_id, f"{exc.__class__.__name__}: {exc}")
    finally:
        app.state.batch_jobs.pop(batch_id, None)
        if app.state.active_batch == batch_id:
            app.state.active_batch = None
        app.state.chain_cache = None


async def _mark_interrupted(app, batch_id: str, reason: str) -> None:
    from app.gateway.ledger import now_ms

    async with app.state.db.session_factory() as session:
        batch = await session.get(EvalBatch, batch_id)
        if batch is not None and batch.status in {"queued", "running", "cancelling"}:
            batch.status = "cancelled"
            batch.error = reason
            batch.completed_ms = now_ms()
        runs = (
            await session.scalars(
                select(EvalRun).where(EvalRun.batch_id == batch_id, EvalRun.status.in_(("queued", "running")))
            )
        ).all()
        for run in runs:
            run.status = "cancelled"
            run.error = reason
            run.completed_ms = now_ms()
        await session.commit()


@router.get("/batches")
async def list_batches(request: Request, limit: int = Query(default=15, ge=1, le=50)):
    async with request.app.state.db.session_factory() as session:
        batches = (
            await session.scalars(select(EvalBatch).order_by(EvalBatch.created_ms.desc()).limit(limit))
        ).all()
        runs = []
        if batches:
            runs = (
                await session.scalars(
                    select(EvalRun)
                    .where(EvalRun.batch_id.in_([batch.id for batch in batches]))
                    .order_by(EvalRun.started_ms.asc())
                )
            ).all()
    grouped: dict[str, list[EvalRun]] = {}
    for run in runs:
        grouped.setdefault(run.batch_id, []).append(run)
    return {
        "items": [batch_full(batch, grouped.get(batch.id, [])) for batch in batches],
        "active_batch": request.app.state.active_batch,
        "running": bool(request.app.state.batch_jobs),
        "policies": list(POLICIES),
        "policy_titles": POLICY_TITLES,
    }


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, request: Request):
    async with request.app.state.db.session_factory() as session:
        batch = await session.get(EvalBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"batch {batch_id} not found")
        runs = (
            await session.scalars(
                select(EvalRun).where(EvalRun.batch_id == batch_id).order_by(EvalRun.started_ms.asc())
            )
        ).all()
    return batch_full(batch, runs)


@router.post("/batches/{batch_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_batch(batch_id: str, request: Request):
    async with request.app.state.db.session_factory() as session:
        batch = await session.get(EvalBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"batch {batch_id} not found")
        if batch.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail=f"batch is already {batch.status}; nothing to cancel")
        batch.status = "cancelling"
        await session.commit()
    return {"ok": True, "batch_id": batch_id, "detail": "Stopping after the current task."}


@router.get("/batches/{batch_id}/results")
async def batch_results(
    batch_id: str,
    request: Request,
    policy: str = Query(default="", max_length=16),
    passed: str = Query(default="", max_length=8),
    limit: int = Query(default=300, ge=1, le=1000),
):
    async with request.app.state.db.session_factory() as session:
        batch = await session.get(EvalBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"batch {batch_id} not found")
        run_query = select(EvalRun).where(EvalRun.batch_id == batch_id)
        if policy:
            run_query = run_query.where(EvalRun.policy == policy)
        runs = (await session.scalars(run_query.order_by(EvalRun.started_ms.asc()))).all()
        run_ids = [run.id for run in runs]
        if run_ids:
            result_query = select(EvalResult).where(EvalResult.run_id.in_(run_ids))
            if passed in {"true", "false"}:
                result_query = result_query.where(EvalResult.passed.is_(passed == "true"))
            results = (
                await session.scalars(result_query.order_by(EvalResult.created_ms.asc()).limit(limit))
            ).all()
        else:
            results = []
    run_by_id = {run.id: run_dict(run) for run in runs}
    return {
        "batch": batch_dict(batch),
        "runs": list(run_by_id.values()),
        "results": [
            {**result_dict(row), "policy": run_by_id.get(row.run_id, {}).get("policy")} for row in results
        ],
        "total": len(results),
    }


@router.get("/batches/{batch_id}/results.csv")
async def export_results(batch_id: str, request: Request):
    async with request.app.state.db.session_factory() as session:
        batch = await session.get(EvalBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail=f"batch {batch_id} not found")
        runs = (await session.scalars(select(EvalRun).where(EvalRun.batch_id == batch_id))).all()
        run_by_id = {run.id: run for run in runs}
        results = (
            await session.scalars(
                select(EvalResult)
                .where(EvalResult.run_id.in_(list(run_by_id.keys()) or [""]))
                .order_by(EvalResult.created_ms.asc())
            )
        ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "batch_id",
            "policy",
            "task_id",
            "category",
            "difficulty",
            "passed",
            "answer_score",
            "tool_score",
            "step_score",
            "total_score",
            "steps_count",
            "cost_usd",
            "latency_ms",
            "answer",
            "expected",
            "error",
        ]
    )
    for row in results:
        run = run_by_id.get(row.run_id)
        writer.writerow(
            [
                batch_id,
                run.policy if run else "",
                row.task_id,
                row.category,
                row.difficulty,
                row.passed,
                row.answer_score,
                row.tool_score,
                row.step_score,
                row.total_score,
                row.steps_count,
                row.cost_usd,
                row.latency_ms,
                row.answer,
                row.expected,
                row.error or "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="switchyard-{batch_id}.csv"'},
    )


@router.get("/tasks/{task_id}")
async def task_detail(task_id: str):
    task = TASKS_BY_ID.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    payload = task.public()
    payload["note"] = task.note
    decision = choose_tier([{"role": "user", "content": task.prompt}], policy="auto")
    payload["route"] = decision.as_dict()
    return payload
