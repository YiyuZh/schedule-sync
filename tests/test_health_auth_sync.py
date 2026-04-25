from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import initialize_database
from app.core.config import Settings, SettingsError
from app.main import app


initialize_database()
client = TestClient(app)


def unwrap(response):
    assert response.status_code < 500, response.text
    payload = response.json()
    assert payload["code"] == 0, payload
    return payload["data"]


def register(email: str, password: str = "password123"):
    return unwrap(
        client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": email.split("@")[0]},
        )
    )


def login(email: str, device_id: str, password: str = "password123"):
    return unwrap(
        client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": password,
                "device_id": device_id,
                "device_name": device_id,
                "device_type": "desktop",
            },
        )
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health():
    data = unwrap(client.get("/api/health"))
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_register_login_and_sync_user_isolation():
    suffix = uuid4().hex[:8]
    alice_email = f"alice-{suffix}@example.com"
    bob_email = f"bob-{suffix}@example.com"

    register(alice_email)
    register(bob_email)

    alice_desktop = login(alice_email, f"alice-desktop-{suffix}")
    alice_phone = login(alice_email, f"alice-phone-{suffix}")
    bob = login(bob_email, f"bob-desktop-{suffix}")

    push_data = unwrap(
        client.post(
            "/api/sync/push",
            headers=auth_headers(alice_desktop["access_token"]),
            json={
                "device_id": f"alice-desktop-{suffix}",
                "changes": [
                    {
                        "entity_type": "daily_task",
                        "entity_id": "local-1",
                        "operation": "upsert",
                        "payload": {
                            "sync_id": "task-sync-1",
                            "sync_version": 1,
                            "data": {"title": "数学学习", "ai_api_key": "must-not-store"},
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert push_data["accepted_count"] == 1

    alice_pull = unwrap(
        client.post(
            "/api/sync/pull",
            headers=auth_headers(alice_phone["access_token"]),
            json={"device_id": f"alice-phone-{suffix}", "since_change_id": 0},
        )
    )
    assert len(alice_pull["changes"]) == 1
    assert alice_pull["changes"][0]["entity_id"] == "task-sync-1"
    assert "ai_api_key" not in str(alice_pull["changes"][0]["payload"])

    bob_pull = unwrap(
        client.post(
            "/api/sync/pull",
            headers=auth_headers(bob["access_token"]),
            json={"device_id": f"bob-desktop-{suffix}", "since_change_id": 0},
        )
    )
    assert bob_pull["changes"] == []


def test_refresh_token_flow():
    suffix = uuid4().hex[:8]
    email = f"refresh-{suffix}@example.com"
    device_id = f"refresh-device-{suffix}"
    register(email)
    token_pair = login(email, device_id)

    refreshed = unwrap(
        client.post(
            "/api/auth/refresh",
            json={"refresh_token": token_pair["refresh_token"], "device_id": device_id},
        )
    )
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]


def test_device_register_endpoint():
    suffix = uuid4().hex[:8]
    email = f"device-{suffix}@example.com"
    register(email)
    token_pair = login(email, f"device-old-{suffix}")

    data = unwrap(
        client.post(
            "/api/devices/register",
            headers=auth_headers(token_pair["access_token"]),
            json={
                "device_id": f"device-new-{suffix}",
                "device_name": "New Device",
                "device_type": "desktop",
            },
        )
    )

    assert data["device_id"] == f"device-new-{suffix}"
    assert data["device_name"] == "New Device"


def test_push_conflict_keeps_rejected_item_metadata():
    suffix = uuid4().hex[:8]
    email = f"conflict-{suffix}@example.com"
    register(email)
    token_pair = login(email, f"conflict-device-{suffix}")
    headers = auth_headers(token_pair["access_token"])
    sync_id = f"conflict-task-{suffix}"

    first = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"conflict-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 101,
                        "entity_type": "daily_task",
                        "entity_id": "local-101",
                        "operation": "upsert",
                        "payload": {"sync_id": sync_id, "sync_version": 1, "data": {"title": "v1"}},
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert first["accepted_queue_ids"] == [101]

    second = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"conflict-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 102,
                        "entity_type": "daily_task",
                        "entity_id": sync_id,
                        "operation": "upsert",
                        "payload": {"sync_id": sync_id, "sync_version": 2, "data": {"title": "v2"}},
                        "base_version": 1,
                    }
                ],
            },
        )
    )
    assert second["accepted_queue_ids"] == [102]

    stale = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"conflict-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 103,
                        "entity_type": "daily_task",
                        "entity_id": sync_id,
                        "operation": "upsert",
                        "payload": {"sync_id": sync_id, "sync_version": 2, "data": {"title": "stale"}},
                        "base_version": 1,
                    }
                ],
            },
        )
    )
    assert stale["accepted_count"] == 0
    assert stale["rejected_count"] == 1
    assert stale["conflict_count"] == 1
    assert stale["rejected_items"][0]["queue_id"] == 103


