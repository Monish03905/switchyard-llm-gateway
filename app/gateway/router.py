from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.gateway.cost import CATALOG, estimate_message_tokens, model_info

POLICY_ALIASES = {
    "auto": "auto",
    "yardmaster": "auto",
    "router": "auto",
    "thrift": "thrift",
    "cheap": "thrift",
    "prime": "prime",
    "strong": "prime",
}

CODE_PATTERN = re.compile(
    r"```|(^|\s)(def|class|import|function|print|range|lambda|const|let|Traceback|Exception|=>)\b|python|javascript|typescript|sql\b",
    re.MULTILINE | re.IGNORECASE,
)
STRUCTURED_TERMS = (
    "list ",
    "steps",
    "explain",
    "describe",
    "give two",
    "name two",
    "signs",
    "checks",
    "sentences",
    "summarize",
    "walk me through",
    "plan",
)
SENSITIVE_TERMS = (
    "api key",
    "api_key",
    "secret",
    "password",
    "credential",
    "private",
    "consent",
    "billing",
    "production",
    "delete",
    "permission",
    "personal data",
    "logs",
)
UNIT_TERMS = (
    "convert",
    "kilometer",
    "kilogram",
    "fahrenheit",
    "celsius",
    "meters per second",
    "kilometers per hour",
    "miles per hour",
    "how many grams",
    "how many liters",
)
REASONING_TERMS = (
    "step by step",
    "step-by-step",
    "compare",
    "trade-off",
    "tradeoff",
    "analyze",
    "analyse",
    "analysis",
    "evaluate",
    "design",
    "architecture",
    "prove",
    "derive",
    "debug",
    "root cause",
    "optimi",
    "why does",
    "why ",
    "explain why",
)
MULTI_STEP_TERMS = (
    "then",
    "after that",
    "next",
    "finally",
    "total",
    "each",
    "per ",
    "remaining",
    "how many more",
    "altogether",
    "multiply",
    "subtract",
    "divide",
    "how long",
)
LOOKUP_STARTS = ("what is", "what's", "who ", "when ", "where ", "which ", "how many")
GREETING_PATTERN = re.compile(r"^\s*(hi|hey|hello|yo|thanks|thank you|good (morning|evening))\b", re.I)
NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
OPERATOR_PATTERN = re.compile(r"\d\s*[\+\-\*/%]\s*\d")


@dataclass
class RouteDecision:
    policy: str
    tier: str
    confidence: float
    score: float
    summary: str
    reasons: list[dict] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    pinned_model: str | None = None

    def as_dict(self) -> dict:
        return {
            "policy": self.policy,
            "tier": self.tier,
            "confidence": self.confidence,
            "score": self.score,
            "summary": self.summary,
            "reasons": self.reasons,
            "features": self.features,
            "pinned_model": self.pinned_model,
        }


def normalize_policy(value: str | None) -> str:
    return POLICY_ALIASES.get((value or "auto").strip().lower(), "auto")


def choose_tier(messages: list[dict], policy: str = "auto", requested_model: str = "auto") -> RouteDecision:
    policy = normalize_policy(policy)
    requested = (requested_model or "auto").strip()

    if requested in CATALOG:
        info = model_info(requested)
        return RouteDecision(
            policy="pinned",
            tier=info.tier,
            confidence=1.0,
            score=1.0,
            summary=f"model pinned to {requested}",
            reasons=[{"label": f"model pinned to {requested}", "weight": 1.0}],
            features={"pinned": True, "chars": _chars(messages)},
            pinned_model=requested,
        )

    text = "\n".join(str(m.get("content", "")) for m in messages)
    features = _features(text, messages)
    score = features["score"]

    if policy == "thrift":
        return RouteDecision(
            policy=policy,
            tier="thrift",
            confidence=1.0,
            score=score,
            summary="policy pinned to the thrift tier",
            reasons=[{"label": "policy pinned to thrift", "weight": 1.0}] + _top_reasons(features, limit=2),
            features=features,
        )
    if policy == "prime":
        return RouteDecision(
            policy=policy,
            tier="prime",
            confidence=1.0,
            score=score,
            summary="policy pinned to the prime tier",
            reasons=[{"label": "policy pinned to prime", "weight": 1.0}] + _top_reasons(features, limit=2),
            features=features,
        )

    tier = "prime" if score >= features["threshold"] else "thrift"
    distance = abs(score - features["threshold"])
    confidence = round(min(0.97, 0.56 + distance * 1.6), 2)
    reasons = _top_reasons(features, limit=3)
    summary = "; ".join(r["label"] for r in reasons) or "no strong signals, kept it light"
    return RouteDecision(
        policy="auto",
        tier=tier,
        confidence=confidence,
        score=round(score, 2),
        summary=summary,
        reasons=reasons,
        features=features,
    )


