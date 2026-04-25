from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import AppException
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    refresh_token_expires_at,
    utc_now,
    verify_password,
)
from app.models.device import Device
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPairRead


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: RegisterRequest) -> User:
        exists = self.db.scalar(select(User).where(User.email == payload.email))
        if exists is not None:
            raise AppException("该邮箱已注册", code=4100, status_code=409)
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name.strip() if payload.display_name else None,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login(self, payload: LoginRequest) -> TokenPairRead:
        user = self.db.scalar(select(User).where(User.email == payload.email))
        if user is None or not verify_password(payload.password, str(user.password_hash)):
            raise AppException("邮箱或密码错误", code=4101, status_code=401)
        if not bool(user.is_active):
            raise AppException("账号已停用", code=4102, status_code=403)

        self._register_or_update_device(user, payload.device_id, payload.device_name, payload.device_type)
        user.last_login_at = utc_now()

        access_token, expires_in = create_access_token(user_id=int(user.id), email=str(user.email))
        refresh_token = new_refresh_token()
        self.db.add(
            RefreshToken(
                user_id=int(user.id),
                device_id=payload.device_id,
                token_hash=hash_token(refresh_token),
                expires_at=refresh_token_expires_at(),
            )
        )
        self.db.commit()
        return TokenPairRead(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    def refresh(self, payload: RefreshRequest) -> TokenPairRead:
        token_hash = hash_token(payload.refresh_token)
        token = self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if token is None or token.revoked_at is not None or token.device_id != payload.device_id:
            raise AppException("Refresh Token 无效", code=4103, status_code=401)
        if token.expires_at < utc_now():
            raise AppException("Refresh Token 已过期", code=4104, status_code=401)

        user = self.db.get(User, token.user_id)
        if user is None or not bool(user.is_active):
            raise AppException("账号不可用", code=4105, status_code=401)

        token.revoked_at = utc_now()
        access_token, expires_in = create_access_token(user_id=int(user.id), email=str(user.email))
        refresh_token = new_refresh_token()
        self.db.add(
            RefreshToken(
                user_id=int(user.id),
                device_id=payload.device_id,
                token_hash=hash_token(refresh_token),
                expires_at=refresh_token_expires_at(),
            )
        )
        self.db.commit()
        return TokenPairRead(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    def logout(self, user: User, *, refresh_token: str | None = None, device_id: str | None = None) -> None:
        stmt = select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        if refresh_token:
            stmt = stmt.where(RefreshToken.token_hash == hash_token(refresh_token))
        if device_id:
            stmt = stmt.where(RefreshToken.device_id == device_id)
        for token in self.db.scalars(stmt).all():
            token.revoked_at = utc_now()
        self.db.commit()

    def _register_or_update_device(self, user: User, device_id: str, device_name: str, device_type: str) -> Device:
        device = self.db.scalar(
            select(Device).where(Device.user_id == user.id, Device.device_id == device_id)
        )
        if device is None:
            device = Device(
                user_id=int(user.id),
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                last_seen_at=utc_now(),
            )
            self.db.add(device)
        else:
            device.device_name = device_name
            device.device_type = device_type
            device.last_seen_at = utc_now()
        return device