def test_auth_rate_limit_returns_429():
    suffix = uuid4().hex[:8]
    email = f"rate-{suffix}@example.com"
    for _ in range(20):
        response = client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "wrong",
                "device_id": f"rate-device-{suffix}",
                "device_name": "Rate Device",
            },
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "wrong",
            "device_id": f"rate-device-{suffix}",
            "device_name": "Rate Device",
        },
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == 4290


def test_production_placeholder_config_is_rejected():
    settings = Settings(
        APP_ENV="production",
        APP_BASE_URL="https://sync.example.com",
        SCHEDULE_SYNC_DOMAIN="sync.example.com",
        DATABASE_URL="sqlite:///./data/schedule_sync.db",
        JWT_SECRET="dev-only-change-me-schedule-sync",
    )

    try:
        settings.validate_for_runtime()
    except SettingsError as exc:
        assert "生产配置不安全" in str(exc)
    else:
        raise AssertionError("production placeholder settings should be rejected")


def test_sync_accepts_mobile_flat_payload_and_desktop_envelope():
    suffix = uuid4().hex[:8]
    email = f"payload-{suffix}@example.com"
    register(email)
    desktop = login(email, f"payload-desktop-{suffix}")
    phone = login(email, f"payload-phone-{suffix}")
    headers = auth_headers(phone["access_token"])

    mobile_task_sync_id = f"mobile-task-{suffix}"
    pushed = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"payload-phone-{suffix}",
                "changes": [
                    {
                        "queue_id": 501,
                        "entity_type": "daily_task",
                        "entity_id": mobile_task_sync_id,
                        "operation": "upsert",
                        "payload": {
                            "sync_id": mobile_task_sync_id,
                            "sync_version": 1,
                            "title": "手机端任务",
                            "category": "Python",
                            "priority": "high",
                            "ai_api_key": "must-not-store",
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert pushed["accepted_queue_ids"] == [501]

    pulled = unwrap(
        client.post(
            "/api/sync/pull",
            headers=auth_headers(desktop["access_token"]),
            json={"device_id": f"payload-desktop-{suffix}", "since_change_id": 0},
        )
    )
    assert pulled["changes"][0]["entity_id"] == mobile_task_sync_id
    assert pulled["changes"][0]["payload"]["sync_id"] == mobile_task_sync_id
    assert "ai_api_key" not in str(pulled["changes"][0]["payload"])

    goal_sync_id = f"goal-{suffix}"
    subtask_sync_id = f"subtask-{suffix}"
    desktop_push = unwrap(
        client.post(
            "/api/sync/push",
            headers=auth_headers(desktop["access_token"]),
            json={
                "device_id": f"payload-desktop-{suffix}",
                "changes": [
                    {
                        "queue_id": 502,
                        "entity_type": "long_term_task",
                        "entity_id": goal_sync_id,
                        "operation": "upsert",
                        "payload": {
                            "entity_type": "long_term_task",
                            "sync_id": goal_sync_id,
                            "sync_version": 1,
                            "data": {"sync_id": goal_sync_id, "title": "长期目标"},
                        },
                        "base_version": 0,
                    },
                    {
                        "queue_id": 503,
                        "entity_type": "long_term_subtask",
                        "entity_id": subtask_sync_id,
                        "operation": "upsert",
                        "payload": {
                            "entity_type": "long_term_subtask",
                            "sync_id": subtask_sync_id,
                            "sync_version": 1,
                            "relation_sync_ids": {"long_task_sync_id": goal_sync_id},
                            "data": {
                                "sync_id": subtask_sync_id,
                                "long_task_id": 1,
                                "title": "子任务",
                            },
                        },
                        "base_version": 0,
                    },
                ],
            },
        )
    )
    assert desktop_push["accepted_queue_ids"] == [502, 503]

    phone_pull = unwrap(
        client.post(
            "/api/sync/pull",
            headers=headers,
            json={"device_id": f"payload-phone-{suffix}", "since_change_id": pushed["latest_change_id"]},
        )
    )
    subtask_change = next(item for item in phone_pull["changes"] if item["entity_id"] == subtask_sync_id)
    assert subtask_change["payload"]["relation_sync_ids"]["long_task_sync_id"] == goal_sync_id
