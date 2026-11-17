from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.rate_limit import RateLimiter


def chat(client, prompt: str, **overrides):
    body = {"messages": [{"role": "user", "content": prompt}]}
    body.update(overrides)
    return client.post("/v1/chat/completions", json=body)


def test_health_models_and_metrics(api_client):
    health = api_client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["simulated"] is True
    assert body["checks"]["database"] == "ok"

    assert api_client.get("/api/health").json()["mode"] == "simulated"

    models = api_client.get("/api/models").json()
    assert models["mode"] == "simulated"
    assert set(models["aliases"]) == {"auto", "thrift", "prime"}
    assert len(models["models"]) == 2

    openai_models = api_client.get("/v1/models").json()
    assert openai_models["object"] == "list"
    assert any(row["id"] == "auto" for row in openai_models["data"])

    metrics = api_client.get("/metrics/prometheus")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "switchyard_requests_total" in metrics.text
    assert "switchyard_provider_mode 0" in metrics.text


def test_chat_completion_returns_openai_shape_and_receipt(api_client):
    response = chat(api_client, "What is 47 * 13?")
    assert response.status_code == 200
    body = response.json()

    assert body["object"] == "chat.completion"
    assert body["model"] == "sim-shunter"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "611"
    assert body["usage"]["total_tokens"] >= 1

    switchyard = body["switchyard"]
    assert switchyard["request_id"] == body["id"]
    assert switchyard["tier"] == "thrift"
    assert switchyard["mode"] == "simulated"
    assert switchyard["cache_hit"] is False
    assert switchyard["cost_usd"] > 0
    assert switchyard["saved_usd"] > 0
    assert switchyard["route"]["reasons"]

    receipt = api_client.get(f"/api/requests/{body['id']}").json()
    assert receipt["status"] == "ok"
    assert receipt["prompt_text"] is None
    assert len(receipt["entry_hash"]) == 64
    assert len(receipt["prev_hash"]) == 64

    assert api_client.get("/api/requests/req_missing").status_code == 404


def test_cache_header_bypasses_the_cache(api_client):
    prompt = "Say the same thing twice."
    first = chat(api_client, prompt)
    cached = chat(api_client, prompt)
    bypass = chat(api_client, prompt, cache=False)

    assert first.json()["switchyard"]["cache_hit"] is False
    assert cached.json()["switchyard"]["cache_hit"] is True
    assert cached.json()["switchyard"]["cost_usd"] == 0.0
    assert bypass.json()["switchyard"]["cache_hit"] is False


def test_validation_errors_use_the_json_envelope(api_client):
    empty = api_client.post("/v1/chat/completions", json={"messages": []})
    assert empty.status_code == 422
    error = empty.json()["error"]
    assert error["type"] == "validation_error"
    assert error["code"] == "validation_error"

    blank = chat(api_client, "")
    assert blank.status_code == 422
    assert "content" in blank.json()["error"]["message"]

    dispatch = api_client.post("/api/dispatch", json={"prompt": ""})
    assert dispatch.status_code == 422


def test_dispatch_runs_the_agent_with_tools(api_client):
    response = api_client.post(
        "/api/dispatch",
        json={"prompt": "What is 84 * 19?", "use_tools": True, "max_steps": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "simulated"
    agent = body["agent"]
    assert agent["answer"] == "1596"
    assert [step["type"] for step in agent["steps"]] == ["tool", "answer"]
    assert agent["steps"][0]["tool"] == "calculator"


def test_gateway_key_can_be_enforced(api_client):
    api_client.app.state.settings.gateway_api_key = "gate-key"
    try:
        blocked = chat(api_client, "hello")
        assert blocked.status_code == 401
        assert blocked.json()["error"]["type"] == "http_error"
        assert blocked.headers["www-authenticate"] == "Bearer"

        allowed = api_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"Authorization": "Bearer gate-key"},
        )
        assert allowed.status_code == 200
    finally:
        api_client.app.state.settings.gateway_api_key = ""


def test_rate_limit_returns_429_with_retry_after(api_client):
    api_client.app.state.limiter = RateLimiter(2)
    assert api_client.post("/api/dispatch", json={"prompt": "one"}).status_code == 200
    assert api_client.post("/api/dispatch", json={"prompt": "two"}).status_code == 200

    limited = api_client.post("/api/dispatch", json={"prompt": "three"})
    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "http_error"
    assert int(limited.headers["retry-after"]) >= 1


