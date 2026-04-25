from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("请输入有效邮箱")
    return normalized


class UserRead(BaseSchema):
    id: int
    email: str
    display_name: str | None = None
    is_active: bool
    last_login_at: object | None = None


class RegisterRequest(BaseSchema):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseSchema):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=100)
    device_type: str = Field(default="desktop", min_length=1, max_length=30)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class TokenPairRead(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseSchema):
    refresh_token: str = Field(min_length=20, max_length=500)
    device_id: str = Field(min_length=1, max_length=100)


class LogoutRequest(BaseSchema):
    refresh_token: str | None = Field(default=None, max_length=500)
    device_id: str | None = Field(default=None, max_length=100)
