"""Run the full gauntlet in simulated mode and fail when routing regresses.

This is the gate CI runs. It is deterministic, needs no provider key, and checks
the three things that make the router worth having:

  * the strong rail stays close to perfect,
  * the router keeps almost all of that accuracy,
  * the router is measurably cheaper than always using the strong rail.

Usage: python scripts/policy_gate.py
Exit code is 0 when the yard passes, 1 when a threshold is missed.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

MIN_PRIME_PASS = 0.95
MIN_ROUTER_PASS = 0.90
MIN_COST_SAVING_PCT = 10.0

ROOT = Path(__file__).resolve().parent.parent


def settings_for(database_url: str) -> Settings:
    from app.config import Settings

    return Settings(
        provider_mode="simulated",
        database_url=database_url,
        serve_frontend=False,
        simulator_latency_min_ms=0,
        simulator_latency_max_ms=0,
        max_retries=0,
        retry_base_ms=0,
        cache_ttl_s=60,
        daily_budget_usd=0,
        gateway_api_key="",
        admin_token="",
        store_prompts=False,
        ledger_key="ci-gate-ledger-key",
        rate_limit_rpm=0,
        log_level="WARNING",
    )


async def run_gate() -> int:
    # The script may be launched from any working directory; find the repo root first.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from sqlalchemy import select

    from app.agent.runner import AgentRunner
    from app.db import Database, LedgerLock
    from app.evals.runner import GauntletRunner, comparison_from_runs
    from app.gateway.breaker import CircuitBreaker
    from app.gateway.cache import MemoryCache, ResponseCache
    from app.gateway.chaos import Squall
    from app.gateway.ledger import Ledger
    from app.gateway.pipeline import GatewayPipeline
    from app.gateway.registry import ProviderRegistry
    from app.models import EvalBatch, EvalRun

    with tempfile.TemporaryDirectory(prefix="switchyard-gate-") as workdir:
        database_url = f"sqlite+aiosqlite:///{(Path(workdir) / 'gate.db').as_posix()}"
        db = Database(database_url)
        await db.init()
        settings = settings_for(database_url)
        registry = ProviderRegistry(settings, Squall())
        cache = ResponseCache(MemoryCache(128), settings.cache_ttl_s, note="ci gate")
        breaker = CircuitBreaker(threshold=3, window_s=60, cooldown_s=20)
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
        try:
            batch, tasks, policies = await gauntlet.create_batch(
                ["thrift", "prime", "yardmaster"], label="CI policy gate"
            )
            print(f"Running {len(tasks)} tasks x {len(policies)} policies...")
            await gauntlet.execute(batch.id, policies, tasks)

            async with db.session_factory() as session:
                finished = await session.get(EvalBatch, batch.id)
                runs = (
                    await session.scalars(
                        select(EvalRun).where(EvalRun.batch_id == batch.id).order_by(EvalRun.policy)
                    )
                ).all()

            rows = [
                {
                    "policy": run.policy,
                    "status": run.status,
                    "pass_rate": run.pass_rate,
                    "avg_score": run.avg_score,
                    "total_cost_usd": run.total_cost_usd,
                    "total_co2e_g": run.total_co2e_g,
                    "tool_rate": run.tool_rate,
                    "avg_latency_ms": run.avg_latency_ms,
                }
                for run in runs
            ]
            by_policy = {row["policy"]: row for row in rows}
            comparison = comparison_from_runs(rows)
            router = by_policy.get("yardmaster", {})
            prime = by_policy.get("prime", {})

            lines = [
                "",
                f"Batch {batch.id} | {finished.status} | {finished.tasks_done}/{finished.tasks_total} runs",
                "",
                f"{'policy':<12} {'pass':>7} {'avg':>7} {'cost':>12} {'p95 lat':>9}",
            ]
            for run in runs:
                lines.append(
                    f"{run.policy:<12} {run.pass_rate:>6.1%} {run.avg_score:>7.2f} "
                    f"{'$' + format(run.total_cost_usd, '.6f'):>12} {run.p95_latency_ms:>7} ms"
                )

            saving = comparison.get("yardmaster_vs_prime", {}).get("cost_saved_pct", 0.0)
            delta = comparison.get("yardmaster_vs_prime", {}).get("pass_delta_pts", 0.0)
            lines += [
                "",
                f"Router vs prime: {saving:+.1f}% of spend saved, {delta:+.1f} pts pass rate.",
                "",
            ]
            report = "\n".join(lines)
            print(report)

            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a", encoding="utf-8") as handle:
                    handle.write("## Switchyard policy gate\n\n")
                    handle.write("```\n" + report.strip() + "\n```\n")

            failures = []
            if finished.status != "completed":
                failures.append(f"batch finished as {finished.status}")
            if prime.get("pass_rate", 0.0) < MIN_PRIME_PASS:
                failures.append(f"prime pass rate {prime.get('pass_rate', 0.0):.1%} < {MIN_PRIME_PASS:.0%}")
            if router.get("pass_rate", 0.0) < MIN_ROUTER_PASS:
                failures.append(
                    f"router pass rate {router.get('pass_rate', 0.0):.1%} < {MIN_ROUTER_PASS:.0%}"
                )
            if saving < MIN_COST_SAVING_PCT:
                failures.append(f"router saved {saving:.1f}% < {MIN_COST_SAVING_PCT:.1f}% required")
            if failures:
                print("Gate failed:")
                for failure in failures:
                    print(f"  - {failure}")
                return 1
            print("Gate passed.")
            return 0
        finally:
            await registry.close()
            await cache.close()
            await db.close()


def main() -> None:
    sys.exit(asyncio.run(run_gate()))


if __name__ == "__main__":
    main()