def test_admin_levers_require_the_token(api_client, admin_headers):
    assert api_client.get("/api/admin/state").status_code == 401
    assert api_client.post("/api/admin/squall", json={"fails": 1}).status_code == 401
    assert api_client.post("/api/admin/cache/purge").status_code == 401
    assert api_client.post("/api/providers/simulator/probe").status_code == 401

    state = api_client.get("/api/admin/state", headers=admin_headers)
    assert state.status_code == 200
    body = state.json()
    assert body["simulated"] is True
    assert body["flags"]["admin_token_required"] is True
    assert body["flags"]["store_prompts"] is False
    assert body["levers"]["squall"]["armed"] == 0
    assert body["levers"]["chain"]["ok"] is True

    probe = api_client.post("/api/providers/simulator/probe", headers=admin_headers)
    assert probe.status_code == 200
    assert probe.json()["ok"] is True

    purge = api_client.post("/api/admin/cache/purge", headers=admin_headers)
    assert purge.status_code == 200
    assert purge.json()["removed"] >= 0

    reset = api_client.post("/api/admin/breakers/reset", headers=admin_headers)
    assert reset.status_code == 200
    assert reset.json()["ok"] is True


def test_squall_drives_the_error_envelope_then_recovers(api_client, admin_headers):
    armed = api_client.post("/api/admin/squall", json={"fails": 10}, headers=admin_headers).json()
    assert armed["squall"]["armed"] == 10

    failed = chat(api_client, "Explain why retries need exponential backoff.")
    assert failed.status_code == 502
    error = failed.json()["error"]
    assert error["type"] == "all_routes_failed"
    assert error["request_id"].startswith("req_")

    disarmed = api_client.delete("/api/admin/squall", headers=admin_headers).json()
    assert disarmed["squall"]["armed"] == 0

    recovered = chat(api_client, "What is 47 * 13?")
    assert recovered.status_code == 200


def test_dashboard_reports_traffic_and_exports(api_client):
    first = chat(api_client, "What is 47 * 13?").json()
    chat(api_client, "What is 15% of 240?")

    overview = api_client.get("/api/overview").json()
    assert overview["meta"]["simulated"] is True
    assert overview["stats"]["requests"] == 2
    assert overview["stats"]["ok"] == 2
    assert overview["route_mix"]["total"] >= 2
    assert overview["recent"]
    assert overview["guardrails"]["chain"]["ok"] is True

    listing = api_client.get("/api/requests").json()
    assert listing["total"] == 2
    assert listing["items"][0]["id"]

    verify = api_client.get("/api/ledger/verify").json()
    assert verify["ok"] is True
    assert verify["entries"] == 2

    export = api_client.get("/api/requests/export.csv")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "input_tokens" in export.text

    chain = api_client.get("/api/ledger/export.csv")
    assert chain.status_code == 200
    assert "entry_hash" in chain.text

    providers = api_client.get("/api/providers").json()
    assert providers["mode"] == "simulated"
    assert providers["chaos"]["armed"] == 0

    assert first["switchyard"]["request_id"]


def test_gauntlet_batch_runs_over_http(api_client, admin_headers):
    response = api_client.post(
        "/api/evals/batches",
        json={"policies": ["thrift", "prime"], "label": "api batch", "task_ids": ["q01", "m01"]},
        headers=admin_headers,
    )
    assert response.status_code == 202
    batch = response.json()["batch"]
    assert batch["tasks_total"] == 4

    deadline = time.time() + 15
    detail = batch
    while time.time() < deadline:
        detail = api_client.get(f"/api/evals/batches/{batch['id']}").json()
        if detail["status"] in {"completed", "cancelled", "failed"}:
            break
        time.sleep(0.05)

    assert detail["status"] == "completed"
    assert detail["tasks_done"] == 4
    runs = {run["policy"]: run for run in detail["runs"]}
    assert runs["thrift"]["pass_rate"] == 0.5
    assert runs["prime"]["pass_rate"] == 1.0
    assert detail["comparison"]["thrift_vs_prime"]["pass_delta_pts"] == -50.0

    results = api_client.get(f"/api/evals/batches/{batch['id']}/results").json()
    assert results["total"] == 4
    assert all(result["request_ids"] for result in results["results"])

    export = api_client.get(f"/api/evals/batches/{batch['id']}/results.csv")
    assert export.status_code == 200
    assert "policy" in export.text

    tasks = api_client.get("/api/evals/tasks").json()
    assert tasks["total"] == len(tasks["tasks"]) == 36
    task = api_client.get("/api/evals/tasks/q01").json()
    assert task["id"] == "q01"
    assert task["route"]["tier"] == "thrift"
    assert api_client.get("/api/evals/tasks/nope").status_code == 404

    route_map = api_client.get("/api/evals/route-map?policy=thrift").json()
    assert route_map["counts"]["thrift"] == 36
    assert len(route_map["tasks"]) == 36


def test_spa_fallback_serves_the_cockpit(client_factory):
    dist = Path(__file__).resolve().parents[1] / "web" / "dist" / "index.html"
    if not dist.exists():
        pytest.skip("web/dist is not built")

    with client_factory(serve_frontend=True) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert root.headers["content-type"].startswith("text/html")

        deep_link = client.get("/dispatch")
        assert deep_link.status_code == 200
        assert deep_link.headers["content-type"].startswith("text/html")

        reserved = client.get("/api/definitely-not-here")
        assert reserved.status_code == 404
        assert reserved.json()["error"]["type"] == "http_error"
