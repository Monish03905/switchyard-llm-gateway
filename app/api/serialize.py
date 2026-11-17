from __future__ import annotations

import json

from app.models import EvalBatch, EvalRun, GatewayRequest


def safe_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def request_summary(row: GatewayRequest) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at,
        "created_ms": row.created_ms,
        "source": row.source,
        "policy": row.policy,
        "tier": row.tier,
        "provider": row.provider,
        "model": row.model,
        "status": row.status,
        "cache_hit": row.cache_hit,
        "fallback_used": row.fallback_used,
        "attempts": row.attempts,
        "tokens": row.total_tokens,
        "cost_usd": row.cost_usd,
        "saved_usd": row.saved_usd,
        "co2e_g": row.co2e_g,
        "saved_co2e_g": row.saved_co2e_g,
        "latency_ms": row.latency_ms,
        "route_confidence": row.route_confidence,
        "route_reason": row.route_reason,
        "prompt_preview": row.prompt_preview,
        "response_preview": row.response_preview,
        "error": row.error,
        "batch_id": row.batch_id,
        "run_id": row.run_id,
        "task_id": row.task_id,
    }


def request_detail(row: GatewayRequest) -> dict:
    detail = request_summary(row)
    detail.update(
        {
            "requested_model": row.requested_model,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "baseline_cost_usd": row.baseline_cost_usd,
            "energy_wh": row.energy_wh,
            "baseline_energy_wh": row.baseline_energy_wh,
            "baseline_co2e_g": row.baseline_co2e_g,
            "features": safe_json(row.features_json, {}),
            "attempts_detail": safe_json(row.attempts_json, []),
            "prompt_hash": row.prompt_hash,
            "prompt_text": row.prompt_text,
            "response_text": row.response_text,
            "prev_hash": row.prev_hash,
            "entry_hash": row.entry_hash,
            "seq": row.seq,
            "client": row.client,
        }
    )
    return detail


def run_dict(run: EvalRun) -> dict:
    return {
        "id": run.id,
        "batch_id": run.batch_id,
        "policy": run.policy,
        "mode": run.mode,
        "provider": run.provider,
        "model": run.model,
        "status": run.status,
        "tasks_total": run.tasks_total,
        "tasks_done": run.tasks_done,
        "passed": run.passed,
        "pass_rate": run.pass_rate,
        "avg_score": run.avg_score,
        "tool_rate": run.tool_rate,
        "total_cost_usd": run.total_cost_usd,
        "total_co2e_g": run.total_co2e_g,
        "total_energy_wh": run.total_energy_wh,
        "total_tokens": run.total_tokens,
        "avg_latency_ms": run.avg_latency_ms,
        "p95_latency_ms": run.p95_latency_ms,
        "avg_steps": run.avg_steps,
        "started_ms": run.started_ms,
        "completed_ms": run.completed_ms,
        "error": run.error,
        "progress": round(run.tasks_done / run.tasks_total, 4) if run.tasks_total else 0.0,
    }


def batch_dict(batch: EvalBatch, runs: list[EvalRun] | None = None) -> dict:
    payload = {
        "id": batch.id,
        "created_at": batch.created_at,
        "created_ms": batch.created_ms,
        "completed_ms": batch.completed_ms,
        "label": batch.label,
        "mode": batch.mode,
        "status": batch.status,
        "policies": safe_json(batch.policies_json, []),
        "tasks_total": batch.tasks_total,
        "tasks_done": batch.tasks_done,
        "progress": round(batch.tasks_done / batch.tasks_total, 4) if batch.tasks_total else 0.0,
        "error": batch.error,
    }
    if runs is not None:
        payload["runs"] = [run_dict(run) for run in runs]
    return payload


def batch_full(batch: EvalBatch, runs: list[EvalRun]) -> dict:
    from app.evals.runner import comparison_from_runs

    payload = batch_dict(batch, runs)
    payload["comparison"] = comparison_from_runs(payload["runs"])
    return payload


def result_dict(row) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "task_id": row.task_id,
        "category": row.category,
        "difficulty": row.difficulty,
        "passed": row.passed,
        "answer_score": row.answer_score,
        "tool_score": row.tool_score,
        "step_score": row.step_score,
        "total_score": row.total_score,
        "answer": row.answer,
        "expected": row.expected,
        "steps": safe_json(row.steps_json, []),
        "request_ids": safe_json(row.request_ids_json, []),
        "cost_usd": row.cost_usd,
        "latency_ms": row.latency_ms,
        "steps_count": row.steps_count,
        "error": row.error,
    }
