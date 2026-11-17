from __future__ import annotations

import pytest
from sqlalchemy import select

from app.evals.runner import GauntletRunner, comparison_from_runs
from app.models import EvalBatch, EvalResult, EvalRun, GatewayRequest
from tests.conftest import build_yard, make_settings


def gauntlet_for(yard) -> GauntletRunner:
    return GauntletRunner(
        pipeline=yard.pipeline,
        registry=yard.registry,
        agent=yard.agent,
        session_factory=yard.db.session_factory,
    )


async def test_gauntlet_compares_policies_end_to_end(db):
    yard = await build_yard(db, make_settings())
    gauntlet = gauntlet_for(yard)

    batch, tasks, policies = await gauntlet.create_batch(
        ["thrift", "prime"], label="pytest batch", task_ids=["q01", "m01"]
    )
    assert batch.status == "queued"
    assert batch.tasks_total == 4
    assert policies == ["thrift", "prime"]
    assert [task.id for task in tasks] == ["q01", "m01"]

    await gauntlet.execute(batch.id, policies, tasks)

    async with db.session_factory() as session:
        finished = await session.get(EvalBatch, batch.id)
        runs = (
            await session.scalars(
                select(EvalRun).where(EvalRun.batch_id == batch.id).order_by(EvalRun.started_ms)
            )
        ).all()
        results = (
            await session.scalars(
                select(EvalResult)
                .where(EvalResult.run_id.in_([run.id for run in runs]))
                .order_by(EvalResult.task_id)
            )
        ).all()
        receipts = (await session.scalars(select(GatewayRequest))).all()

    assert finished.status == "completed"
    assert finished.tasks_done == finished.tasks_total == 4

    by_policy = {run.policy: run for run in runs}
    assert by_policy["thrift"].pass_rate == 0.5
    assert by_policy["prime"].pass_rate == 1.0
    assert by_policy["prime"].total_cost_usd > by_policy["thrift"].total_cost_usd
    assert by_policy["thrift"].avg_steps > 0

    m01_thrift = next(row for row in results if row.task_id == "m01" and row.run_id == by_policy["thrift"].id)
    m01_prime = next(row for row in results if row.task_id == "m01" and row.run_id == by_policy["prime"].id)
    assert m01_thrift.passed is False
    assert m01_prime.passed is True
    assert m01_prime.answer == "130"

    comparison = comparison_from_runs(
        [
            {
                "policy": run.policy,
                "status": run.status,
                "total_cost_usd": run.total_cost_usd,
                "total_co2e_g": run.total_co2e_g,
                "pass_rate": run.pass_rate,
                "tool_rate": run.tool_rate,
                "avg_latency_ms": run.avg_latency_ms,
            }
            for run in runs
        ]
    )
    assert comparison["thrift_vs_prime"]["pass_delta_pts"] == -50.0
    assert comparison["thrift_vs_prime"]["cost_saved_pct"] > 0

    assert receipts
    assert all(row.source == "eval" for row in receipts)
    assert all(row.batch_id == batch.id for row in receipts)
    assert all(row.run_id and row.task_id for row in receipts)
    assert {row.task_id for row in receipts} == {"q01", "m01"}


async def test_gauntlet_rejects_unknown_policies_and_tasks(db):
    yard = await build_yard(db, make_settings())
    gauntlet = gauntlet_for(yard)

    with pytest.raises(ValueError, match="unknown policy"):
        await gauntlet.create_batch(["platinum"])
    with pytest.raises(ValueError, match="unknown task id"):
        await gauntlet.create_batch(["thrift"], task_ids=["nope"])


def test_comparison_survives_missing_or_zero_runs():
    assert comparison_from_runs([]) == {}
    assert comparison_from_runs([{"policy": "thrift", "status": "failed"}]) == {}

    comparison = comparison_from_runs(
        [
            {
                "policy": "prime",
                "status": "completed",
                "total_cost_usd": 0.0,
                "total_co2e_g": 0.0,
                "pass_rate": 1.0,
                "tool_rate": 1.0,
                "avg_latency_ms": 10.0,
            },
            {
                "policy": "thrift",
                "status": "completed",
                "total_cost_usd": 0.0,
                "total_co2e_g": 0.0,
                "pass_rate": 0.5,
                "tool_rate": 0.5,
                "avg_latency_ms": 5.0,
            },
        ]
    )
    assert comparison["thrift_vs_prime"]["cost_saved_pct"] == 0.0
    assert comparison["thrift_vs_prime"]["pass_delta_pts"] == -50.0
