from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings, SettingsError, get_settings
from app.core.database import SessionLocal, initialize_database
from app.core.security import hash_password
from app.main import app
from app.models.device import Device
from app.models.sync_change import SyncChange
from app.models.sync_record import SyncRecord
from app.models.user import User


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


def configure_test_admin(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "autsky6666@gmail.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Aut123456")
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    get_settings.cache_clear()


def admin_headers(monkeypatch) -> dict[str, str]:
    configure_test_admin(monkeypatch)
    token = unwrap(
        client.post(
            "/api/admin/login",
            json={"email": "autsky6666@gmail.com", "password": "Aut123456"},
        )
    )
    return auth_headers(token["access_token"])


def test_health():
    data = unwrap(client.get("/api/health"))
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_app_version_endpoint():
    data = unwrap(client.get("/api/app-version"))
    assert data["platform"] == "ios"
    assert data["latest_version"]
    assert data["minimum_supported_version"]
    assert "release_notes" in data


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
    assert push_data["accepted_items"][0]["entity_id"] == "task-sync-1"
    assert push_data["accepted_items"][0]["sync_version"] == 1

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


def test_admin_login_and_overview(monkeypatch):
    headers = admin_headers(monkeypatch)
    me = unwrap(client.get("/api/admin/me", headers=headers))
    assert me["email"] == "autsky6666@gmail.com"

    overview = unwrap(client.get("/api/admin/overview", headers=headers))
    assert overview["total_users"] >= 0
    assert overview["total_devices"] >= 0
    assert overview["total_sync_records"] >= 0
    assert len(overview["daily_active"]) == 30


