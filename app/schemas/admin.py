from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.auth import normalize_email
from app.schemas.common import BaseSchema


class AdminLoginRequest(BaseSchema):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class AdminTokenRead(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminMeRead(BaseSchema):
    email: str


class DailyActivePoint(BaseSchema):
    date: str
    active_users: int
    sync_changes: int


class AdminOverviewRead(BaseSchema):
    total_users: int
    active_users_30d: int
    total_devices: int
    total_sync_records: int
    today_active_users: int
    daily_active: list[DailyActivePoint]


class AdminUserListItem(BaseSchema):
    id: int
    email: str
    display_name: str | None = None
    is_active: bool
    device_count: int
    sync_record_count: int
    last_login_at: str | None = None
    last_active_at: str | None = None
    created_at: str | None = None


class AdminUserListRead(BaseSchema):
    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int


class AdminDeviceRead(BaseSchema):
    device_id: str
    device_name: str
    device_type: str
    last_seen_at: str | None = None
    created_at: str | None = None


class AdminEntityCountRead(BaseSchema):
    entity_type: str
    count: int


class AdminUserDetailRead(BaseSchema):
    user: AdminUserListItem
    devices: list[AdminDeviceRead]
    entity_counts: list[AdminEntityCountRead]


class AdminDeleteRequest(BaseSchema):
    confirm_email: str = Field(min_length=3, max_length=255)

    @field_validator("confirm_email")
    @classmethod
    def validate_confirm_email(cls, value: str) -> str:
        return normalize_email(value)
