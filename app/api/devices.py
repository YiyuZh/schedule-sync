from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.response import ApiResponse, success
from app.schemas.device import DeviceListRead, DeviceRead, DeviceRegisterRequest, DeviceUpdateRequest
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=ApiResponse[DeviceListRead])
def list_devices(db: DbSession, user: CurrentUser) -> dict[str, object]:
    devices = DeviceService(db).list_devices(user)
    return success({"items": [DeviceRead.model_validate(item).model_dump() for item in devices]})


@router.post("/register", response_model=ApiResponse[DeviceRead])
def register_device(payload: DeviceRegisterRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    device = DeviceService(db).register_device(user, payload)
    return success(DeviceRead.model_validate(device).model_dump())


@router.put("/{device_id}", response_model=ApiResponse[DeviceRead])
def update_device(device_id: str, payload: DeviceUpdateRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    device = DeviceService(db).update_device(user, device_id, payload)
    return success(DeviceRead.model_validate(device).model_dump())


@router.delete("/{device_id}", response_model=ApiResponse[dict[str, bool]])
def delete_device(device_id: str, db: DbSession, user: CurrentUser) -> dict[str, object]:
    DeviceService(db).delete_device(user, device_id)
    return success({"ok": True})
