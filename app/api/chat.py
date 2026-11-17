from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request

from app.agent.runner import AgentRunner
from app.api.deps import enforce_rate_limit, gateway_auth
from app.gateway.cost import CATALOG
from app.gateway.pipeline import ChatCall, GatewayError, GatewayPipeline
from app.gateway.router import normalize_policy
from app.schemas import ChatCompletionRequest, DispatchRequest

router = APIRouter(tags=["gateway"])


def _openai_payload(outcome, mode: str) -> dict:
    return {
        "id": outcome.request_id,
        "object": "chat.completion",
        "created": int(datetime.fromisoformat(outcome.created_at).timestamp()),
        "model": outcome.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": outcome.text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": outcome.input_tokens,
            "completion_tokens": outcome.output_tokens,
            "total_tokens": outcome.total_tokens,
        },
        "switchyard": {
            "request_id": outcome.request_id,
            "mode": mode,
            "policy": outcome.policy,
            "tier": outcome.tier,
            "cache_hit": outcome.cache_hit,
            "fallback_used": outcome.fallback_used,
            "attempts": outcome.attempts,
            "route": outcome.route.as_dict(),
            "cost_usd": outcome.cost_usd,
            "saved_usd": outcome.saved_usd,
            "co2e_g": outcome.co2e_g,
            "latency_ms": outcome.latency_ms,
        },
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    client: str = Depends(gateway_auth),
    x_switchyard_cache: str | None = Header(default=None),
):
    pipeline: GatewayPipeline = request.app.state.pipeline
    use_cache = body.cache
    if use_cache is None:
        use_cache = (x_switchyard_cache or "").lower() != "off"
    outcome = await pipeline.complete(
        ChatCall(
            messages=[message.model_dump() for message in body.messages],
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            cache=use_cache,
        ),
        source="api",
        client=client,
    )
    return _openai_payload(outcome, request.app.state.registry.mode)


@router.get("/v1/models")
async def list_models(request: Request):
    registry = request.app.state.registry
    data = []
    for row in registry.model_catalog():
        data.append(
            {
                "id": row["model"],
                "object": "model",
                "created": 0,
                "owned_by": row["vendor"],
                "switchyard": row,
            }
        )
    for alias in ("auto", "thrift", "prime"):
        data.append(
            {
                "id": alias,
                "object": "model",
                "created": 0,
                "owned_by": "switchyard",
                "switchyard": {"tier": "router" if alias == "auto" else alias},
            }
        )
    return {"object": "list", "data": data, "mode": registry.mode}


@router.post("/api/dispatch")
async def dispatch(
    body: DispatchRequest,
    request: Request,
    _client: str = Depends(enforce_rate_limit),
):
    pipeline: GatewayPipeline = request.app.state.pipeline
    agent: AgentRunner = request.app.state.agent
    mode = request.app.state.registry.mode
    policy = normalize_policy(body.policy)

    if body.use_tools:
        outcome = await agent.run(
            body.prompt,
            policy=policy,
            max_steps=body.max_steps,
            source="playground",
        )
        return {"mode": mode, "agent": outcome.as_dict()}

    try:
        outcome = await pipeline.complete(
            ChatCall(
                messages=[{"role": "user", "content": body.prompt}],
                model=policy,
                temperature=0.2,
                max_tokens=1024,
                cache=True,
            ),
            source="playground",
            client="playground",
        )
    except GatewayError:
        raise
    return {"mode": mode, "completion": outcome.as_dict()}


@router.get("/api/models")
async def public_models(request: Request):
    registry = request.app.state.registry
    return {
        "mode": registry.mode,
        "models": registry.model_catalog(),
        "aliases": ["auto", "thrift", "prime"],
        "prices_note": "USD per million tokens. Edit the sheet in app/gateway/cost.py.",
        "catalog_size": len(CATALOG),
    }
