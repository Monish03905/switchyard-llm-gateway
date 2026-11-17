from __future__ import annotations

from app.gateway.router import choose_tier, normalize_policy


def route(prompt: str, **kwargs):
    return choose_tier([{"role": "user", "content": prompt}], **kwargs)


def test_short_lookup_stays_on_the_thrift_rail():
    decision = route("What is the capital of Canada?")
    assert decision.tier == "thrift"
    assert decision.policy == "auto"
    assert decision.features["short_lookup"] is True
    assert decision.score < decision.features["threshold"]
    assert 0.56 <= decision.confidence <= 0.97


def test_fenced_code_routes_up():
    decision = route("```python\nprint(len({1, 1, 2}))\n```")
    assert decision.tier == "prime"
    assert decision.features["has_fence"] is True
    assert decision.score >= 0.33


def test_inline_code_plus_reasoning_routes_up():
    decision = route("Why does `x = 1` raise an error?")
    assert decision.features["has_backtick"] is True
    assert decision.tier == "prime"


def test_multi_step_arithmetic_routes_up():
    decision = route(
        "A courier travels 42 km on Monday, 57 km on Tuesday, and 31 km on Wednesday. "
        "What is the total distance?"
    )
    assert decision.features["multi_step"] is True
    assert decision.tier == "prime"


def test_lone_operator_stays_thrifty():
    decision = route("What is 47 * 13?")
    assert decision.features["has_operator_math"] is True
    assert decision.score == 0.1
    assert decision.tier == "thrift"


def test_unit_conversion_routes_up():
    decision = route("Convert 12 kilometers to meters.")
    assert decision.features["unit_terms"]
    assert decision.tier == "prime"


def test_safety_language_routes_up():
    decision = route("The user asks for the gateway API key so they can debug billing.")
    assert decision.features["sensitive_terms"]
    assert decision.tier == "prime"


def test_greeting_routes_down():
    decision = route("hello there")
    assert decision.features["greeting"] is True
    assert decision.tier == "thrift"


def test_policy_aliases_pin_the_rail():
    thrifty = route("Design a three-step migration plan.", policy="cheap")
    strong = route("hello", policy="strong")
    routed = route("Explain why retries need backoff.", policy="yardmaster")

    assert thrifty.tier == "thrift" and thrifty.policy == "thrift"
    assert strong.tier == "prime" and strong.policy == "prime"
    assert routed.policy == "auto"
    assert normalize_policy("router") == "auto"
    assert normalize_policy("nonsense") == "auto"


def test_pinned_model_wins():
    decision = choose_tier(
        [{"role": "user", "content": "hello"}],
        policy="auto",
        requested_model="sim-mainline",
    )
    assert decision.policy == "pinned"
    assert decision.tier == "prime"
    assert decision.confidence == 1.0
    assert decision.pinned_model == "sim-mainline"


def test_reasons_are_ranked_by_impact():
    decision = route("Explain why a code block with 42 + 57 fails in production, step by step.")
    assert decision.reasons
    weights = [abs(reason["weight"]) for reason in decision.reasons]
    assert weights == sorted(weights, reverse=True)
    assert all(reason["label"] for reason in decision.reasons)
