from __future__ import annotations

import pytest
from sqlalchemy import select

from app.gateway.pipeline import ChatCall, GatewayError
from app.gateway.providers.base import Completion, ProviderError
from app.gateway.registry import Candidate
from app.models import GatewayRequest
from tests.conftest import build_yard, make_settings


class FakeProvider:
    kind = "fake"

    def __init__(self, name: str, *, fail_times: int = 0, retryable: bool = True, text: str = "fake answer"):
        self.name = name
        self.tier_models = {"thrift": "sim-shunter", "prime": "sim-mainline"}
        self.fail_times = fail_times
        self.retryable = retryable
        self.text = text
        self.calls = 0

    def model_for(self, tier: str) -> str:
        return self.tier_models[tier]

    async def chat(self, messages, model, temperature, max_tokens, request_id):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError(
                f"{self.name} is unavailable",
                provider=self.name,
                retryable=self.retryable,
                status_code=503,
            )
        return Completion(
            text=self.text,
            provider=self.name,
            model=model,
            input_tokens=12,
            output_tokens=6,
            latency_ms=2,
        )

    async def probe(self):
        return {"ok": True, "provider": self.name}

    async def close(self):
        return None


class FakeRegistry:
    mode = "simulated"

    def __init__(self, providers):
        self.providers = providers
        self.primary = providers[0]
        self.secondary = providers[1] if len(providers) > 1 else None

    def baseline_model(self) -> str:
        return "sim-mainline"

    def candidates(self, tier: str, pinned_model=None) -> list[Candidate]:
        other = "prime" if tier == "thrift" else "thrift"
        ordered = [Candidate(provider, provider.model_for(tier), tier) for provider in self.providers]
        ordered += [Candidate(provider, provider.model_for(other), other) for provider in self.providers]
        return ordered

    async def close(self):
        return None


async def test_successful_call_records_a_receipt(db):
    yard = await build_yard(db, make_settings())
    outcome = await yard.pipeline.complete(
        ChatCall([{"role": "user", "content": "What is 47 * 13?"}]), source="test"
    )

    assert outcome.status == "ok"
    assert outcome.tier == "thrift"
    assert outcome.model == "sim-shunter"
    assert outcome.cost_usd > 0
    assert outcome.baseline_cost_usd > outcome.cost_usd
    assert outcome.saved_usd > 0
    assert outcome.route.reasons

    async with db.session_factory() as session:
        rows = (await session.scalars(select(GatewayRequest))).all()
        report = await yard.ledger.verify(session)
    assert len(rows) == 1
    assert rows[0].id == outcome.request_id
    assert rows[0].source == "test"
    assert report["ok"] is True


async def test_cache_hit_is_free_and_happens_once(db):
    yard = await build_yard(db, make_settings())

    first = await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 15% of 240?"}]))
    second = await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 15% of 240?"}]))

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.cost_usd == 0.0
    assert second.saved_usd > 0
    assert second.attempts[0]["status"] == "cache"
    assert second.text == first.text

    stats = await yard.cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1

    bypass = await yard.pipeline.complete(
        ChatCall([{"role": "user", "content": "What is 15% of 240?"}], cache=False)
    )
    assert bypass.cache_hit is False
    assert bypass.cost_usd > 0


async def test_retry_then_fallback_to_the_second_provider(db):
    primary = FakeProvider("primary-rail", fail_times=10)
    backup = FakeProvider("backup-rail", text="from the backup rail")
    yard = await build_yard(
        db,
        make_settings(max_retries=1),
        registry=FakeRegistry([primary, backup]),
    )

    outcome = await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 2 + 2?"}]))

    assert outcome.provider == "backup-rail"
    assert outcome.text == "from the backup rail"
    assert outcome.fallback_used is True
    assert [attempt["status"] for attempt in outcome.attempts] == ["error", "error", "ok"]
    assert primary.calls == 2
    assert backup.calls == 1


async def test_non_retryable_error_moves_on_immediately(db):
    primary = FakeProvider("primary-rail", fail_times=10, retryable=False)
    backup = FakeProvider("backup-rail")
    yard = await build_yard(
        db,
        make_settings(max_retries=3),
        registry=FakeRegistry([primary, backup]),
    )

    outcome = await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 2 + 2?"}]))

    assert outcome.provider == "backup-rail"
    assert primary.calls == 1
    assert [attempt["status"] for attempt in outcome.attempts] == ["error", "ok"]


