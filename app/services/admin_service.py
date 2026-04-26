from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.response import AppException
from app.core.security import create_admin_access_token, hash_password, verify_password
from app.models.device import Device
from app.models.refresh_token import RefreshToken
from app.models.sync_change import SyncChange
from app.models.sync_record import SyncRecord
from app.models.user import User
from app.models.user_setting import UserSetting
from app.schemas.admin import (
    AdminDeleteRequest,
    AdminDeviceRead,
    AdminEntityCountRead,
    AdminOverviewRead,
    AdminResetPasswordRead,
    AdminResetPasswordRequest,
    AdminTokenRead,
    AdminUserDetailRead,
    AdminUserListItem,
    AdminUserListRead,
    DailyActivePoint,
)
from app.utils.datetime_utils import to_datetime_str, utc_now


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate(self, *, email: str, password: str) -> AdminTokenRead:
        settings = get_settings()
        expected_email = settings.admin_email.strip().lower()
        if email.strip().lower() != expected_email:
            raise AppException("管理员账号或密码错误", code=4401, status_code=401)

        if settings.admin_password_hash.strip():
            password_ok = verify_password(password, settings.admin_password_hash.strip())
        elif not settings.is_production and settings.admin_password.strip():
            password_ok = secrets.compare_digest(password, settings.admin_password)
        else:
            raise AppException("管理员密码未配置", code=4400, status_code=500)

        if not password_ok:
            raise AppException("管理员账号或密码错误", code=4401, status_code=401)

        access_token, expires_in = create_admin_access_token(email=expected_email)
        return AdminTokenRead(access_token=access_token, expires_in=expires_in)

    def overview(self) -> AdminOverviewRead:
        total_users = int(self.db.scalar(select(func.count(User.id))) or 0)
        total_devices = int(self.db.scalar(select(func.count(Device.id))) or 0)
        total_sync_records = int(self.db.scalar(select(func.count(SyncRecord.id))) or 0)

        today = utc_now().date()
        start_date = today - timedelta(days=29)
        start_dt = utc_now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29)

        daily_users: dict[str, set[int]] = defaultdict(set)
        daily_changes: dict[str, int] = defaultdict(int)
        active_user_ids: set[int] = set()

        for user in self.db.scalars(select(User).where(User.last_login_at >= start_dt)).all():
            day = user.last_login_at.date().isoformat() if user.last_login_at else ""
            if day:
                daily_users[day].add(int(user.id))
                active_user_ids.add(int(user.id))

        for device in self.db.scalars(select(Device).where(Device.last_seen_at >= start_dt)).all():
            day = device.last_seen_at.date().isoformat() if device.last_seen_at else ""
            if day:
                daily_users[day].add(int(device.user_id))
                active_user_ids.add(int(device.user_id))

        for change in self.db.scalars(select(SyncChange).where(SyncChange.changed_at >= start_dt)).all():
            day = change.changed_at.date().isoformat()
            daily_users[day].add(int(change.user_id))
            daily_changes[day] += 1
            active_user_ids.add(int(change.user_id))

        points: list[DailyActivePoint] = []
        for offset in range(30):
            day = (start_date + timedelta(days=offset)).isoformat()
            points.append(
                DailyActivePoint(
                    date=day,
                    active_users=len(daily_users.get(day, set())),
                    sync_changes=int(daily_changes.get(day, 0)),
                )
            )

        return AdminOverviewRead(
            total_users=total_users,
            active_users_30d=len(active_user_ids),
            total_devices=total_devices,
            total_sync_records=total_sync_records,
            today_active_users=len(daily_users.get(today.isoformat(), set())),
            daily_active=points,
        )

    def list_users(self, *, search: str | None = None, page: int = 1, page_size: int = 20) -> AdminUserListRead:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if search and search.strip():
            keyword = f"%{search.strip().lower()}%"
            condition = or_(
                func.lower(User.email).like(keyword),
                func.lower(func.coalesce(User.display_name, "")).like(keyword),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = int(self.db.scalar(count_stmt) or 0)
        users = self.db.scalars(
            stmt.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return AdminUserListRead(
            items=[self._build_user_item(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_user_detail(self, user_id: int) -> AdminUserDetailRead:
        user = self.db.get(User, user_id)
        if user is None:
            raise AppException("用户不存在", code=4404, status_code=404)

        devices = self.db.scalars(
            select(Device).where(Device.user_id == user_id).order_by(Device.last_seen_at.desc(), Device.id.desc())
        ).all()
        entity_counts = self.db.execute(
            select(SyncRecord.entity_type, func.count(SyncRecord.id))
            .where(SyncRecord.user_id == user_id)
            .group_by(SyncRecord.entity_type)
            .order_by(func.count(SyncRecord.id).desc())
        ).all()

        return AdminUserDetailRead(
            user=self._build_user_item(user),
            devices=[
                AdminDeviceRead(
                    device_id=device.device_id,
                    device_name=device.device_name,
                    device_type=device.device_type,
                    last_seen_at=to_datetime_str(device.last_seen_at),
                    created_at=to_datetime_str(device.created_at),
                )
                for device in devices
            ],
            entity_counts=[
                AdminEntityCountRead(entity_type=str(entity_type), count=int(count))
                for entity_type, count in entity_counts
            ],
        )

    def delete_user(self, user_id: int, payload: AdminDeleteRequest) -> None:
        user = self.db.get(User, user_id)
        if user is None:
            raise AppException("用户不存在", code=4404, status_code=404)

        if payload.confirm_email != user.email:
            raise AppException("确认邮箱不匹配，已取消删除", code=4405, status_code=400)
        if user.email.strip().lower() == get_settings().admin_email.strip().lower():
            raise AppException("不能删除管理员账号", code=4406, status_code=403)

        for model in (SyncChange, SyncRecord, UserSetting, RefreshToken, Device):
            self.db.execute(delete(model).where(model.user_id == user_id))
        self.db.delete(user)
        self.db.commit()

    def reset_user_password(self, user_id: int, payload: AdminResetPasswordRequest) -> AdminResetPasswordRead:
        user = self.db.get(User, user_id)
        if user is None:
            raise AppException("用户不存在", code=4404, status_code=404)

        if payload.confirm_email != user.email:
            raise AppException("确认邮箱不匹配，已取消修改密码", code=4407, status_code=400)

        user.password_hash = hash_password(payload.new_password)
        revoked_count = 0
        if payload.revoke_existing_sessions:
            for token in self.db.scalars(
                select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            ).all():
                token.revoked_at = utc_now()
                revoked_count += 1

        self.db.commit()
        return AdminResetPasswordRead(ok=True, revoked_refresh_tokens=revoked_count)

    def _build_user_item(self, user: User) -> AdminUserListItem:
        device_count = int(self.db.scalar(select(func.count(Device.id)).where(Device.user_id == user.id)) or 0)
        sync_record_count = int(
            self.db.scalar(select(func.count(SyncRecord.id)).where(SyncRecord.user_id == user.id)) or 0
        )
        last_device_seen = self.db.scalar(select(func.max(Device.last_seen_at)).where(Device.user_id == user.id))
        last_change_at = self.db.scalar(select(func.max(SyncChange.changed_at)).where(SyncChange.user_id == user.id))
        last_active_at = self._max_datetime(user.last_login_at, last_device_seen, last_change_at)

        return AdminUserListItem(
            id=int(user.id),
            email=str(user.email),
            display_name=user.display_name,
            is_active=bool(user.is_active),
            device_count=device_count,
            sync_record_count=sync_record_count,
            last_login_at=to_datetime_str(user.last_login_at),
            last_active_at=to_datetime_str(last_active_at),
            created_at=to_datetime_str(user.created_at),
        )

    def _max_datetime(self, *values: object | None) -> object | None:
        dates = [value for value in values if value is not None]
        if not dates:
            return None
        return max(dates)
