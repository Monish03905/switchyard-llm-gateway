from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app.agent.tools import TOOL_NAMES, TOOL_SPECS, ToolError, run_tool
from app.gateway.pipeline import ChatCall, GatewayError, GatewayPipeline

AGENT_MARKER = "[[SWITCHYARD_AGENT]]"

SYSTEM_TEMPLATE = (
    AGENT_MARKER
    + " tools=__TOOL_LIST__ max_steps=__MAX_STEPS__]\n"
    + "You are the dispatch agent for Switchyard, an LLM gateway. You finish one task at a time.\n"
    "Reply with exactly one JSON object. No markdown fences, no prose outside the object.\n"
    'To call a tool: {"tool": "calculator", "args": {"expression": "12 * 3"}}\n'
    'To finish: {"answer": "..."}\n'
    "Use the listed tools when the task asks for one, or when arithmetic, unit conversion, or a reference lookup is needed.\n"
    "For numeric tasks put only the final number in 'answer'. For descriptive tasks include each requested idea explicitly.\n"
    "Never invent tool results. If a tool errors, correct the arguments or finish with your best answer.\n"
    "Tools:\n" + "\n".join(f"- {spec['name']}: {spec['summary']}" for spec in TOOL_SPECS)
)


@dataclass
class AgentOutcome:
    answer: str
    trace: list[dict]
    request_ids: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    co2e_g: float
    energy_wh: float
    latency_ms: int
    error: str | None
    stopped_reason: str
    model: str
    provider: str
    tier: str

    @property
    def steps_count(self) -> int:
        return len(self.trace)

    def as_dict(self) -> dict:
        return {
            "answer": self.answer,
            "steps": self.trace,
            "steps_count": self.steps_count,
            "request_ids": self.request_ids,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
            },
            "cost_usd": self.cost_usd,
            "co2e_g": self.co2e_g,
            "energy_wh": self.energy_wh,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "stopped_reason": self.stopped_reason,
            "model": self.model,
            "provider": self.provider,
            "tier": self.tier,
        }


class AgentRunner:
    def __init__(self, pipeline: GatewayPipeline):
        self.pipeline = pipeline

    async def run(
        self,
        prompt: str,
        *,
        policy: str = "auto",
        tools: list[str] | None = None,
        max_steps: int = 4,
        source: str = "playground",
        batch_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentOutcome:
        available = [name for name in (tools or TOOL_NAMES) if name in TOOL_NAMES]
        max_steps = max(1, min(int(max_steps), 8))
        system = SYSTEM_TEMPLATE.replace("__TOOL_LIST__", "|".join(available) or "none").replace(
            "__MAX_STEPS__", str(max_steps)
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        trace: list[dict] = []
        request_ids: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
        co2e_g = 0.0
        energy_wh = 0.0
        started = time.perf_counter()
        model = ""
        provider = ""
        tier = ""

        for step_number in range(1, max_steps + 1):
            try:
                outcome = await self.pipeline.complete(
                    ChatCall(messages=messages, model=policy, temperature=0.1, max_tokens=500, cache=False),
                    source=source,
                    client="agent",
                    batch_id=batch_id,
                    run_id=run_id,
                    task_id=task_id,
                )
            except GatewayError as exc:
                trace.append(
                    {
                        "n": step_number,
                        "type": "gateway_error",
                        "ok": False,
                        "error": exc.message,
                        "request_id": exc.request_id,
                    }
                )
                return AgentOutcome(
                    answer="",
                    trace=trace,
                    request_ids=request_ids,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    co2e_g=co2e_g,
                    energy_wh=energy_wh,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=exc.message,
                    stopped_reason="gateway_error",
                    model=model,
                    provider=provider,
                    tier=tier,
                )

            request_ids.append(outcome.request_id)
            input_tokens += outcome.input_tokens
            output_tokens += outcome.output_tokens
            cost_usd += outcome.cost_usd
            co2e_g += outcome.co2e_g
            energy_wh += outcome.energy_wh
            model, provider, tier = outcome.model, outcome.provider, outcome.tier

            action = extract_action(outcome.text)
            if action is not None and "tool" in action:
                tool_name = str(action.get("tool", ""))
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                tool_started = time.perf_counter()
                if tool_name not in available:
                    ok, result = (
                        False,
                        f"tool '{tool_name}' is not available. Available: {', '.join(available)}",
                    )
                else:
                    try:
                        result = run_tool(tool_name, args)
                        ok = True
                    except ToolError as exc:
                        result = f"tool error: {exc}"
                        ok = False
                tool_ms = int((time.perf_counter() - tool_started) * 1000)
                trace.append(
                    {
                        "n": step_number,
                        "type": "tool",
                        "tool": tool_name,
                        "args": args,
                        "ok": ok,
                        "result": result[:500],
                        "latency_ms": tool_ms,
                        "request_id": outcome.request_id,
                        "model": outcome.model,
                        "tier": outcome.tier,
                        "route": outcome.route.as_dict(),
                    }
                )
                messages.append({"role": "assistant", "content": outcome.text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"TOOL RESULT ({tool_name}): {result}\n"
                            "Continue. Reply with the next JSON object (another tool call or the final answer)."
                        ),
                    }
                )
                continue

            if action is not None and "answer" in action:
                answer = str(action.get("answer", "")).strip()
                trace.append(
                    {
                        "n": step_number,
                        "type": "answer",
                        "ok": True,
                        "answer": answer[:1000],
                        "request_id": outcome.request_id,
                        "model": outcome.model,
                        "tier": outcome.tier,
                        "route": outcome.route.as_dict(),
                    }
                )
                return AgentOutcome(
                    answer=answer,
                    trace=trace,
                    request_ids=request_ids,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=round(cost_usd, 8),
                    co2e_g=round(co2e_g, 6),
                    energy_wh=round(energy_wh, 6),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=None,
                    stopped_reason="answered",
                    model=model,
                    provider=provider,
                    tier=tier,
                )

            # A provider that ignores the JSON protocol still deserves a fair read.
            answer = (outcome.text or "").strip()
            trace.append(
                {
                    "n": step_number,
                    "type": "answer",
                    "ok": True,
                    "answer": answer[:1000],
                    "request_id": outcome.request_id,
                    "model": outcome.model,
                    "tier": outcome.tier,
                    "route": outcome.route.as_dict(),
                    "note": "reply was not JSON; treated as final answer",
                }
            )
            return AgentOutcome(
                answer=answer,
                trace=trace,
                request_ids=request_ids,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=round(cost_usd, 8),
                co2e_g=round(co2e_g, 6),
                energy_wh=round(energy_wh, 6),
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=None,
                stopped_reason="non_json_answer",
                model=model,
                provider=provider,
                tier=tier,
            )

        trace.append(
            {
                "n": max_steps + 1,
                "type": "stop",
                "ok": False,
                "error": f"step budget of {max_steps} exhausted",
            }
        )
        return AgentOutcome(
            answer="",
            trace=trace,
            request_ids=request_ids,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 8),
            co2e_g=round(co2e_g, 6),
            energy_wh=round(energy_wh, 6),
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"step budget of {max_steps} exhausted",
            stopped_reason="max_steps",
            model=model,
            provider=provider,
            tier=tier,
        )


def extract_action(text: str) -> dict | None:
    if not text:
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("tool" in value or "answer" in value):
            return value
    return None