async def test_all_routes_failed_returns_502_and_an_error_receipt(db):
    primary = FakeProvider("primary-rail", fail_times=99)
    backup = FakeProvider("backup-rail", fail_times=99)
    yard = await build_yard(
        db,
        make_settings(max_retries=1),
        registry=FakeRegistry([primary, backup]),
    )

    with pytest.raises(GatewayError) as caught:
        await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 2 + 2?"}]))

    assert caught.value.status_code == 502
    assert caught.value.kind == "all_routes_failed"
    assert caught.value.request_id

    async with db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest))
        report = await yard.ledger.verify(session)
    assert row.status == "error"
    assert row.attempts == 8
    assert row.error
    assert report["ok"] is True


async def test_budget_guard_blocks_once_the_daily_limit_is_gone(db):
    yard = await build_yard(db, make_settings(daily_budget_usd=5e-7))

    first = await yard.pipeline.complete(
        ChatCall([{"role": "user", "content": "What is 2 + 2?"}], cache=False)
    )
    assert first.cost_usd > 0

    with pytest.raises(GatewayError) as caught:
        await yard.pipeline.complete(ChatCall([{"role": "user", "content": "What is 3 + 3?"}], cache=False))
    assert caught.value.status_code == 402
    assert caught.value.kind == "budget_exhausted"

    async with db.session_factory() as session:
        blocked = await session.scalar(select(GatewayRequest).where(GatewayRequest.status == "blocked"))
    assert blocked is not None
    assert blocked.error.startswith("Daily budget exhausted")


async def test_budget_guard_downgrades_a_prime_route(db):
    yard = await build_yard(db, make_settings(daily_budget_usd=1e-6))

    outcome = await yard.pipeline.complete(
        ChatCall(
            [{"role": "user", "content": "Design a three-step plan to rotate an API key without downtime."}],
            max_tokens=20,
            cache=False,
        )
    )

    assert outcome.tier == "thrift"
    assert outcome.route.policy == "auto"
    assert outcome.route.summary.startswith("budget guard:")
    assert "downgraded" in outcome.route.reasons[0]["label"]
    assert outcome.route.confidence <= 0.5


async def test_routing_ignores_agent_scaffolding(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.pipeline.complete(
        ChatCall(
            [
                {
                    "role": "system",
                    "content": "```python\ndef deep_work():\n    return 'heavy'\n```",
                },
                {"role": "user", "content": "hello"},
            ]
        )
    )

    assert outcome.tier == "thrift"
    assert outcome.route.features["greeting"] is True


async def test_pinned_model_keeps_its_identity(db):
    yard = await build_yard(db, make_settings())

    outcome = await yard.pipeline.complete(
        ChatCall([{"role": "user", "content": "hello"}], model="sim-mainline")
    )

    assert outcome.route.policy == "pinned"
    assert outcome.tier == "prime"
    assert outcome.model == "sim-mainline"
    assert outcome.provider == "simulator"

    async with db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest))
    assert row.requested_model == "sim-mainline"
    assert row.policy == "pinned"


async def test_prompt_storage_can_be_switched_off(db):
    private = await build_yard(db, make_settings(store_prompts=False))
    await private.pipeline.complete(
        ChatCall([{"role": "user", "content": "A private question about payroll."}])
    )
    async with db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest))
    assert row.prompt_text is None
    assert row.response_text is None
    assert "payroll" in row.prompt_preview

    open_book = await build_yard(db, make_settings(store_prompts=True))
    await open_book.pipeline.complete(
        ChatCall([{"role": "user", "content": "A recorded question about widgets."}])
    )
    async with db.session_factory() as session:
        stored = await session.scalar(
            select(GatewayRequest).where(GatewayRequest.prompt_preview.contains("widgets"))
        )
    assert stored.prompt_text.startswith("[user]")
    assert stored.response_text


async def test_agent_attribution_is_persisted(db):
    yard = await build_yard(db, make_settings())

    await yard.pipeline.complete(
        ChatCall([{"role": "user", "content": "What is 2 + 2?"}]),
        source="eval",
        batch_id="gnt_test",
        run_id="run_test",
        task_id="q01",
    )

    async with db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest))
    assert (row.source, row.batch_id, row.run_id, row.task_id) == (
        "eval",
        "gnt_test",
        "run_test",
        "q01",
    )
