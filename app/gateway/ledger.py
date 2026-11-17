from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GatewayRequest


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat(timespec="seconds")


def new_request_id() -> str:
    return f"req_{int(time.time() * 1000):x}{secrets.token_hex(4)}"


def new_batch_id() -> str:
    return f"gnt_{secrets.token_hex(8)}"


def new_run_id() -> str:
    return f"run_{secrets.token_hex(8)}"


def _payload(row: GatewayRequest) -> str:
    material = {
        "id": row.id,
        "created_ms": row.created_ms,
        "source": row.source,
        "policy": row.policy,
        "tier": row.tier,
        "provider": row.provider,
        "model": row.model,
        "status": row.status,
        "cache_hit": row.cache_hit,
        "fallback_used": row.fallback_used,
        "tokens": [row.input_tokens, row.output_tokens],
        "cost_usd": row.cost_usd,
        "saved_usd": row.saved_usd,
        "latency_ms": row.latency_ms,
        "prompt_hash": row.prompt_hash,
        "prompt_preview": row.prompt_preview,
        "response_preview": row.response_preview,
        "error": row.error or "",
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, payload: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), f"{prev_hash}|{payload}".encode(), hashlib.sha256).hexdigest()


class Ledger:
    def __init__(self, key: str, lock):
        self.key = key
        self.lock = lock

    async def append(self, session: AsyncSession, row: GatewayRequest) -> GatewayRequest:
        async with self.lock:
            last = await session.scalar(select(GatewayRequest).order_by(GatewayRequest.seq.desc()).limit(1))
            row.prev_hash = last.entry_hash if last else "0" * 64
            row.entry_hash = _hash(row.prev_hash, _payload(row), self.key)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def verify(self, session: AsyncSession) -> dict:
        rows = (await session.scalars(select(GatewayRequest).order_by(GatewayRequest.seq.asc()))).all()
        expected_prev = "0" * 64
        for row in rows:
            if row.prev_hash != expected_prev:
                return _broken(row, len(rows), "previous hash mismatch")
            recomputed = _hash(row.prev_hash, _payload(row), self.key)
            if not hmac.compare_digest(recomputed, row.entry_hash):
                return _broken(row, len(rows), "entry hash mismatch")
            expected_prev = row.entry_hash
        return {
            "ok": True,
            "entries": len(rows),
            "checked_ms": now_ms(),
            "broken_at": None,
            "detail": "Every receipt links to the one before it.",
        }


def _broken(row: GatewayRequest, total: int, detail: str) -> dict:
    return {
        "ok": False,
        "entries": total,
        "checked_ms": now_ms(),
        "broken_at": row.id,
        "broken_seq": row.seq,
        "detail": detail,
    }


def preview(text: str, limit: int = 280) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
