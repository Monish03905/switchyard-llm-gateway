from __future__ import annotations

import json

import httpx
import pytest

from app.gateway.providers.base import ProviderError
from app.gateway.providers.openai_compat import OpenAICompatProvider


@pytest.fixture(autouse=True)
def clean_proxy_env(monkeypatch):
    # httpx 0.28 cannot parse a bracketed IPv6 entry such as "[::1]" in NO_PROXY.
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(name, raising=False)


async def build_provider(handler) -> OpenAICompatProvider:
    provider = OpenAICompatProvider(
        name="groq",
        base_url="https://gateway.test/v1/",
        api_key="test-key",
        cheap_model="cheap-x",
        strong_model="strong-x",
        timeout_s=3,
    )
    headers = dict(provider._client.headers)
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=headers,
    )
    return provider


async def test_successful_chat_parses_usage_and_sends_auth():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "  hello world  "}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    provider = await build_provider(handler)
    completion = await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", 0.2, 64, "req_test")
    await provider.close()

    assert completion.text == "hello world"
    assert completion.provider == "groq"
    assert completion.model == "cheap-x"
    assert (completion.input_tokens, completion.output_tokens) == (7, 3)
    assert completion.finish_reason == "stop"

    request = seen[0]
    assert str(request.url) == "https://gateway.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["x-request-id"] == "req_test"
    payload = json.loads(request.content)
    assert payload["model"] == "cheap-x"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


async def test_missing_usage_falls_back_to_estimates():
    def handler(_request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "one two three four"}}]},
        )

    provider = await build_provider(handler)
    completion = await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", None, 32, "r")
    await provider.close()

    assert completion.input_tokens >= 1
    assert completion.output_tokens >= 1
    assert completion.finish_reason == "stop"


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (503, True), (401, False), (400, False)],
)
async def test_http_errors_are_classified(status, retryable):
    def handler(_request):
        return httpx.Response(status, json={"error": {"message": "rail is unhappy"}})

    provider = await build_provider(handler)
    with pytest.raises(ProviderError) as caught:
        await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", 0.1, 16, "r")
    await provider.close()

    assert caught.value.retryable is retryable
    assert caught.value.status_code == status
    assert "rail is unhappy" in caught.value.message


async def test_timeouts_and_transport_errors_are_retryable():
    def timeout_handler(_request):
        raise httpx.ReadTimeout("took too long")

    provider = await build_provider(timeout_handler)
    with pytest.raises(ProviderError) as caught:
        await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", 0.1, 16, "r")
    await provider.close()
    assert caught.value.retryable is True
    assert "timed out" in caught.value.message

    def broken_handler(_request):
        raise httpx.ConnectError("no route")

    provider = await build_provider(broken_handler)
    with pytest.raises(ProviderError) as caught:
        await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", 0.1, 16, "r")
    await provider.close()
    assert caught.value.retryable is True
    assert "transport error" in caught.value.message


async def test_malformed_payload_is_retryable():
    def handler(_request):
        return httpx.Response(200, json={"choices": []})

    provider = await build_provider(handler)
    with pytest.raises(ProviderError) as caught:
        await provider.chat([{"role": "user", "content": "hi"}], "cheap-x", 0.1, 16, "r")
    await provider.close()
    assert caught.value.retryable is True
    assert "unexpected payload" in caught.value.message


async def test_probe_reports_success_and_failure():
    def ok_handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "ready"}}]})

    provider = await build_provider(ok_handler)
    probe = await provider.probe()
    await provider.close()
    assert probe["ok"] is True
    assert probe["sample"] == "ready"

    def bad_handler(_request):
        return httpx.Response(503, text="down")

    provider = await build_provider(bad_handler)
    probe = await provider.probe()
    await provider.close()
    assert probe["ok"] is False
    assert "503" in probe["error"]
