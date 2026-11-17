from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All knobs live here so a deployment is one .env file away."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    serve_frontend: bool = True
    cors_origins: str = "*"

    database_url: str = "sqlite+aiosqlite:///./switchyard.db"
    redis_url: str = ""

    provider_mode: Literal["auto", "live", "simulated"] = "auto"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_cheap: str = "llama-3.1-8b-instant"
    groq_model_strong: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_cheap: str = "gpt-4o-mini"
    openai_model_strong: str = "gpt-4o"
    fallback_provider: str = ""

    request_timeout_s: float = 45.0
    max_retries: int = 2
    retry_base_ms: int = 350
    breaker_threshold: int = 3
    breaker_window_s: int = 60
    breaker_cooldown_s: int = 20

    cache_ttl_s: int = 3600
    cache_max_entries: int = 2000

    daily_budget_usd: float = 5.0
    carbon_intensity_g_per_kwh: float = 380.0
    datacenter_pue: float = 1.15

    gateway_api_key: str = ""
    admin_token: str = ""
    rate_limit_rpm: int = 120
    store_prompts: bool = False

    ledger_key: str = "switchyard-dev-ledger-key"

    simulator_latency_min_ms: int = 70
    simulator_latency_max_ms: int = 240

    @property
    def live_keys_present(self) -> bool:
        return bool(self.groq_api_key or self.openai_api_key)

    @property
    def resolved_mode(self) -> Literal["live", "simulated"]:
        if self.provider_mode == "simulated":
            return "simulated"
        if self.provider_mode == "live":
            return "live" if self.live_keys_present else "simulated"
        return "live" if self.live_keys_present else "simulated"

    @property
    def cors_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def using_default_ledger_key(self) -> bool:
        return self.ledger_key == "switchyard-dev-ledger-key"


@lru_cache
def get_settings() -> Settings:
    # Tests set env vars before constructing the app; lru_cache keeps one view per process.
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
    os.environ.pop("_SWITCHYARD_CACHE_BUST", None)
