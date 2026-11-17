from __future__ import annotations

import time

from app.gateway.ledger import now_ms


async def chain_state(app, *, force: bool = False) -> dict:
    cached = app.state.chain_cache
    if not force and cached and time.time() - cached["at"] < 10:
        return cached["value"]
    async with app.state.db.session_factory() as session:
        value = await app.state.ledger.verify(session)
    app.state.chain_cache = {"at": time.time(), "value": value}
    return value


def provider_health(app) -> dict:
    registry = app.state.registry
    return {
        provider.name: {
            "breaker": app.state.breaker.snapshot(provider.name),
            "last_probe": app.state.probes.get(provider.name),
        }
        for provider in registry.providers
    }


def uptime_seconds(app) -> float:
    return round(time.time() - app.state.started_at, 1)


def age_ms(value: int | None) -> int | None:
    if not value:
        return None
    return max(0, now_ms() - int(value))
