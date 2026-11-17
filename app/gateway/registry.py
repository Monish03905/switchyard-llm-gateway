from __future__ import annotations

from dataclasses import dataclass

from app.gateway.cost import CATALOG
from app.gateway.providers.base import Provider
from app.gateway.providers.openai_compat import OpenAICompatProvider
from app.gateway.providers.simulated import SimulatedProvider


@dataclass(frozen=True)
class Candidate:
    provider: Provider
    model: str
    tier: str


class ProviderRegistry:
    def __init__(self, settings, squall):
        self.settings = settings
        self.squall = squall
        self.providers: list[Provider] = []
        self.mode = settings.resolved_mode
        self.note = ""

        if self.mode == "live":
            if settings.groq_api_key:
                self.providers.append(
                    OpenAICompatProvider(
                        name="groq",
                        base_url=settings.groq_base_url,
                        api_key=settings.groq_api_key,
                        cheap_model=settings.groq_model_cheap,
                        strong_model=settings.groq_model_strong,
                        timeout_s=settings.request_timeout_s,
                    )
                )
            if settings.openai_api_key:
                self.providers.append(
                    OpenAICompatProvider(
                        name="openai",
                        base_url=settings.openai_base_url,
                        api_key=settings.openai_api_key,
                        cheap_model=settings.openai_model_cheap,
                        strong_model=settings.openai_model_strong,
                        timeout_s=settings.request_timeout_s,
                    )
                )
            if not self.providers:
                self.mode = "simulated"

        if self.mode == "simulated":
            self.providers = [
                SimulatedProvider(
                    latency_min_ms=settings.simulator_latency_min_ms,
                    latency_max_ms=settings.simulator_latency_max_ms,
                    squall=squall,
                )
            ]
            self.note = (
                "No provider key detected, so a deterministic simulator is holding the levers. "
                "Costs and pass rates are a rehearsal, not a provider bill."
            )
        else:
            self.note = (
                "Live providers are connected. Prices and energy figures come from the editable "
                "sheet in app/gateway/cost.py."
            )

        self.primary = self._pick_primary()
        others = [p for p in self.providers if p is not self.primary]
        self.secondary = others[0] if others else None

    def _pick_primary(self) -> Provider:
        if len(self.providers) == 1:
            return self.providers[0]
        preferred_secondary = (self.settings.fallback_provider or "").strip().lower()
        for provider in self.providers:
            if provider.name != preferred_secondary:
                return provider
        return self.providers[0]

    def baseline_model(self) -> str:
        return self.primary.model_for("prime")

    def provider_for_model(self, model: str) -> Provider | None:
        for provider in self.providers:
            if model in provider.tier_models.values():
                return provider
        return None

    def candidates(self, tier: str, pinned_model: str | None = None) -> list[Candidate]:
        other = "thrift" if tier == "prime" else "prime"
        ordered: list[Candidate] = []

        if pinned_model:
            owner = self.provider_for_model(pinned_model)
            if owner is not None:
                pinned_tier = "prime" if owner.model_for("prime") == pinned_model else "thrift"
                ordered.append(Candidate(owner, pinned_model, pinned_tier))

        for provider in (self.primary, self.secondary):
            if provider is None:
                continue
            ordered.append(Candidate(provider, provider.model_for(tier), tier))
        for provider in (self.primary, self.secondary):
            if provider is None:
                continue
            ordered.append(Candidate(provider, provider.model_for(other), other))

        deduped: list[Candidate] = []
        seen: set[tuple[str, str]] = set()
        for candidate in ordered:
            key = (candidate.provider.name, candidate.model)
            if not candidate.model or key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def model_catalog(self) -> list[dict]:
        rows = []
        for provider in self.providers:
            for tier in ("thrift", "prime"):
                model_id = provider.model_for(tier)
                info = CATALOG.get(model_id)
                rows.append(
                    {
                        "provider": provider.name,
                        "model": model_id,
                        "tier": tier,
                        "name": info.name if info else model_id,
                        "vendor": info.vendor if info else provider.kind,
                        "input_per_m": info.input_per_m if info else 0.0,
                        "output_per_m": info.output_per_m if info else 0.0,
                        "energy_kwh_per_1k": info.energy_kwh_per_1k if info else 0.0,
                        "context": info.context if info else 0,
                        "note": info.note if info else "",
                    }
                )
        return rows

    def info(self) -> dict:
        return {
            "mode": self.mode,
            "simulated": self.mode == "simulated",
            "note": self.note,
            "primary": self.primary.name,
            "secondary": self.secondary.name if self.secondary else None,
            "providers": [provider.info() for provider in self.providers],
            "catalog": self.model_catalog(),
        }

    async def close(self) -> None:
        for provider in self.providers:
            await provider.close()
