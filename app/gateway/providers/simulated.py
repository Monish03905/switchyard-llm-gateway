from __future__ import annotations

import asyncio
import json
import random
import re
import time

from app.agent.tools import (
    ToolError,
    calculate_expression,
    convert_units,
    format_number,
    lookup_fact,
    parse_conversion_prompt,
)
from app.evals.dataset import match_task
from app.gateway.cost import estimate_message_tokens, estimate_tokens
from app.gateway.providers.base import Completion, Provider, ProviderError

AGENT_MARKER = "[[SWITCHYARD_AGENT]]"
TOOL_RESULT_PREFIX = "TOOL RESULT"


class SimulatedProvider(Provider):
    """A deterministic stand-in, calibrated so offline demos and CI are meaningful.

    It is not pretending to be a model. It follows the same request/response contract,
    behaves like a thrift or prime tier, and is labelled everywhere it appears.
    """

    kind = "simulated"

    def __init__(
        self,
        *,
        latency_min_ms: int,
        latency_max_ms: int,
        squall,
        name: str = "simulator",
    ):
        super().__init__()
        self.name = name
        self.tier_models = {"thrift": "sim-shunter", "prime": "sim-mainline"}
        self.latency_min_ms = latency_min_ms
        self.latency_max_ms = latency_max_ms
        self.squall = squall

    def info(self) -> dict:
        base = super().info()
        base.update({"configured": True, "simulated": True})
        return base

    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float | None,
        max_tokens: int,
        request_id: str,
    ) -> Completion:
        started = time.perf_counter()
        tier = "prime" if model == self.tier_models["prime"] else "thrift"
        await asyncio.sleep(self._delay_seconds(tier, request_id))

        if self.squall.take():
            raise ProviderError(
                "squall over the yard: simulated provider failure",
                provider=self.name,
                retryable=True,
                status_code=503,
            )

        text = _reply(messages, tier, model)
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=estimate_message_tokens(messages),
            output_tokens=estimate_tokens(text),
            latency_ms=latency_ms,
            finish_reason="stop",
        )

    async def probe(self) -> dict:
        return {
            "ok": True,
            "provider": self.name,
            "latency_ms": 1,
            "sample": "ready (simulated)",
        }

    def _delay_seconds(self, tier: str, request_id: str) -> float:
        if self.latency_max_ms <= 0:
            return 0.0
        rng = random.Random(request_id)
        base = rng.uniform(self.latency_min_ms, self.latency_max_ms)
        if tier == "prime":
            base *= 1.55
        return base / 1000


def _reply(messages: list[dict], tier: str, model: str) -> str:
    agent_mode = _agent_mode(messages)
    prompt = _task_prompt(messages)
    has_tool_result = _has_tool_result(messages)
    task = match_task(prompt)

    if agent_mode:
        if has_tool_result:
            if task is not None:
                answer = task.ideal_answer if tier == "prime" else task.cheap_answer
            else:
                answer = _answer_from_tool_result(messages)
            return json.dumps({"answer": answer}, ensure_ascii=False)

        available = _available_tools(messages)
        if task is not None:
            want_tool = task.required_tools[0] if task.required_tools else None
            if want_tool and want_tool in available and (tier == "prime" or task.cheap_uses_tools):
                args = task.sim_tool_args.get(want_tool) or _infer_tool_args(want_tool, prompt)
                return json.dumps({"tool": want_tool, "args": args}, ensure_ascii=False)
            answer = task.ideal_answer if tier == "prime" else task.cheap_answer
            return json.dumps({"answer": answer}, ensure_ascii=False)

        call = _infer_tool_call(prompt, available)
        if call is not None:
            return json.dumps(call, ensure_ascii=False)
        return json.dumps({"answer": _direct_answer(prompt, tier)}, ensure_ascii=False)

    if task is not None:
        return task.ideal_answer if tier == "prime" else task.cheap_answer
    return _direct_answer(prompt, tier)


