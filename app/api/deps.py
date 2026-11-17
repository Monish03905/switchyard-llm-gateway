from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException, Request

from app.config import Settings
from app.gateway.pipeline import GatewayPipeline
from app.gateway.registry import ProviderRegistry


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_pipeline(request: Request) -> GatewayPipeline:
    return request.app.state.pipeline


def get_registry(request: Request) -> ProviderRegistry:
    return request.app.state.registry


def client_identity(request: Request) -> tuple[str, str]:
    raw = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        raw = forwarded.split(",")[0].strip() or raw
    label = "ip_" + hashlib.sha256(raw.encode()).hexdigest()[:12]
    return raw, label


def enforce_rate_limit(request: Request) -> str:
    raw, label = client_identity(request)
    wait = request.app.state.limiter.check(raw)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached. Try again in {wait:.0f}s.",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    return label


def gateway_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    settings: Settings = request.app.state.settings
    if settings.gateway_api_key:
        expected = f"Bearer {settings.gateway_api_key}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=401,
                detail="A valid gateway API key is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        label = "api-key"
    else:
        _, label = client_identity(request)
    enforce_rate_limit(request)
    return label


def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> None:
    settings: Settings = request.app.state.settings
    if not settings.admin_token:
        return
    if not x_admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Admin token required for this lever.")
