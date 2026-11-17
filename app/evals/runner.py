from __future__ import annotations

import json
import logging
import math

from sqlalchemy import select

from app.agent.runner import AgentRunner
from app.agent.tools import TOOL_NAMES
from app.evals.dataset import TASKS, TASKS_BY_ID, EvalTask
from app.evals.scorers import score_task
from app.gateway.ledger import iso_from_ms, new_batch_id, new_run_id, now_ms
from app.gateway.pipeline import GatewayPipeline
from app.gateway.registry import ProviderRegistry
from app.models import EvalBatch, EvalResult, EvalRun

logger = logging.getLogger("switchyard.evals")

POLICIES = ("thrift", "prime", "yardmaster")
POLICY_TO_MODEL = {"thrift": "thrift", "prime": "prime", "yardmaster": "auto"}
POLICY_TITLES = {
    "thrift": "Thrift — always the cheap rail",
    "prime": "Prime — always the strong rail",
    "yardmaster": "Yardmaster — the router decides",
}


class GauntletRunner:
    def __init__(
        self,
        *,
        pipeline: GatewayPipeline,
        registry: ProviderRegistry,
        agent: AgentRunner,
        session_factory,
    ):
        self.pipeline = pipeline
        self.registry = registry
        self.agent = agent
        self.session_factory = session_factory

    async def create_batch(
        self,
        policies: list[str],
        label: str = "",
        task_ids: list[str] | None = None,
    ) -> tuple[EvalBatch, list[EvalTask], list[str]]:
        chosen_policies = []
        for policy in policies or list(POLICIES):
            clean = policy.strip().lower()
            if clean not in POLICIES:
                raise ValueError(f"unknown policy '{policy}'; choose from {', '.join(POLICIES)}")
            if clean not in chosen_policies:
                chosen_policies.append(clean)
        if not chosen_policies:
            raise ValueError("at least one policy is required")

        if task_ids:
            unknown = [task_id for task_id in task_ids if task_id not in TASKS_BY_ID]
            if unknown:
                raise ValueError(f"unknown task id(s): {', '.join(unknown[:5])}")
            chosen_tasks = [TASKS_BY_ID[task_id] for task_id in task_ids]
        else:
            chosen_tasks = list(TASKS)

        created = now_ms()
        batch = EvalBatch(
            id=new_batch_id(),
            created_at=iso_from_ms(created),
            created_ms=created,
            label=label.strip()[:120] or "Unlabelled run",
            mode=self.registry.mode,
            status="queued",
            policies_json=json.dumps(chosen_policies),
            tasks_total=len(chosen_tasks) * len(chosen_policies),
            tasks_done=0,
        )
        async with self.session_factory() as session:
            session.add(batch)
            await session.commit()
        return batch, chosen_tasks, chosen_policies

    async def execute(self, batch_id: str, policies: list[str], tasks: list[EvalTask]) -> None:
        try:
            await self._execute(batch_id, policies, tasks)
        except Exception as exc:  # keep the background job from dying silently
            logger.exception("gauntlet batch %s failed", batch_id)
            async with self.session_factory() as session:
                batch = await session.get(EvalBatch, batch_id)
                if batch is not None:
                    batch.status = "failed"
                    batch.error = f"{exc.__class__.__name__}: {exc}"
                    batch.completed_ms = now_ms()
                runs = (
                    await session.scalars(
                        select(EvalRun).where(
                            EvalRun.batch_id == batch_id,
                            EvalRun.status.in_(("queued", "running")),
                        )
                    )
                ).all()
                for run in runs:
                    run.status = "failed"
                    run.error = f"{exc.__class__.__name__}: {exc}"
                    run.completed_ms = now_ms()
                await session.commit()

    async def _execute(self, batch_id: str, policies: list[str], tasks: list[EvalTask]) -> None:
        async with self.session_factory() as session:
            batch = await session.get(EvalBatch, batch_id)
            if batch is None:
                return
            batch.status = "running"
            await session.commit()

        cancelled = False
        for policy in policies:
            if cancelled:
                break
            run_id = new_run_id()
            started = now_ms()
            model = self._model_label(policy)
            run = EvalRun(
                id=run_id,
                batch_id=batch_id,
                policy=policy,
                mode=self.registry.mode,
                provider=self.registry.primary.name,
                model=model,
                status="running",
                tasks_total=len(tasks),
                started_ms=started,
            )
            async with self.session_factory() as session:
                session.add(run)
                await session.commit()

            latencies: list[int] = []
            answer_scores: list[float] = []
            tool_scores: list[float] = []
            step_scores: list[float] = []
            step_counts: list[int] = []
            passed = 0
            cost_total = 0.0
            co2_total = 0.0
            energy_total = 0.0
            tokens_total = 0

            for index, task in enumerate(tasks, start=1):
                async with self.session_factory() as session:
                    fresh = await session.get(EvalBatch, batch_id)
                    if fresh is not None and fresh.status == "cancelling":
                        cancelled = True
                        break

                outcome = await self.agent.run(
                    task.prompt,
                    policy=POLICY_TO_MODEL[policy],
                    tools=TOOL_NAMES,
                    max_steps=task.max_steps,
                    source="eval",
                    batch_id=batch_id,
                    run_id=run_id,
                    task_id=task.id,
                )
                score = score_task(
                    task,
                    answer=outcome.answer,
                    trace=outcome.trace,
                    error=outcome.error,
                )
                if score.passed:
                    passed += 1
                latencies.append(outcome.latency_ms)
                answer_scores.append(score.answer)
                tool_scores.append(score.tools)
                step_scores.append(score.steps)
                step_counts.append(outcome.steps_count)
                cost_total += outcome.cost_usd
                co2_total += outcome.co2e_g
                energy_total += outcome.energy_wh
                tokens_total += outcome.input_tokens + outcome.output_tokens
                created = now_ms()

                result = EvalResult(
                    run_id=run_id,
                    task_id=task.id,
                    category=task.category,
                    difficulty=task.difficulty,
                    passed=score.passed,
                    answer_score=score.answer,
                    tool_score=score.tools,
                    step_score=score.steps,
                    total_score=score.total,
                    answer=outcome.answer,
                    expected=task.expected,
                    steps_json=json.dumps(outcome.trace),
                    request_ids_json=json.dumps(outcome.request_ids),
                    cost_usd=round(outcome.cost_usd, 8),
                    latency_ms=outcome.latency_ms,
                    steps_count=outcome.steps_count,
                    error=outcome.error or (None if score.passed else score.detail),
                    created_ms=created,
                )
                async with self.session_factory() as session:
                    session.add(result)
                    updated_run = await session.get(EvalRun, run_id)
                    updated_batch = await session.get(EvalBatch, batch_id)
                    if updated_run is not None:
                        _apply_run_progress(
                            updated_run,
                            done=index,
                            passed=passed,
                            answer_scores=answer_scores,
                            tool_scores=tool_scores,
                            step_scores=step_scores,
                            step_counts=step_counts,
                            latencies=latencies,
                            cost_total=cost_total,
                            co2_total=co2_total,
                            tokens_total=tokens_total,
                        )
                    if updated_batch is not None:
                        updated_batch.tasks_done = min(
                            updated_batch.tasks_total, updated_batch.tasks_done + 1
                        )
                    await session.commit()

            async with self.session_factory() as session:
                final_run = await session.get(EvalRun, run_id)
                if final_run is not None:
                    _apply_run_progress(
                        final_run,
                        done=len(latencies),
                        passed=passed,
                        answer_scores=answer_scores,
                        tool_scores=tool_scores,
                        step_scores=step_scores,
                        step_counts=step_counts,
                        latencies=latencies,
                        cost_total=cost_total,
                        co2_total=co2_total,
                        tokens_total=tokens_total,
                    )
                    final_run.p95_latency_ms = _percentile(latencies, 0.95)
                    final_run.total_energy_wh = round(energy_total, 6)
                    final_run.status = "cancelled" if cancelled else "completed"
                    final_run.completed_ms = now_ms()
                await session.commit()

        async with self.session_factory() as session:
            final_batch = await session.get(EvalBatch, batch_id)
            if final_batch is not None:
                final_batch.status = "cancelled" if cancelled else "completed"
                final_batch.completed_ms = now_ms()
            await session.commit()

    def _model_label(self, policy: str) -> str:
        if policy == "thrift":
            return self.registry.primary.model_for("thrift")
        if policy == "prime":
            return self.registry.primary.model_for("prime")
        return "router"


