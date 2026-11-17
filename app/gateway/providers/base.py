from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    finish_reason: str = "stop"


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool = True,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class Provider:
    name = "provider"
    kind = "generic"

    def __init__(self):
        self.tier_models: dict[str, str] = {}

    def model_for(self, tier: str) -> str:
        return self.tier_models.get(tier, "")

    def info(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "tier_models": dict(self.tier_models),
        }

    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float | None,
        max_tokens: int,
        request_id: str,
    ) -> Completion:
        raise NotImplementedError

    async def probe(self) -> dict:
        raise NotImplementedError

    async def close(self) -> None:
        return None
