from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class SyncOperation(str, Enum):
    create = "create"
    update = "update"
    upsert = "upsert"
    delete = "delete"


class SyncPushChange(BaseSchema):
    queue_id: int | None = None
    entity_type: str = Field(min_length=1, max_length=80)
    entity_id: str = Field(min_length=1, max_length=120)
    operation: SyncOperation
    payload: dict[str, Any] | None = None
    base_version: int = Field(default=0, ge=0)
    created_at: str | None = None

    @field_validator("entity_type", "entity_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class SyncPushRequest(BaseSchema):
    device_id: str = Field(min_length=1, max_length=100)
    changes: list[SyncPushChange] = Field(default_factory=list, max_length=1000)


class SyncPushResult(BaseSchema):
    pushed_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    conflict_count: int = 0
    latest_change_id: int = 0
    accepted_queue_ids: list[int] = Field(default_factory=list)
    rejected_items: list["SyncRejectedItem"] = Field(default_factory=list)


class SyncRejectedItem(BaseSchema):
    queue_id: int | None = None
    entity_type: str
    entity_id: str
    code: int
    message: str


class SyncPullRequest(BaseSchema):
    device_id: str = Field(min_length=1, max_length=100)
    since_change_id: int = Field(default=0, ge=0)
    limit: int = Field(default=500, ge=1, le=1000)


class SyncChangeRead(BaseSchema):
    change_id: int
    entity_type: str
    entity_id: str
    operation: SyncOperation
    sync_version: int
    remote_version: int
    changed_by_device_id: str
    changed_at: object
    payload: dict[str, Any] | None = None


class SyncPullResult(BaseSchema):
    changes: list[SyncChangeRead]
    latest_change_id: int


class SyncBootstrapRecord(BaseSchema):
    entity_type: str
    entity_id: str
    sync_version: int
    payload: dict[str, Any] | None = None
    updated_at: object


class SyncBootstrapResult(BaseSchema):
    items: list[SyncBootstrapRecord]
    page: int
    page_size: int
    latest_change_id: int


class SyncHealthRead(BaseSchema):
    status: str = "ok"
    app: str
    environment: str
    db: str = "unknown"