def _apply_run_progress(
    run: EvalRun,
    *,
    done: int,
    passed: int,
    answer_scores: list[float],
    tool_scores: list[float],
    step_scores: list[float],
    step_counts: list[int],
    latencies: list[int],
    cost_total: float,
    co2_total: float,
    tokens_total: int,
) -> None:
    run.tasks_done = done
    run.passed = passed
    run.pass_rate = round(passed / done, 4) if done else 0.0
    run.avg_score = (
        round(
            _mean(
                0.6 * a + 0.25 * t + 0.15 * s
                for a, t, s in zip(answer_scores, tool_scores, step_scores, strict=False)
            ),
            4,
        )
        if done
        else 0.0
    )
    run.tool_rate = round(_mean(tool_scores), 4) if done else 0.0
    run.total_cost_usd = round(cost_total, 8)
    run.total_co2e_g = round(co2_total, 6)
    run.total_tokens = tokens_total
    run.avg_latency_ms = round(_mean(latencies), 1) if done else 0.0
    run.avg_steps = round(_mean(step_counts), 2) if done else 0.0


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return int(ordered[index])


def comparison_from_runs(runs: list[dict]) -> dict:
    by_policy = {run["policy"]: run for run in runs if run.get("status") != "failed"}
    prime = by_policy.get("prime")
    thrift = by_policy.get("thrift")
    yard = by_policy.get("yardmaster")
    result: dict = {}
    if prime and yard:
        result["yardmaster_vs_prime"] = {
            "cost_saved_pct": _pct(prime["total_cost_usd"] - yard["total_cost_usd"], prime["total_cost_usd"]),
            "pass_delta_pts": round((yard["pass_rate"] - prime["pass_rate"]) * 100, 1),
            "tool_delta_pts": round((yard["tool_rate"] - prime["tool_rate"]) * 100, 1),
            "co2_saved_pct": _pct(prime["total_co2e_g"] - yard["total_co2e_g"], prime["total_co2e_g"]),
            "latency_delta_ms": round(yard["avg_latency_ms"] - prime["avg_latency_ms"], 1),
        }
    if prime and thrift:
        result["thrift_vs_prime"] = {
            "cost_saved_pct": _pct(
                prime["total_cost_usd"] - thrift["total_cost_usd"], prime["total_cost_usd"]
            ),
            "pass_delta_pts": round((thrift["pass_rate"] - prime["pass_rate"]) * 100, 1),
        }
    if yard and thrift:
        result["yardmaster_vs_thrift"] = {
            "pass_delta_pts": round((yard["pass_rate"] - thrift["pass_rate"]) * 100, 1),
            "cost_delta_pct": _pct(
                yard["total_cost_usd"] - thrift["total_cost_usd"], thrift["total_cost_usd"]
            ),
        }
    return result


def _pct(delta: float, base: float) -> float:
    if not base:
        return 0.0
    return round((delta / base) * 100, 1)
