from __future__ import annotations

import time

import httpx

from app.gateway.cost import estimate_message_tokens, estimate_tokens
from app.gateway.providers.base import Completion, Provider, ProviderError


class OpenAICompatProvider(Provider):
    """Works with Groq, OpenAI, Together, vLLM, Ollama and friends."""

    kind = "openai-compatible"

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        cheap_model: str,
        strong_model: str,
        timeout_s: float,
    ):
        super().__init__()
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.tier_models = {"thrift": cheap_model, "prime": strong_model}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=6.0, write=10.0, pool=5.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "switchyard/1.0",
            },
        )

    def info(self) -> dict:
        base = super().info()
        base.update(
            {
                "base_url": self.base_url,
                "configured": True,
            }
        )
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
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2 if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"X-Request-Id": request_id},
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"{self.name} timed out after {self._client.timeout.read}s",
                provider=self.name,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self.name} transport error: {exc.__class__.__name__}",
                provider=self.name,
                retryable=True,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            detail = _safe_detail(response)
            retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
            raise ProviderError(
                f"{self.name} returned {response.status_code}: {detail}",
                provider=self.name,
                retryable=retryable,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError(
                f"{self.name} returned an unexpected payload",
                provider=self.name,
                retryable=True,
            ) from exc

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or estimate_message_tokens(messages))
        output_tokens = int(usage.get("completion_tokens") or estimate_tokens(text))
        return Completion(
            text=text.strip(),
            provider=self.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason") or "stop",
        )

    async def probe(self) -> dict:
        started = time.perf_counter()
        try:
            completion = await self.chat(
                [{"role": "user", "content": "Reply with the single word: ready"}],
                self.tier_models["thrift"],
                0.0,
                8,
                "probe",
            )
            return {
                "ok": True,
                "provider": self.name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "sample": completion.text[:80],
            }
        except ProviderError as exc:
            return {
                "ok": False,
                "provider": self.name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": exc.message,
            }

    async def close(self) -> None:
        await self._client.aclose()


def _safe_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:240]
            if body.get("message"):
                return str(body["message"])[:240]
        return response.text[:240]
    except ValueError:
        return response.text[:240]
