from __future__ import annotations

from sqlalchemy import select

from app.db import LedgerLock
from app.gateway.ledger import Ledger, iso_from_ms
from app.models import GatewayRequest


def receipt(request_id: str, created_ms: int = 1_700_000_000_000) -> GatewayRequest:
    return GatewayRequest(
        id=request_id,
        created_at=iso_from_ms(created_ms),
        created_ms=created_ms,
        source="test",
        policy="auto",
        requested_model="auto",
        tier="thrift",
        provider="simulator",
        model="sim-shunter",
        status="ok",
        cache_hit=False,
        fallback_used=False,
        attempts=1,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.00001,
        baseline_cost_usd=0.0002,
        saved_usd=0.00019,
        latency_ms=12,
        route_confidence=0.9,
        route_reason="test route",
        features_json="{}",
        attempts_json="[]",
        prompt_hash="a" * 64,
        prompt_preview="What is 2 + 2?",
        response_preview="4",
    )


async def test_receipts_form_a_hash_chain(db):
    ledger = Ledger("unit-test-key", LedgerLock())
    async with db.session_factory() as session:
        first = await ledger.append(session, receipt("req_one"))
    async with db.session_factory() as session:
        second = await ledger.append(session, receipt("req_two", created_ms=1_700_000_001_000))

    assert first.prev_hash == "0" * 64
    assert len(first.entry_hash) == 64
    assert second.prev_hash == first.entry_hash
    assert second.entry_hash != first.entry_hash

    async with db.session_factory() as session:
        report = await ledger.verify(session)
    assert report["ok"] is True
    assert report["entries"] == 2
    assert report["broken_at"] is None


async def test_verify_catches_a_tampered_receipt(db):
    ledger = Ledger("unit-test-key", LedgerLock())
    async with db.session_factory() as session:
        await ledger.append(session, receipt("req_one"))
    async with db.session_factory() as session:
        await ledger.append(session, receipt("req_two", created_ms=1_700_000_001_000))

    async with db.session_factory() as session:
        row = await session.scalar(select(GatewayRequest).where(GatewayRequest.id == "req_one"))
        row.cost_usd = 99.0
        await session.commit()

    async with db.session_factory() as session:
        report = await ledger.verify(session)
    assert report["ok"] is False
    assert report["broken_at"] == "req_one"
    assert report["detail"] == "entry hash mismatch"


async def test_a_different_signing_key_cannot_verify_the_chain(db):
    ledger = Ledger("unit-test-key", LedgerLock())
    async with db.session_factory() as session:
        await ledger.append(session, receipt("req_one"))

    intruder = Ledger("not-the-same-key", LedgerLock())
    async with db.session_factory() as session:
        report = await intruder.verify(session)
    assert report["ok"] is False
    assert report["detail"] == "entry hash mismatch"
