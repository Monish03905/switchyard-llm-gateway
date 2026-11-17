"""Exercise every HTTP surface of a running Switchyard instance.

The pytest suite drives the app in-process. This script instead talks to a real
server, the real SQLite/Postgres ledger and the built cockpit, so the answer to
"does the whole thing actually work?" is one command:

    python scripts/smoke.py                    # defaults to 127.0.0.1:8000
    python scripts/smoke.py --base http://host:8000
    python scripts/smoke.py --with-gauntlet    # queue a real 36-task batch too

Only the Python standard library is used. Exit code 0 means every required
check passed; skipped admin checks are reported, not hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

JSON_HEADERS = {"accept": "application/json"}


def call(
    base: str,
    method: str,
    path: str,
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 45.0,
) -> tuple[int, dict[str, str], bytes]:
    url = base.rstrip("/") + path
    body = None
    request_headers = dict(JSON_HEADERS)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["content-type"] = "application/json"
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def payload_of(body: bytes) -> Any:
    return json.loads(body.decode("utf-8"))


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failures: list[tuple[str, str]] = []

    def check(self, name: str, fn) -> Any:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - a smoke test reports everything
            self.failed += 1
            self.failures.append((name, str(exc)))
            print(f"FAIL  {name}\n      {exc}")
            return None
        self.passed += 1
        suffix = f"  ({detail})" if detail else ""
        print(f"PASS  {name}{suffix}")
        return detail

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        print(f"SKIP  {name}  ({reason})")

    def summary(self) -> int:
        print()
        print(f"{self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        if self.failures:
            print("\nFailures:")
            for name, reason in self.failures:
                print(f"  - {name}: {reason}")
        return 0 if self.failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end HTTP smoke test for Switchyard.")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="Base URL of a running server.")
    parser.add_argument(
        "--admin-token",
        default=os.environ.get("ADMIN_TOKEN", ""),
        help="Admin token; defaults to the ADMIN_TOKEN environment variable.",
    )
    parser.add_argument(
        "--gateway-key",
        default=os.environ.get("GATEWAY_API_KEY", ""),
        help="Gateway bearer key; defaults to the GATEWAY_API_KEY environment variable.",
    )
    parser.add_argument(
        "--with-gauntlet",
        action="store_true",
        help="Also queue a 36-task router batch and wait for it (takes ~30s in simulator mode).",
    )
    parser.add_argument("--gauntlet-timeout", type=float, default=180.0)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    gateway_headers = {"authorization": f"Bearer {args.gateway_key}"} if args.gateway_key else {}
    admin_headers = {"x-admin-token": args.admin_token} if args.admin_token else {}
    run_id = datetime.now(UTC).strftime("%H%M%S") + f"-{os.getpid()}"
    runner = Runner()
    shared: dict[str, Any] = {}

    try:
        call(base, "GET", "/health", timeout=5.0)
    except Exception as exc:  # noqa: BLE001 - report a clear failure, not a traceback
        print(f"cannot reach {base}: {exc}")
        print("start the server first: uvicorn app.main:app --reload")
        return 1

    def get_json(path: str, headers: dict[str, str] | None = None) -> Any:
        status, _, body = call(base, "GET", path, headers=headers)
        if status != 200:
            raise AssertionError(f"HTTP {status}: {body[:200]!r}")
        return payload_of(body)

    def post_json(path: str, payload: Any, headers: dict[str, str] | None = None, expect: int = 200) -> Any:
        status, _, body = call(base, "POST", path, payload, headers=headers)
        if status != expect:
            raise AssertionError(f"expected {expect}, got {status}: {body[:200]!r}")
        return payload_of(body)

    # --- Liveness and discovery -------------------------------------------------
    def health() -> str:
        data = get_json("/health")
        assert data["status"] == "ok", data
        assert data["checks"].get("database") == "ok", data
        shared["health"] = data
        return f"mode={data['mode']}, version={data['version']}"

    runner.check("GET /health", health)

    def api_health() -> str:
        data = get_json("/api/health")
        assert data["status"] == "ok", data
        return data["status"]

    runner.check("GET /api/health", api_health)

    def models() -> str:
        public = get_json("/api/models")
        assert public["aliases"] == ["auto", "thrift", "prime"], public["aliases"]
        assert public["catalog_size"] >= 1
        openai = get_json("/v1/models")
        ids = {row["id"] for row in openai["data"]}
        assert {"auto", "thrift", "prime"} <= ids, ids
        shared["models"] = public
        return f"{public['catalog_size']} catalog rows, {len(openai['data'])} model ids"

    runner.check("GET /api/models + /v1/models", models)

    # --- Gateway and agent ------------------------------------------------------
    chat_prompt = f"Smoke {run_id}: what is 12 times 12? Reply with just the number."

    def chat() -> str:
        status, _, body = call(
            base,
            "POST",
            "/v1/chat/completions",
            {"model": "auto", "messages": [{"role": "user", "content": chat_prompt}], "cache": False},
            headers=gateway_headers,
        )
        if status == 401:
            raise AssertionError("401: set --gateway-key (or GATEWAY_API_KEY) to match the server")
        assert status == 200, f"HTTP {status}: {body[:200]!r}"
        data = payload_of(body)
        assert data["choices"][0]["message"]["content"], data
        audit = data["switchyard"]
        assert audit["tier"] in {"thrift", "prime"}, audit
        assert "route" in audit and "reasons" in audit["route"], audit
        assert data["usage"]["total_tokens"] > 0, data["usage"]
        return f"{audit['tier']} rail, {data['usage']['total_tokens']} tokens"

    runner.check("POST /v1/chat/completions", chat)

    def dispatch_plain() -> str:
        data = post_json(
            "/api/dispatch",
            {"prompt": f"Smoke {run_id}: explain failover in one sentence.", "policy": "auto"},
        )
        completion = data["completion"]
        assert completion["status"] == "ok", completion
        shared["completion"] = completion
        return f"{completion['tier']} rail, {completion['request_id'][:14]}"

    runner.check("POST /api/dispatch (completion)", dispatch_plain)

    agent_prompt = "Use the calculator tool. What is 42 + 57 + 31? Reply with the final number."

    def dispatch_agent() -> str:
        data = post_json(
            "/api/dispatch",
            {"prompt": agent_prompt, "policy": "auto", "use_tools": True, "max_steps": 4},
        )
        agent = data["agent"]
        assert "130" in str(agent["answer"]), agent["answer"]
        tools = [step for step in agent["steps"] if step["type"] == "tool"]
        assert tools and tools[0].get("tool") == "calculator", agent["steps"]
        assert agent["request_ids"], agent
        shared["agent"] = agent
        return (
            f"answer={agent['answer']!r}, {agent['steps_count']} steps, {len(agent['request_ids'])} receipts"
        )

    runner.check("POST /api/dispatch (agent + calculator)", dispatch_agent)

    # --- Dashboard, receipts, exports ------------------------------------------
    def overview() -> str:
        data = get_json("/api/overview?hours=24")
        assert data["stats"]["requests"] >= 1, data["stats"]
        assert data["guardrails"]["chain"]["ok"] is True, data["guardrails"]["chain"]
        assert data["providers"]["mode"] in {"simulated", "live"}, data["providers"]["mode"]
        shared["overview"] = data
        return f"{data['stats']['requests']} receipts in 24h, chain sealed"

    runner.check("GET /api/overview", overview)

    def receipt_list() -> str:
        data = get_json("/api/requests?limit=3")
        assert data["items"], data
        assert data["total"] >= len(data["items"]), data
        shared["receipt"] = data["items"][0]
        return f"{data['total']} receipts on file"

    runner.check("GET /api/requests", receipt_list)

    def receipt_detail() -> str:
        receipt_id = shared["receipt"]["id"]
        data = get_json(f"/api/requests/{receipt_id}")
        assert data["id"] == receipt_id, data
        for key in ("prev_hash", "entry_hash", "prompt_hash", "features"):
            assert key in data, f"missing {key}"
        assert data["seq"] >= 1
        return f"seq={data['seq']}, {len(data['attempts_detail'])} attempt(s)"

    runner.check("GET /api/requests/{id}", receipt_detail)

    def ledger_verify() -> str:
        data = get_json("/api/ledger/verify")
        assert data["ok"] is True, data
        assert data["entries"] >= 1, data
        return f"{data['entries']} links verified"

    runner.check("GET /api/ledger/verify", ledger_verify)

    def exports() -> str:
        status, _headers, body = call(base, "GET", "/api/requests/export.csv?hours=168")
        assert status == 200, status
        header = body.decode("utf-8", "replace").splitlines()[0]
        assert header.startswith("created_at,id,source"), header
        status, _headers, body = call(base, "GET", "/api/ledger/export.csv")
        assert status == 200, status
        header = body.decode("utf-8", "replace").splitlines()[0]
        assert header.startswith("seq,id,created_at"), header
        return "requests + chain CSV headers"

    runner.check("GET /api/requests/export.csv + /api/ledger/export.csv", exports)

    # --- Evals ------------------------------------------------------------------
    def tasks() -> str:
        data = get_json("/api/evals/tasks")
        assert data["total"] == 36, data["total"]
        shared["task"] = data["tasks"][0]
        return f"{data['total']} tasks in {len(data['categories'])} categories"

    runner.check("GET /api/evals/tasks", tasks)

    def task_detail() -> str:
        task_id = shared["task"]["id"]
        data = get_json(f"/api/evals/tasks/{task_id}")
        assert data["id"] == task_id, data
        assert data["expected"], data
        assert data["route"]["tier"] in {"thrift", "prime"}, data["route"]
        assert "threshold" in data["route"]["features"], data["route"]
        return f"{task_id}: {data['route']['tier']} rail, score {data['route']['score']:.2f}"

    runner.check("GET /api/evals/tasks/{id}", task_detail)

    def route_map() -> str:
        data = get_json("/api/evals/route-map?policy=auto")
        counts = data["counts"]
        assert counts["thrift"] + counts["prime"] == 36, counts
        return f"{counts['thrift']} thrift / {counts['prime']} prime"

    runner.check("GET /api/evals/route-map", route_map)

    def batches() -> str:
        data = get_json("/api/evals/batches")
        batch = data["items"][0]
        shared["batch"] = batch
        detail = get_json(f"/api/evals/batches/{batch['id']}")
        assert detail["tasks_done"] == detail["tasks_total"], detail
        results = get_json(f"/api/evals/batches/{batch['id']}/results?limit=5")
        assert results["results"], results
        status, _, body = call(base, "GET", f"/api/evals/batches/{batch['id']}/results.csv")
        assert status == 200, status
        header = body.decode("utf-8", "replace").splitlines()[0]
        assert header.startswith("batch_id,policy,task_id"), header
        return f"batch {batch['id'][:8]}, {len(detail.get('runs', []))} runs, CSV ok"

    list_status, _, list_body = call(base, "GET", "/api/evals/batches")
    if list_status == 200 and payload_of(list_body)["items"]:
        runner.check("GET /api/evals/batches[/{id}/results[.csv]]", batches)
    elif list_status == 200:
        runner.skip("GET /api/evals/batches[/{id}/results[.csv]]", "no batch yet; use --with-gauntlet")
    else:

        def batches_failed() -> None:
            raise AssertionError(f"HTTP {list_status}")

        runner.check("GET /api/evals/batches[/{id}/results[.csv]]", batches_failed)

    # --- Providers and admin ----------------------------------------------------
    def providers() -> str:
        data = get_json("/api/providers")
        assert data["providers"], data
        shared["provider"] = data["providers"][0]["name"]
        return f"{len(data['providers'])} provider(s), fallback={data['fallback_provider'] or 'none'}"

    runner.check("GET /api/providers", providers)

    def admin_state() -> str:
        status, _, body = call(base, "GET", "/api/admin/state", headers=admin_headers)
        assert status == 200, f"HTTP {status}: {body[:200]!r}"
        data = payload_of(body)
        assert data["levers"]["chain"]["ok"] is True, data["levers"]["chain"]
        return "levers unlocked"

    admin_status, _, _admin_body = call(base, "GET", "/api/admin/state", headers=admin_headers)
    if admin_status == 401:
        runner.skip("GET /api/admin/state", "admin token required")
    else:
        shared["admin"] = True
        runner.check("GET /api/admin/state", admin_state)

    if shared.get("admin"):

        def probe() -> str:
            result = post_json(f"/api/providers/{shared['provider']}/probe", {}, headers=admin_headers)
            assert result.get("provider") == shared["provider"], result
            return f"{shared['provider']} probe returned"

        runner.check("POST /api/providers/{name}/probe", probe)

        def levers() -> str:
            armed = post_json("/api/admin/squall", {"fails": 1}, headers=admin_headers)
            assert armed["squall"]["armed"] == 1, armed
            disarmed = json.loads(call(base, "DELETE", "/api/admin/squall", headers=admin_headers)[2])
            assert disarmed["squall"]["armed"] == 0, disarmed
            reset = post_json("/api/admin/breakers/reset", {}, headers=admin_headers)
            assert reset["ok"] is True, reset
            return "squall arm/disarm + breaker reset"

        runner.check("POST /api/admin/squall (+ DELETE, breakers reset)", levers)

    # --- Ops and cockpit --------------------------------------------------------
    def metrics() -> str:
        status, _headers, body = call(base, "GET", "/metrics/prometheus")
        assert status == 200, status
        text = body.decode("utf-8", "replace")
        assert "switchyard_" in text, text[:120]
        return "Prometheus text exposed"

    runner.check("GET /metrics/prometheus", metrics)

    def docs() -> str:
        status, _, _ = call(base, "GET", "/docs")
        assert status == 200, status
        return "/docs reachable"

    runner.check("GET /docs", docs)

    def cockpit() -> str:
        status, headers, body = call(base, "GET", "/")
        assert status == 200, status
        assert "text/html" in headers.get("content-type", ""), headers
        text = body.decode("utf-8", "replace")
        assert "index" in text and "SWITCHYARD" in text.upper(), text[:160]
        return "built cockpit served"

    runner.check("GET / (SPA)", cockpit)

    # --- Optional full gauntlet -------------------------------------------------
    if args.with_gauntlet:
        if not shared.get("admin"):
            runner.skip("POST /api/evals/batches", "admin token required")
        else:
            batch_status, _, batch_body = call(base, "GET", "/api/evals/batches")
            running = batch_status == 200 and payload_of(batch_body).get("running")
            if running:
                runner.skip("POST /api/evals/batches", "another gauntlet is already running")
            else:

                def gauntlet() -> str:
                    status, _, body = call(
                        base,
                        "POST",
                        "/api/evals/batches",
                        {"policies": ["yardmaster"], "label": f"smoke {run_id}"},
                        headers=admin_headers,
                    )
                    assert status == 202, f"HTTP {status}: {body[:200]!r}"
                    batch_id = payload_of(body)["batch"]["id"]
                    deadline = time.time() + args.gauntlet_timeout
                    batch: dict[str, Any] = {}
                    while time.time() < deadline:
                        batch = get_json(f"/api/evals/batches/{batch_id}")
                        if batch["status"] in {"completed", "cancelled", "failed"}:
                            break
                        time.sleep(2)
                    assert batch.get("status") == "completed", batch
                    assert batch["tasks_done"] == 36, batch
                    return f"batch {batch_id[:8]} completed 36 tasks"

                runner.check("POST /api/evals/batches (with-gate)", gauntlet)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