def _agent_mode(messages: list[dict]) -> bool:
    return any(AGENT_MARKER in str(m.get("content", "")) for m in messages)


def _task_prompt(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        if not content.startswith(TOOL_RESULT_PREFIX):
            return content
    return ""


def _has_tool_result(messages: list[dict]) -> bool:
    return any(str(m.get("content", "")).startswith(TOOL_RESULT_PREFIX) for m in messages)


def _available_tools(messages: list[dict]) -> list[str]:
    for message in messages:
        content = str(message.get("content", ""))
        if AGENT_MARKER not in content:
            continue
        match = re.search(r"tools=([a-z0-9_|,]+)", content)
        if match:
            return [name for name in re.split(r"[|,]", match.group(1)) if name]
    return []


def _answer_from_tool_result(messages: list[dict]) -> str:
    for message in reversed(messages):
        content = str(message.get("content", ""))
        if content.startswith(TOOL_RESULT_PREFIX):
            first_line = content.splitlines()[0]
            if ":" in first_line:
                return first_line.split(":", 1)[1].strip()
            return first_line
    return ""


def _infer_tool_call(prompt: str, available: list[str]) -> dict | None:
    lowered = prompt.lower()
    if "convert" in available:
        conversion = parse_conversion_prompt(prompt)
        if conversion:
            return {"tool": "convert", "args": conversion}
    if "calculator" in available:
        expression = _extract_expression(prompt)
        if expression:
            return {"tool": "calculator", "args": {"expression": expression}}
    if "lookup" in available and lowered.strip().startswith(("what", "who", "which", "when", "where")):
        if lookup_fact(prompt) is not None:
            return {"tool": "lookup", "args": {"query": prompt}}
    return None


def _infer_tool_args(tool: str, prompt: str) -> dict:
    if tool == "calculator":
        return {"expression": _extract_expression(prompt) or "0"}
    if tool == "convert":
        return parse_conversion_prompt(prompt) or {}
    return {"query": prompt}


def _direct_answer(prompt: str, tier: str) -> str:
    lowered = prompt.lower().strip()
    if re.match(r"^(hi|hey|hello|yo|thanks|thank you)\b", lowered):
        return "Yard's open. Ask for arithmetic, a conversion, or a reference fact while the simulator is on duty."

    conversion = parse_conversion_prompt(prompt)
    if conversion:
        try:
            result = convert_units(**conversion)
            return f"{result['formatted']} {result['to']}"
        except ToolError:
            pass

    percentage = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", prompt)
    if percentage:
        value = float(percentage.group(1)) * float(percentage.group(2)) / 100
        return format_number(value)

    squared = re.search(r"(\d+(?:\.\d+)?)\s*squared\s+minus\s+(\d+(?:\.\d+)?)\s*squared", prompt, re.I)
    if squared:
        value = float(squared.group(1)) ** 2 - float(squared.group(2)) ** 2
        return format_number(value)

    add = re.search(r"add\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", prompt, re.I)
    if add:
        return format_number(float(add.group(1)) + float(add.group(2)))

    expression = _extract_expression(prompt)
    if expression:
        try:
            return calculate_expression(expression)
        except ToolError:
            pass

    fact = lookup_fact(prompt)
    if fact is not None:
        return fact["answer"]

    return (
        "The yard is in simulator mode, so I will not invent an answer to that. "
        "Add a provider key (GROQ_API_KEY) and this same request goes out on the live rail."
    )


def _extract_expression(prompt: str) -> str | None:
    runs = re.findall(r"[0-9.+\-*/%() ]{3,}", prompt)
    candidates = []
    for run in runs:
        cleaned = run.strip()
        if not re.search(r"\d", cleaned):
            continue
        if not re.search(r"[+\-*/%]", cleaned):
            continue
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned.startswith(("+", "*", "/", "%")):
            continue
        candidates.append(cleaned)
    if not candidates:
        return None
    return max(candidates, key=len)
