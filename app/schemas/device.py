from __future__ import annotations

from pydantic import Field

from app.schemas.common import BaseSchema


class DeviceRead(BaseSchema):
    id: int
    device_id: str
    device_name: str
    device_type: str
    last_seen_at: object | None = None
    created_at: object
    updated_at: object


class DeviceListRead(BaseSchema):
    items: list[DeviceRead]


class DeviceUpdateRequest(BaseSchema):
    device_name: str | None = Field(default=None, min_length=1, max_length=100)
    device_type: str | None = Field(default=None, min_length=1, max_length=30)


class DeviceRegisterRequest(BaseSchema):
    device_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=100)
    device_type: str = Field(default="desktop", min_length=1, max_length=30)