def _chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages)


def _features(text: str, messages: list[dict]) -> dict:
    lowered = text.lower()
    chars = len(text)
    words = len(text.split())
    numbers = NUMBER_PATTERN.findall(text)
    question_marks = text.count("?")
    has_code = bool(CODE_PATTERN.search(text))
    has_fence = "```" in text
    has_backtick = "`" in text and not has_fence
    reasoning_hits = [term for term in REASONING_TERMS if term in lowered]
    multi_hits = [term for term in MULTI_STEP_TERMS if term in lowered]
    structured_hits = [term for term in STRUCTURED_TERMS if term in lowered]
    sensitive_hits = [term for term in SENSITIVE_TERMS if term in lowered]
    unit_hits = [term for term in UNIT_TERMS if term in lowered]
    has_operator_math = bool(OPERATOR_PATTERN.search(text))
    multi_step = len(numbers) >= 3 and bool(multi_hits)
    short_lookup = chars < 170 and lowered.strip().startswith(LOOKUP_STARTS)
    greeting = chars < 90 and bool(GREETING_PATTERN.match(text))

    contributions: list[tuple[float, str]] = []

    if has_fence:
        contributions.append((0.40, "contains a code block"))
    elif has_backtick:
        contributions.append((0.36, "inline code or literal syntax"))
    elif has_code:
        contributions.append((0.28, "code-shaped prompt"))

    if len(reasoning_hits) >= 2:
        contributions.append((0.24, f"reasoning language ({', '.join(reasoning_hits[:2])})"))
    elif reasoning_hits:
        contributions.append((0.14, f"asks for reasoning ({reasoning_hits[0]})"))

    if multi_step:
        contributions.append((0.36, "multi-step arithmetic"))
    elif has_operator_math:
        contributions.append((0.10, "contains an arithmetic expression"))

    if structured_hits:
        contributions.append((0.34, f"asks for structured guidance ({structured_hits[0].strip()})"))

    if sensitive_hits:
        contributions.append((0.38, f"safety-sensitive wording ({sensitive_hits[0]})"))

    if unit_hits:
        contributions.append((0.34, "unit conversion needs precision"))

    if chars > 900:
        contributions.append((0.20, f"long brief ({chars:,} chars)"))
    elif chars > 450:
        contributions.append((0.10, f"medium brief ({chars:,} chars)"))

    if question_marks > 1:
        contributions.append((0.08, f"{question_marks} questions in one request"))

    if short_lookup and not has_operator_math and not unit_hits and not sensitive_hits:
        contributions.append((-0.14, "single lookup-style question"))
    if greeting:
        contributions.append((-0.30, "greeting or small talk"))

    # The threshold is deliberately conservative: routing up is safe, routing down is not.
    threshold = 0.33
    score = round(sum(weight for weight, _ in contributions), 2)
    return {
        "chars": chars,
        "words": words,
        "approx_tokens": estimate_message_tokens(messages),
        "numbers": len(numbers),
        "question_marks": question_marks,
        "has_code": has_code,
        "has_fence": has_fence,
        "has_backtick": has_backtick,
        "reasoning_terms": reasoning_hits[:4],
        "structured_terms": structured_hits[:3],
        "sensitive_terms": sensitive_hits[:3],
        "unit_terms": unit_hits[:3],
        "multi_step": multi_step,
        "has_operator_math": has_operator_math,
        "short_lookup": short_lookup,
        "greeting": greeting,
        "score": score,
        "threshold": threshold,
        "contributions": [{"label": label, "weight": round(weight, 2)} for weight, label in contributions],
    }


def _top_reasons(features: dict, limit: int = 3) -> list[dict]:
    contributions = sorted(
        features.get("contributions", []), key=lambda item: abs(item["weight"]), reverse=True
    )
    if not contributions:
        return [{"label": "no routing signals found", "weight": 0.0}]
    return contributions[:limit]
