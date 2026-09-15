"""Integration test against a running Agent Relay server and its real DB.

Unlike test_agent_relay.py (TestClient, in-process, scratch DB reset per
test), this hits an already-running server over HTTP -- SPEC.md acceptance
scenario 1: register two agents, exchange a task and its result.

Requires a server already running (see README): uv run uvicorn main:app
Set RELAY_BASE_URL to point elsewhere; defaults to the local dev server.
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.environ.get("RELAY_BASE_URL", "http://127.0.0.1:8000")


def register(client: httpx.Client, name: str) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/agents", json={"name": name})
    assert response.status_code == 201
    data = response.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


def test_two_agents_exchange_a_task_and_its_result():
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        sender, sender_headers = register(client, "live-sender")
        recipient, recipient_headers = register(client, "live-recipient")

        sent = client.post(
            "/api/v1/tasks",
            headers=sender_headers,
            json={"to": recipient["agent_id"], "input": "Review this Python function: def add(a,b): return a+b"},
        )
        assert sent.status_code == 201
        task_id = sent.json()["task_id"]
        assert sent.json()["status"] == "queued"

        claim = client.post(
            "/api/v1/tasks/claim",
            headers=recipient_headers,
            json={"worker_id": "live-scenario-worker", "wait_seconds": 5},
        )
        assert claim.status_code == 200
        claim_data = claim.json()
        assert claim_data["task_id"] == task_id
        assert claim_data["from"] == sender["agent_id"]

        complete = client.post(
            f"/api/v1/tasks/{task_id}/complete",
            headers=recipient_headers,
            json={"claim_token": claim_data["claim_token"], "output": "Looks correct, no off-by-one issues."},
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"

        result = client.get(f"/api/v1/tasks/{task_id}", headers=sender_headers)
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "completed"
        assert body["output"] == "Looks correct, no off-by-one issues."
        assert body["error"] is None
