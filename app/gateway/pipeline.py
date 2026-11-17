from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import Settings
from app.gateway.breaker import CircuitBreaker
from app.gateway.cache import ResponseCache, make_cache_key
from app.gateway.cost import (
    call_cost_usd,
    call_energy_wh,
    estimate_message_tokens,
)
from app.gateway.ledger import (
    Ledger,
    iso_from_ms,
    new_request_id,
    now_ms,
    preview,
)
from app.gateway.providers.base import ProviderError
from app.gateway.registry import Candidate, ProviderRegistry
from app.gateway.router import RouteDecision, choose_tier
from app.models import GatewayRequest


class GatewayError(Exception):
    def __init__(self, message: str, *, status_code: int, request_id: str = "", kind: str = "gateway_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.kind = kind


@dataclass
class GatewayOutcome:
    request_id: str
    text: str
    policy: str
    tier: str
    provider: str
    model: str
    status: str
    cache_hit: bool
    fallback_used: bool
    attempts: list
    input_tokens: int
    output_tokens: int
    cost_usd: float
    baseline_cost_usd: float
    saved_usd: float
    energy_wh: float
    baseline_energy_wh: float
    co2e_g: float
    baseline_co2e_g: float
    saved_co2e_g: float
    latency_ms: int
    created_at: str
    route: RouteDecision
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "policy": self.policy,
            "tier": self.tier,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "cache_hit": self.cache_hit,
            "fallback_used": self.fallback_used,
            "attempts": self.attempts,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
            },
            "cost_usd": self.cost_usd,
            "baseline_cost_usd": self.baseline_cost_usd,
            "saved_usd": self.saved_usd,
            "energy_wh": self.energy_wh,
            "co2e_g": self.co2e_g,
            "saved_co2e_g": self.saved_co2e_g,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            "route": self.route.as_dict(),
            "error": self.error,
        }


@dataclass
class ChatCall:
    messages: list[dict]
    model: str = "auto"
    temperature: float | None = 0.2
    max_tokens: int = 1024
    cache: bool = True


class GatewayPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        registry: ProviderRegistry,
        cache: ResponseCache,
        breaker: CircuitBreaker,
        ledger: Ledger,
        session_factory,
    ):
        self.settings = settings
        self.registry = registry
        self.cache = cache
        self.breaker = breaker
        self.ledger = ledger
        self.session_factory = session_factory

    async def complete(
        self,
        call: ChatCall,
        *,
        source: str = "api",
        client: str = "",
        batch_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> GatewayOutcome:
        started = time.perf_counter()
        created_ms = now_ms()
        created_at = iso_from_ms(created_ms)
        request_id = new_request_id()

        # Route on the human turn(s). Agent scaffolding and fixed system prompts are overhead,
        # not evidence about task difficulty; including them would push every agent call uphill.
        route_messages = [m for m in call.messages if m.get("role") == "user"] or call.messages
        route = choose_tier(route_messages, policy=call.model, requested_model=call.model)
        budget = await self._budget_state()
        if route.tier == "prime" and route.policy == "auto" and budget["limit"] > 0:
            estimated_input = estimate_message_tokens(call.messages)
            projected = call_cost_usd(self.registry.baseline_model(), estimated_input, call.max_tokens)
            if budget["remaining"] < projected:
                route.tier = "thrift"
                route.reasons = [
                    {"label": "budget guard downgraded this request", "weight": 1.0}
                ] + route.reasons
                route.summary = "budget guard: " + route.summary
                route.confidence = min(route.confidence, 0.5)

        candidates = self.registry.candidates(route.tier, route.pinned_model)
        key = make_cache_key(
            self.registry.mode,
            route.tier,
            candidates[0].provider.name if candidates else "",
            candidates[0].model if candidates else "",
            call.messages,
            call.temperature,
        )
        prompt_hash, prompt_preview, prompt_text = _prompt_fields(call.messages, self.settings)

        if call.cache:
            cached = await self.cache.get(key)
            if cached is not None:
                return await self._finish_cache_hit(
                    cached,
                    request_id=request_id,
                    created_ms=created_ms,
                    created_at=created_at,
                    route=route,
                    call=call,
                    source=source,
                    client=client,
                    batch_id=batch_id,
                    run_id=run_id,
                    task_id=task_id,
                    prompt_hash=prompt_hash,
                    prompt_preview=prompt_preview,
                    prompt_text=prompt_text,
                    started=started,
                )

        if budget["limit"] > 0 and budget["remaining"] <= 0:
            await self._persist_blocked(
                request_id=request_id,
                created_ms=created_ms,
                created_at=created_at,
                route=route,
                call=call,
                source=source,
                client=client,
                batch_id=batch_id,
                run_id=run_id,
                task_id=task_id,
                prompt_hash=prompt_hash,
                prompt_preview=prompt_preview,
                prompt_text=prompt_text,
                error="Daily budget exhausted. The yard will reopen at 00:00 UTC.",
            )
            raise GatewayError(
                "Daily budget exhausted. The yard will reopen at 00:00 UTC.",
                status_code=402,
                request_id=request_id,
                kind="budget_exhausted",
            )

        attempts: list[dict] = []
        success = None
        success_candidate: Candidate | None = None
        success_index = -1
        last_error: Exception | None = None
        usable = [c for c in candidates if self.breaker.allow(c.provider.name)]
        if not usable:
            # Every circuit is open: make one best-effort pass so a probe can close them.
            usable = candidates

        for index, candidate in enumerate(usable):
            for retry in range(self.settings.max_retries + 1):
                call_started = time.perf_counter()
                try:
                    completion = await candidate.provider.chat(
                        call.messages,
                        candidate.model,
                        call.temperature,
                        call.max_tokens,
                        request_id,
                    )
                except ProviderError as exc:
                    self.breaker.record_failure(candidate.provider.name)
                    last_error = exc
                    attempts.append(
                        {
                            "provider": candidate.provider.name,
                            "model": candidate.model,
                            "tier": candidate.tier,
                            "status": "error",
                            "error": exc.message,
                            "status_code": exc.status_code,
                            "retryable": exc.retryable,
                            "retry": retry,
                            "latency_ms": int((time.perf_counter() - call_started) * 1000),
                        }
                    )
                    if not exc.retryable:
                        break
                    if retry < self.settings.max_retries:
                        await self._backoff(retry)
                        continue
                    break
                except Exception as exc:  # defensive: a provider bug must not take the yard down
                    self.breaker.record_failure(candidate.provider.name)
                    last_error = ProviderError(
                        f"{candidate.provider.name} raised {exc.__class__.__name__}",
                        provider=candidate.provider.name,
                        retryable=True,
                    )
                    attempts.append(
                        {
                            "provider": candidate.provider.name,
                            "model": candidate.model,
                            "tier": candidate.tier,
                            "status": "error",
                            "error": f"{exc.__class__.__name__}",
                            "retry": retry,
                            "latency_ms": int((time.perf_counter() - call_started) * 1000),
                        }
                    )
                    if retry < self.settings.max_retries:
                        await self._backoff(retry)
                        continue
                    break
                else:
                    self.breaker.record_success(candidate.provider.name)
                    success = completion
                    success_candidate = candidate
                    success_index = index
                    attempts.append(
                        {
                            "provider": completion.provider,
                            "model": completion.model,
                            "tier": candidate.tier,
                            "status": "ok",
                            "latency_ms": completion.latency_ms,
                            "retry": retry,
                        }
                    )
                    break
            if success is not None:
                break

        latency_ms = max(1, int((time.perf_counter() - started) * 1000))

        if success is None or success_candidate is None:
            error_message = (
                last_error.message if isinstance(last_error, ProviderError) else "All provider routes failed"
            )
            await self._persist_error(
                request_id=request_id,
                created_ms=created_ms,
                created_at=created_at,
                route=route,
                call=call,
                source=source,
                client=client,
                batch_id=batch_id,
                run_id=run_id,
                task_id=task_id,
                prompt_hash=prompt_hash,
                prompt_preview=prompt_preview,
                prompt_text=prompt_text,
                attempts=attempts,
                latency_ms=latency_ms,
                error=error_message,
            )
            raise GatewayError(
                f"All routes failed after {len(attempts)} attempt(s): {error_message}",
                status_code=502,
                request_id=request_id,
                kind="all_routes_failed",
            )

        cost = call_cost_usd(success.model, success.input_tokens, success.output_tokens)
        baseline_model = self.registry.baseline_model()
        baseline_cost = call_cost_usd(baseline_model, success.input_tokens, success.output_tokens)
        energy_wh, co2e_g = call_energy_wh(
            success.model,
            success.input_tokens + success.output_tokens,
            self.settings.carbon_intensity_g_per_kwh,
            self.settings.datacenter_pue,
        )
        baseline_energy_wh, baseline_co2e_g = call_energy_wh(
            baseline_model,
            success.input_tokens + success.output_tokens,
            self.settings.carbon_intensity_g_per_kwh,
            self.settings.datacenter_pue,
        )
        fallback_used = success_index > 0

        outcome = GatewayOutcome(
            request_id=request_id,
            text=success.text,
            policy=route.policy,
            tier=success_candidate.tier,
            provider=success.provider,
            model=success.model,
            status="ok",
            cache_hit=False,
            fallback_used=fallback_used,
            attempts=attempts,
            input_tokens=success.input_tokens,
            output_tokens=success.output_tokens,
            cost_usd=round(cost, 8),
            baseline_cost_usd=round(baseline_cost, 8),
            saved_usd=round(max(0.0, baseline_cost - cost), 8),
            energy_wh=round(energy_wh, 6),
            baseline_energy_wh=round(baseline_energy_wh, 6),
            co2e_g=round(co2e_g, 6),
            baseline_co2e_g=round(baseline_co2e_g, 6),
            saved_co2e_g=round(max(0.0, baseline_co2e_g - co2e_g), 6),
            latency_ms=latency_ms,
            created_at=created_at,
            route=route,
        )

        row = self._row_from_outcome(
            outcome,
            created_ms=created_ms,
            source=source,
            client=client,
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            prompt_text=prompt_text,
            response_text=success.text,
            batch_id=batch_id,
            run_id=run_id,
            task_id=task_id,
            attempts=attempts,
            requested_model=call.model,
        )
        async with self.session_factory() as session:
            await self.ledger.append(session, row)

        if call.cache:
            await self.cache.set(
                key,
                {
                    "text": success.text,
                    "provider": success.provider,
                    "model": success.model,
                    "tier": success_candidate.tier,
                    "input_tokens": success.input_tokens,
                    "output_tokens": success.output_tokens,
                    "finish_reason": success.finish_reason,
                },
            )

        return outcome

    async def _finish_cache_hit(
        self,
        cached: dict,
        *,
        request_id: str,
        created_ms: int,
        created_at: str,
        route: RouteDecision,
        call: ChatCall,
        source: str,
        client: str,
        batch_id: str | None,
        run_id: str | None,
        task_id: str | None,
        prompt_hash: str,
        prompt_preview: str,
        prompt_text: str | None,
        started: float,
    ) -> GatewayOutcome:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        input_tokens = int(cached.get("input_tokens", 0))
        output_tokens = int(cached.get("output_tokens", 0))
        baseline_model = self.registry.baseline_model()
        baseline_cost = call_cost_usd(baseline_model, input_tokens, output_tokens)
        baseline_energy_wh, baseline_co2e_g = call_energy_wh(
            baseline_model,
            input_tokens + output_tokens,
            self.settings.carbon_intensity_g_per_kwh,
            self.settings.datacenter_pue,
        )
        attempts = [
            {
                "provider": cached.get("provider", ""),
                "model": cached.get("model", ""),
                "tier": cached.get("tier", route.tier),
                "status": "cache",
                "latency_ms": latency_ms,
            }
        ]
        outcome = GatewayOutcome(
            request_id=request_id,
            text=cached.get("text", ""),
            policy=route.policy,
            tier=cached.get("tier", route.tier),
            provider=cached.get("provider", ""),
            model=cached.get("model", ""),
            status="ok",
            cache_hit=True,
            fallback_used=False,
            attempts=attempts,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            baseline_cost_usd=round(baseline_cost, 8),
            saved_usd=round(baseline_cost, 8),
            energy_wh=0.0,
            baseline_energy_wh=round(baseline_energy_wh, 6),
            co2e_g=0.0,
            baseline_co2e_g=round(baseline_co2e_g, 6),
            saved_co2e_g=round(max(0.0, baseline_co2e_g), 6),
            latency_ms=latency_ms,
            created_at=created_at,
            route=route,
        )
        row = self._row_from_outcome(
            outcome,
            created_ms=created_ms,
            source=source,
            client=client,
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            prompt_text=prompt_text,
            response_text=outcome.text,
            batch_id=batch_id,
            run_id=run_id,
            task_id=task_id,
            attempts=attempts,
            requested_model=call.model,
        )
        async with self.session_factory() as session:
            await self.ledger.append(session, row)
        return outcome

    async def _persist_blocked(
        self,
        *,
        request_id: str,
        created_ms: int,
        created_at: str,
        route: RouteDecision,
        call: ChatCall,
        source: str,
        client: str,
        batch_id: str | None,
        run_id: str | None,
        task_id: str | None,
        prompt_hash: str,
        prompt_preview: str,
        prompt_text: str | None,
        error: str,
    ) -> None:
        row = GatewayRequest(
            id=request_id,
            created_at=created_at,
            created_ms=created_ms,
            source=source,
            policy=route.policy,
            requested_model=call.model,
            tier=route.tier,
            provider="",
            model="",
            status="blocked",
            cache_hit=False,
            fallback_used=False,
            attempts=0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            baseline_cost_usd=0.0,
            saved_usd=0.0,
            latency_ms=0,
            route_confidence=route.confidence,
            route_reason=route.summary,
            features_json=json.dumps(route.features),
            attempts_json="[]",
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            prompt_text=prompt_text,
            response_preview="",
            error=error,
            client=client,
            batch_id=batch_id,
            run_id=run_id,
            task_id=task_id,
        )
        async with self.session_factory() as session:
            await self.ledger.append(session, row)

    async def _persist_error(
        self,
        *,
        request_id: str,
        created_ms: int,
        created_at: str,
        route: RouteDecision,
        call: ChatCall,
        source: str,
        client: str,
        batch_id: str | None,
        run_id: str | None,
        task_id: str | None,
        prompt_hash: str,
        prompt_preview: str,
        prompt_text: str | None,
        attempts: list,
        latency_ms: int,
        error: str,
    ) -> None:
        last = attempts[-1] if attempts else {}
        row = GatewayRequest(
            id=request_id,
            created_at=created_at,
            created_ms=created_ms,
            source=source,
            policy=route.policy,
            requested_model=call.model,
            tier=last.get("tier", route.tier),
            provider=last.get("provider", ""),
            model=last.get("model", ""),
            status="error",
            cache_hit=False,
            fallback_used=len(attempts) > 1,
            attempts=len([a for a in attempts if a.get("status") == "error"]),
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            baseline_cost_usd=0.0,
            saved_usd=0.0,
            latency_ms=latency_ms,
            route_confidence=route.confidence,
            route_reason=route.summary,
            features_json=json.dumps(route.features),
            attempts_json=json.dumps(attempts),
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            prompt_text=prompt_text,
            response_preview="",
            error=error,
            client=client,
            batch_id=batch_id,
            run_id=run_id,
            task_id=task_id,
        )
        async with self.session_factory() as session:
            await self.ledger.append(session, row)

    def _row_from_outcome(
        self,
        outcome: GatewayOutcome,
        *,
        created_ms: int,
        source: str,
        client: str,
        prompt_hash: str,
        prompt_preview: str,
        prompt_text: str | None,
        response_text: str,
        batch_id: str | None,
        run_id: str | None,
        task_id: str | None,
        attempts: list,
        requested_model: str,
    ) -> GatewayRequest:
        return GatewayRequest(
            id=outcome.request_id,
            created_at=outcome.created_at,
            created_ms=created_ms,
            source=source,
            policy=outcome.policy,
            requested_model=requested_model,
            tier=outcome.tier,
            provider=outcome.provider,
            model=outcome.model,
            status=outcome.status,
            cache_hit=outcome.cache_hit,
            fallback_used=outcome.fallback_used,
            attempts=len([a for a in attempts if a.get("status") in {"ok", "error"}]),
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            total_tokens=outcome.total_tokens,
            cost_usd=outcome.cost_usd,
            baseline_cost_usd=outcome.baseline_cost_usd,
            saved_usd=outcome.saved_usd,
            energy_wh=outcome.energy_wh,
            baseline_energy_wh=outcome.baseline_energy_wh,
            co2e_g=outcome.co2e_g,
            baseline_co2e_g=outcome.baseline_co2e_g,
            saved_co2e_g=outcome.saved_co2e_g,
            latency_ms=outcome.latency_ms,
            route_confidence=outcome.route.confidence,
            route_reason=outcome.route.summary,
            features_json=json.dumps(outcome.route.features),
            attempts_json=json.dumps(attempts),
            prompt_hash=prompt_hash,
            prompt_preview=prompt_preview,
            prompt_text=prompt_text,
            response_preview=preview(response_text, 500),
            response_text=response_text if self.settings.store_prompts else None,
            error=None,
            client=client,
            batch_id=batch_id,
            run_id=run_id,
            task_id=task_id,
        )

    async def _budget_state(self) -> dict:
        start_ms = int(
            datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
        )
        async with self.session_factory() as session:
            spent = await session.scalar(
                select(func.coalesce(func.sum(GatewayRequest.cost_usd), 0.0)).where(
                    GatewayRequest.created_ms >= start_ms
                )
            )
        spent = float(spent or 0.0)
        limit = float(self.settings.daily_budget_usd)
        return {
            "limit": limit,
            "spent": round(spent, 8),
            "remaining": round(max(0.0, limit - spent), 8) if limit > 0 else 10**9,
            "start_ms": start_ms,
        }

    async def _backoff(self, retry: int) -> None:
        base = self.settings.retry_base_ms / 1000
        if base <= 0:
            return
        await asyncio.sleep(base * (2**retry) + random.uniform(0, 0.05))


def _prompt_fields(messages: list[dict], settings: Settings) -> tuple[str, str, str | None]:
    normalized = [
        {
            "role": str(m.get("role", "")),
            "content": " ".join(str(m.get("content", "")).lower().split()),
        }
        for m in messages
    ]
    prompt_hash = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    last_user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            last_user = str(message.get("content", ""))
            break
    prompt_preview = preview(last_user, 300)
    prompt_text = None
    if settings.store_prompts:
        prompt_text = "\n\n".join(f"[{message.get('role')}] {message.get('content')}" for message in messages)
    return prompt_hash, prompt_preview, prompt_text
