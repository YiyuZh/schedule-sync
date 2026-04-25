from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import AppException
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceRegisterRequest, DeviceUpdateRequest
from app.utils.datetime_utils import utc_now


class DeviceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_devices(self, user: User) -> list[Device]:
        return self.db.scalars(
            select(Device).where(Device.user_id == user.id).order_by(Device.last_seen_at.desc(), Device.id.desc())
        ).all()

    def update_device(self, user: User, device_id: str, payload: DeviceUpdateRequest) -> Device:
        device = self.db.scalar(select(Device).where(Device.user_id == user.id, Device.device_id == device_id))
        if device is None:
            raise AppException("设备不存在", code=4200, status_code=404)
        if payload.device_name is not None:
            device.device_name = payload.device_name
        if payload.device_type is not None:
            device.device_type = payload.device_type
        self.db.commit()
        self.db.refresh(device)
        return device

    def register_device(self, user: User, payload: DeviceRegisterRequest) -> Device:
        device = self.db.scalar(select(Device).where(Device.user_id == user.id, Device.device_id == payload.device_id))
        if device is None:
            device = Device(
                user_id=int(user.id),
                device_id=payload.device_id,
                device_name=payload.device_name,
                device_type=payload.device_type,
                last_seen_at=utc_now(),
            )
            self.db.add(device)
        else:
            device.device_name = payload.device_name
            device.device_type = payload.device_type
            device.last_seen_at = utc_now()
        self.db.commit()
        self.db.refresh(device)
        return device

    def delete_device(self, user: User, device_id: str) -> None:
        device = self.db.scalar(select(Device).where(Device.user_id == user.id, Device.device_id == device_id))
        if device is None:
            raise AppException("设备不存在", code=4201, status_code=404)
        self.db.delete(device)
        self.db.commit()
