from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    vendor: str
    tier: str
    input_per_m: float
    output_per_m: float
    energy_kwh_per_1k: float
    context: int = 128_000
    note: str = ""


# Prices are USD per million tokens, energy is kWh per 1k tokens.
# They are editable on purpose: the gate compares policies under one price sheet,
# and a stale number should be a one-line fix, not a rewrite.
CATALOG: dict[str, ModelInfo] = {
    "sim-shunter": ModelInfo(
        id="sim-shunter",
        name="Shunter 8B",
        vendor="Switchyard simulator",
        tier="thrift",
        input_per_m=0.06,
        output_per_m=0.09,
        energy_kwh_per_1k=0.00016,
        context=32_000,
        note="Deterministic offline stand-in for a small, fast model.",
    ),
    "sim-mainline": ModelInfo(
        id="sim-mainline",
        name="Mainline 70B",
        vendor="Switchyard simulator",
        tier="prime",
        input_per_m=0.60,
        output_per_m=0.80,
        energy_kwh_per_1k=0.00058,
        context=128_000,
        note="Deterministic offline stand-in for a frontier-class model.",
    ),
    "llama-3.1-8b-instant": ModelInfo(
        id="llama-3.1-8b-instant",
        name="Llama 3.1 8B Instant",
        vendor="Groq",
        tier="thrift",
        input_per_m=0.05,
        output_per_m=0.08,
        energy_kwh_per_1k=0.00016,
        context=131_072,
        note="Groq list price; verify before publishing numbers.",
    ),
    "llama-3.3-70b-versatile": ModelInfo(
        id="llama-3.3-70b-versatile",
        name="Llama 3.3 70B Versatile",
        vendor="Groq",
        tier="prime",
        input_per_m=0.59,
        output_per_m=0.79,
        energy_kwh_per_1k=0.00058,
        context=131_072,
        note="Groq list price; verify before publishing numbers.",
    ),
    "gpt-4o-mini": ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o mini",
        vendor="OpenAI",
        tier="thrift",
        input_per_m=0.15,
        output_per_m=0.60,
        energy_kwh_per_1k=0.00018,
        context=128_000,
        note="OpenAI list price; verify before publishing numbers.",
    ),
    "gpt-4o": ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        vendor="OpenAI",
        tier="prime",
        input_per_m=2.50,
        output_per_m=10.00,
        energy_kwh_per_1k=0.00075,
        context=128_000,
        note="OpenAI list price; verify before publishing numbers.",
    ),
}


def model_info(model_id: str) -> ModelInfo:
    if model_id in CATALOG:
        return CATALOG[model_id]
    tier = "prime" if any(word in model_id.lower() for word in ("70b", "gpt-4o", "large")) else "thrift"
    return ModelInfo(
        id=model_id,
        name=model_id,
        vendor="custom",
        tier=tier,
        input_per_m=0.60 if tier == "prime" else 0.06,
        output_per_m=0.80 if tier == "prime" else 0.09,
        energy_kwh_per_1k=0.00058 if tier == "prime" else 0.00016,
        note="Unknown model: the default price sheet is applied.",
    )


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_message_tokens(messages: list[dict]) -> int:
    total = 0
    for message in messages:
        total += 4
        total += estimate_tokens(str(message.get("content", "")))
    return max(total, 1)


def call_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    info = model_info(model_id)
    return (input_tokens / 1_000_000) * info.input_per_m + (output_tokens / 1_000_000) * info.output_per_m


def call_energy_wh(
    model_id: str, total_tokens: int, carbon_intensity: float, pue: float
) -> tuple[float, float]:
    info = model_info(model_id)
    kwh = info.energy_kwh_per_1k * (max(total_tokens, 0) / 1000) * pue
    return kwh * 1000, kwh * carbon_intensity


def round_money(value: float) -> float:
    return round(value, 8)
