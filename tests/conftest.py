from __future__ import annotations

from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.agent.runner import AgentRunner
from app.config import Settings
from app.db import Database, LedgerLock
from app.gateway.breaker import CircuitBreaker
from app.gateway.cache import MemoryCache, ResponseCache
from app.gateway.chaos import Squall
from app.gateway.ledger import Ledger
from app.gateway.pipeline import GatewayPipeline
from app.gateway.registry import ProviderRegistry

API_DEFAULTS = {
    "provider_mode": "simulated",
    "serve_frontend": "false",
    "app_env": "test",
    "log_level": "WARNING",
    "simulator_latency_min_ms": "0",
    "simulator_latency_max_ms": "0",
    "max_retries": "1",
    "retry_base_ms": "0",
    "cache_ttl_s": "120",
    "daily_budget_usd": "5",
    "rate_limit_rpm": "1000",
    "gateway_api_key": "",
    "admin_token": "yard-admin",
    "store_prompts": "false",
    "ledger_key": "pytest-api-ledger-key",
}


def make_settings(**overrides) -> Settings:
    values = {
        "provider_mode": "simulated",
        "database_url": "sqlite+aiosqlite:///./tmp_pytest.db",
        "serve_frontend": False,
        "simulator_latency_min_ms": 0,
        "simulator_latency_max_ms": 0,
        "max_retries": 1,
        "retry_base_ms": 0,
        "cache_ttl_s": 120,
        "daily_budget_usd": 5.0,
        "rate_limit_rpm": 1000,
        "gateway_api_key": "",
        "admin_token": "",
        "store_prompts": True,
        "ledger_key": "pytest-ledger-key",
        "breaker_threshold": 3,
        "breaker_window_s": 60,
        "breaker_cooldown_s": 20,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class Yard:
    settings: Settings
    db: Database
    squall: Squall
    registry: object
    cache: ResponseCache
    breaker: CircuitBreaker
    ledger: Ledger
    pipeline: GatewayPipeline
    agent: AgentRunner


async def build_yard(db: Database, settings: Settings, *, registry=None, squall=None) -> Yard:
    squall = squall or Squall()
    registry = registry or ProviderRegistry(settings, squall)
    cache = ResponseCache(MemoryCache(64), settings.cache_ttl_s, note="pytest cache")
    breaker = CircuitBreaker(
        threshold=settings.breaker_threshold,
        window_s=settings.breaker_window_s,
        cooldown_s=settings.breaker_cooldown_s,
    )
    ledger = Ledger(settings.ledger_key, LedgerLock())
    pipeline = GatewayPipeline(
        settings=settings,
        registry=registry,
        cache=cache,
        breaker=breaker,
        ledger=ledger,
        session_factory=db.session_factory,
    )
    return Yard(
        settings=settings,
        db=db,
        squall=squall,
        registry=registry,
        cache=cache,
        breaker=breaker,
        ledger=ledger,
        pipeline=pipeline,
        agent=AgentRunner(pipeline),
    )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'yard.db').as_posix()}")
    await database.init()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def yard(db, settings):
    built = await build_yard(db, settings)
    yield built
    await built.registry.close()
    await built.cache.close()


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    counter = {"n": 0}

    def build(**overrides):
        counter["n"] += 1
        db_name = f"api_{counter['n']}.db"
        env = dict(API_DEFAULTS)
        env["database_url"] = f"sqlite+aiosqlite:///{(tmp_path / db_name).as_posix()}"
        for key, value in overrides.items():
            env[key.lower()] = value
        for key, value in env.items():
            monkeypatch.setenv(key.upper(), str(value))
        from app.main import create_app

        return TestClient(create_app())

    return build


@pytest.fixture
def api_client(client_factory):
    with client_factory() as client:
        yield client


@pytest.fixture
def admin_headers():
    return {"X-Admin-Token": "yard-admin"}