def test_admin_wrong_password_is_rejected(monkeypatch):
    configure_test_admin(monkeypatch)
    response = client.post(
        "/api/admin/login",
        json={"email": "autsky6666@gmail.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == 4401


def test_normal_user_token_cannot_access_admin_api():
    suffix = uuid4().hex[:8]
    email = f"normal-admin-denied-{suffix}@example.com"
    register(email)
    token_pair = login(email, f"normal-admin-denied-device-{suffix}")
    response = client.get("/api/admin/overview", headers=auth_headers(token_pair["access_token"]))
    assert response.status_code in {401, 403}


def test_admin_users_search_and_detail(monkeypatch):
    suffix = uuid4().hex[:8]
    email = f"admin-search-{suffix}@example.com"
    register(email)
    login(email, f"admin-search-device-{suffix}")
    headers = admin_headers(monkeypatch)

    users = unwrap(client.get(f"/api/admin/users?search={email}", headers=headers))
    assert users["total"] >= 1
    found = next(item for item in users["items"] if item["email"] == email)
    assert found["device_count"] >= 1

    detail = unwrap(client.get(f"/api/admin/users/{found['id']}", headers=headers))
    assert detail["user"]["email"] == email
    assert detail["devices"]


def test_admin_delete_user_cleans_sync_data(monkeypatch):
    suffix = uuid4().hex[:8]
    email = f"admin-delete-{suffix}@example.com"
    register(email)
    token_pair = login(email, f"admin-delete-device-{suffix}")
    push_result = unwrap(
        client.post(
            "/api/sync/push",
            headers=auth_headers(token_pair["access_token"]),
            json={
                "device_id": f"admin-delete-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 701,
                        "entity_type": "daily_task",
                        "entity_id": f"delete-task-{suffix}",
                        "operation": "upsert",
                        "payload": {
                            "sync_id": f"delete-task-{suffix}",
                            "sync_version": 1,
                            "data": {"title": "delete me"},
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert push_result["accepted_count"] == 1

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        user_id = int(user.id)
        assert db.query(Device).filter(Device.user_id == user_id).count() >= 1
        assert db.query(SyncRecord).filter(SyncRecord.user_id == user_id).count() >= 1
        assert db.query(SyncChange).filter(SyncChange.user_id == user_id).count() >= 1

    headers = admin_headers(monkeypatch)
    deleted = unwrap(
        client.request(
            "DELETE",
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={"confirm_email": email},
        )
    )
    assert deleted["ok"] is True

    with SessionLocal() as db:
        assert db.get(User, user_id) is None
        assert db.query(Device).filter(Device.user_id == user_id).count() == 0
        assert db.query(SyncRecord).filter(SyncRecord.user_id == user_id).count() == 0
        assert db.query(SyncChange).filter(SyncChange.user_id == user_id).count() == 0


def test_admin_user_cannot_be_deleted(monkeypatch):
    headers = admin_headers(monkeypatch)
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "autsky6666@gmail.com").first()
        if user is None:
            user = User(
                email="autsky6666@gmail.com",
                password_hash=hash_password("not-used-by-admin-login"),
                display_name="Admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = int(user.id)

    response = client.request(
        "DELETE",
        f"/api/admin/users/{user_id}",
        headers=headers,
        json={"confirm_email": "autsky6666@gmail.com"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == 4406


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
    assert first["accepted_items"] == [
        {
            "queue_id": 101,
            "entity_type": "daily_task",
            "entity_id": sync_id,
            "sync_version": 1,
        }
    ]

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
    assert second["accepted_items"][0]["sync_version"] == 2

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


def test_daily_task_status_patch_uses_last_write_without_overwriting_content():
    suffix = uuid4().hex[:8]
    email = f"status-patch-{suffix}@example.com"
    register(email)
    token_pair = login(email, f"status-device-{suffix}")
    headers = auth_headers(token_pair["access_token"])
    sync_id = f"status-task-{suffix}"

    created = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"status-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 801,
                        "entity_type": "daily_task",
                        "entity_id": sync_id,
                        "operation": "upsert",
                        "payload": {
                            "sync_id": sync_id,
                            "sync_version": 1,
                            "data": {
                                "sync_id": sync_id,
                                "title": "保留标题",
                                "notes": "保留备注",
                                "status": "pending",
                                "completed_at": None,
                                "actual_duration_minutes": 0,
                                "updated_at": "2026-04-26 08:00:00",
                            },
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert created["accepted_count"] == 1

    newer_status = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"status-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 802,
                        "entity_type": "daily_task",
                        "entity_id": sync_id,
                        "operation": "upsert",
                        "payload": {
                            "entity_type": "daily_task",
                            "sync_id": sync_id,
                            "sync_version": 1,
                            "sync_scope": "daily_task_status",
                            "changed_fields": ["status", "completed_at", "actual_duration_minutes"],
                            "data": {
                                "sync_id": sync_id,
                                "title": "不应覆盖标题",
                                "status": "completed",
                                "completed_at": "2026-04-26 09:00:00",
                                "actual_duration_minutes": 30,
                                "updated_at": "2026-04-26 09:00:00",
                            },
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert newer_status["accepted_count"] == 1
    assert newer_status["rejected_count"] == 0

    older_status = unwrap(
        client.post(
            "/api/sync/push",
            headers=headers,
            json={
                "device_id": f"status-device-{suffix}",
                "changes": [
                    {
                        "queue_id": 803,
                        "entity_type": "daily_task",
                        "entity_id": sync_id,
                        "operation": "upsert",
                        "payload": {
                            "entity_type": "daily_task",
                            "sync_id": sync_id,
                            "sync_version": 1,
                            "sync_scope": "daily_task_status",
                            "changed_fields": ["status", "completed_at", "actual_duration_minutes"],
                            "data": {
                                "sync_id": sync_id,
                                "status": "pending",
                                "completed_at": None,
                                "actual_duration_minutes": 0,
                                "updated_at": "2026-04-26 08:30:00",
                            },
                        },
                        "base_version": 0,
                    }
                ],
            },
        )
    )
    assert older_status["accepted_count"] == 1
    assert older_status["rejected_count"] == 0

    with SessionLocal() as db:
        record = db.query(SyncRecord).filter(SyncRecord.entity_id == sync_id).one()
        payload = record.payload_json
    assert '"title":"保留标题"' in payload
    assert '"notes":"保留备注"' in payload
    assert '"status":"completed"' in payload
    assert '"actual_duration_minutes":30' in payload


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
    assert pushed["accepted_items"][0]["entity_id"] == mobile_task_sync_id

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
