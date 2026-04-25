from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import AppException
from app.models.device import Device
from app.models.sync_change import SyncChange
from app.models.sync_record import SyncRecord
from app.models.user import User
from app.schemas.sync import (
    SyncBootstrapRecord,
    SyncBootstrapResult,
    SyncChangeRead,
    SyncOperation,
    SyncPullRequest,
    SyncPullResult,
    SyncPushChange,
    SyncPushRequest,
    SyncPushResult,
    SyncRejectedItem,
)
from app.utils.datetime_utils import utc_now
from app.utils.json_utils import content_hash, dumps_json, loads_json, sanitize_payload


class SyncService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def push(self, user: User, payload: SyncPushRequest) -> SyncPushResult:
        self._ensure_device(user, payload.device_id)
        accepted = 0
        rejected = 0
        conflict_count = 0
        accepted_queue_ids: list[int] = []
        rejected_items: list[SyncRejectedItem] = []

        for change in payload.changes:
            try:
                with self.db.begin_nested():
                    self._apply_change(user, payload.device_id, change)
                accepted += 1
                if change.queue_id is not None:
                    accepted_queue_ids.append(change.queue_id)
            except AppException as exc:
                if exc.code == 4302:
                    conflict_count += 1
                rejected += 1
                rejected_items.append(
                    SyncRejectedItem(
                        queue_id=change.queue_id,
                        entity_type=change.entity_type,
                        entity_id=change.entity_id,
                        code=exc.code,
                        message=exc.message,
                    )
                )

        self.db.commit()
        latest_change_id = self._latest_change_id(user)
        return SyncPushResult(
            pushed_count=accepted,
            accepted_count=accepted,
            rejected_count=rejected,
            conflict_count=conflict_count,
            latest_change_id=latest_change_id,
            accepted_queue_ids=accepted_queue_ids,
            rejected_items=rejected_items,
        )

    def pull(self, user: User, payload: SyncPullRequest) -> SyncPullResult:
        self._ensure_device(user, payload.device_id)
        all_changes = self.db.scalars(
            select(SyncChange)
            .where(SyncChange.user_id == user.id, SyncChange.id > payload.since_change_id)
            .order_by(SyncChange.id.asc())
            .limit(payload.limit)
        ).all()

        latest_change_id = payload.since_change_id
        items: list[SyncChangeRead] = []
        for change in all_changes:
            latest_change_id = max(latest_change_id, int(change.id))
            if change.changed_by_device_id == payload.device_id:
                continue
            record = self._get_record(user, change.entity_type, change.entity_id)
            items.append(
                SyncChangeRead(
                    change_id=int(change.id),
                    entity_type=change.entity_type,
                    entity_id=change.entity_id,
                    operation=SyncOperation(change.operation),
                    sync_version=int(change.version),
                    remote_version=int(change.version),
                    changed_by_device_id=change.changed_by_device_id,
                    changed_at=change.changed_at,
                    payload=loads_json(record.payload_json) if record is not None else None,
                )
            )

        return SyncPullResult(changes=items, latest_change_id=latest_change_id)

    def bootstrap(self, user: User, *, page: int = 1, page_size: int = 500) -> SyncBootstrapResult:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 1000)
        records = self.db.scalars(
            select(SyncRecord)
            .where(SyncRecord.user_id == user.id, SyncRecord.deleted_at.is_(None))
            .order_by(SyncRecord.updated_at.asc(), SyncRecord.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [
            SyncBootstrapRecord(
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                sync_version=int(record.version),
                payload=loads_json(record.payload_json),
                updated_at=record.updated_at,
            )
            for record in records
        ]
        return SyncBootstrapResult(
            items=items,
            page=page,
            page_size=page_size,
            latest_change_id=self._latest_change_id(user),
        )

    def _apply_change(self, user: User, device_id: str, change: SyncPushChange) -> None:
        payload = sanitize_payload(change.payload or {})
        entity_id = self._resolve_entity_id(change.entity_id, payload)
        record = self._get_record(user, change.entity_type, entity_id)

        operation = "delete" if change.operation == SyncOperation.delete else "upsert"
        if change.base_version and record is not None and int(record.version) > int(change.base_version):
            raise AppException("云端版本已更新，请先拉取后再同步", code=4302, status_code=409)

        next_version = int(record.version) + 1 if record is not None else max(int(payload.get("sync_version") or 1), 1)
        if operation == "delete":
            payload = payload or {"entity_type": change.entity_type, "sync_id": entity_id}
            deleted_at = utc_now()
        else:
            deleted_at = None

        payload["entity_type"] = str(payload.get("entity_type") or change.entity_type)
        payload["sync_id"] = str(payload.get("sync_id") or entity_id)
        payload["sync_version"] = next_version
        payload["sync_deleted"] = operation == "delete"
        payload = sanitize_payload(payload)
        payload_json = dumps_json(payload)

        if record is None:
            record = SyncRecord(
                user_id=int(user.id),
                entity_type=change.entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
                content_hash=content_hash(payload),
                version=next_version,
                deleted_at=deleted_at,
                updated_by_device_id=device_id,
            )
            self.db.add(record)
            self.db.flush()
        else:
            record.payload_json = payload_json
            record.content_hash = content_hash(payload)
            record.version = next_version
            record.deleted_at = deleted_at
            record.updated_by_device_id = device_id

        self.db.add(
            SyncChange(
                user_id=int(user.id),
                entity_type=change.entity_type,
                entity_id=entity_id,
                operation=operation,
                version=next_version,
                changed_by_device_id=device_id,
            )
        )

    def _resolve_entity_id(self, fallback_entity_id: str, payload: dict[str, Any]) -> str:
        sync_id = payload.get("sync_id")
        if sync_id:
            return str(sync_id)
        nested = payload.get("data")
        if isinstance(nested, dict) and nested.get("sync_id"):
            return str(nested["sync_id"])
        return fallback_entity_id

    def _get_record(self, user: User, entity_type: str, entity_id: str) -> SyncRecord | None:
        return self.db.scalar(
            select(SyncRecord).where(
                SyncRecord.user_id == user.id,
                SyncRecord.entity_type == entity_type,
                SyncRecord.entity_id == entity_id,
            )
        )

    def _ensure_device(self, user: User, device_id: str) -> Device:
        device = self.db.scalar(select(Device).where(Device.user_id == user.id, Device.device_id == device_id))
        if device is None:
            raise AppException("设备未登记，请重新登录", code=4300, status_code=401)
        device.last_seen_at = utc_now()
        return device

    def _latest_change_id(self, user: User) -> int:
        return int(self.db.scalar(select(func.max(SyncChange.id)).where(SyncChange.user_id == user.id)) or 0)
