#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:${SCHEDULE_SYNC_PREVIEW_PORT:-18130}}"

python3 - "$BASE_URL" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
suffix = str(int(time.time()))


def request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {body}") from exc
    payload = json.loads(body)
    if payload.get("code") != 0:
        raise RuntimeError(f"{method} {path} failed: {payload}")
    return payload.get("data") or {}


def register(email: str) -> None:
    request("POST", "/api/auth/register", {"email": email, "password": "password123", "display_name": email.split("@")[0]})


def login(email: str, device_id: str) -> str:
    data = request(
        "POST",
        "/api/auth/login",
        {
            "email": email,
            "password": "password123",
            "device_id": device_id,
            "device_name": device_id,
            "device_type": "desktop",
        },
    )
    return data["access_token"]


health = request("GET", "/api/health")
assert health["status"] == "ok", health
assert health["db"] == "ok", health

alice = f"smoke-alice-{suffix}@example.com"
bob = f"smoke-bob-{suffix}@example.com"
register(alice)
register(bob)

alice_pc = login(alice, f"alice-pc-{suffix}")
alice_phone = login(alice, f"alice-phone-{suffix}")
bob_pc = login(bob, f"bob-pc-{suffix}")

push = request(
    "POST",
    "/api/sync/push",
    {
        "device_id": f"alice-pc-{suffix}",
        "changes": [
            {
                "queue_id": 1,
                "entity_type": "daily_task",
                "entity_id": f"local-{suffix}",
                "operation": "upsert",
                "payload": {
                    "sync_id": f"task-sync-{suffix}",
                    "sync_version": 1,
                    "data": {"title": "smoke task", "ai_api_key": "must-not-store"},
                },
                "base_version": 0,
            }
        ],
    },
    alice_pc,
)
assert push["accepted_count"] == 1, push
assert push["accepted_queue_ids"] == [1], push

alice_pull = request("POST", "/api/sync/pull", {"device_id": f"alice-phone-{suffix}", "since_change_id": 0}, alice_phone)
assert len(alice_pull["changes"]) == 1, alice_pull
assert "ai_api_key" not in json.dumps(alice_pull["changes"][0]["payload"], ensure_ascii=False), alice_pull

bob_pull = request("POST", "/api/sync/pull", {"device_id": f"bob-pc-{suffix}", "since_change_id": 0}, bob_pc)
assert bob_pull["changes"] == [], bob_pull

delete = request(
    "POST",
    "/api/sync/push",
    {
        "device_id": f"alice-pc-{suffix}",
        "changes": [
            {
                "queue_id": 2,
                "entity_type": "daily_task",
                "entity_id": f"task-sync-{suffix}",
                "operation": "delete",
                "payload": {"sync_id": f"task-sync-{suffix}", "sync_version": 2, "sync_deleted": True},
                "base_version": 1,
            }
        ],
    },
    alice_pc,
)
assert delete["accepted_count"] == 1, delete

print("[schedule-sync] smoke test passed:", base_url)
PY
