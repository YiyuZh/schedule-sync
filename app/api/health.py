from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.response import ApiResponse, success
from app.schemas.app_version import AppVersionRead
from app.schemas.sync import SyncHealthRead
from app.utils.datetime_utils import now_datetime_str

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[SyncHealthRead])
def health(db: DbSession) -> dict[str, object]:
    settings = get_settings()
    db.execute(text("SELECT 1"))
    return success(SyncHealthRead(status="ok", app=settings.app_name, environment=settings.app_env, db="ok").model_dump())


@router.get("/system/info", response_model=ApiResponse[dict[str, object]])
def system_info() -> dict[str, object]:
    settings = get_settings()
    return success(
        {
            "app_name": settings.app_name,
            "environment": settings.app_env,
            "base_url": settings.app_base_url,
            "cloud_role": "account-device-sync-only",
            "ai_policy": "client_side_only",
        }
    )


@router.get("/app-version", response_model=ApiResponse[AppVersionRead])
def app_version() -> dict[str, object]:
    settings = get_settings()
    return success(
        AppVersionRead(
            platform="ios",
            latest_version=settings.mobile_latest_version,
            minimum_supported_version=settings.mobile_min_supported_version,
            update_required=settings.mobile_update_required,
            release_notes=settings.mobile_release_notes,
            testflight_url=settings.mobile_testflight_url or None,
            app_store_url=settings.mobile_app_store_url or None,
            checked_at=now_datetime_str(),
        ).model_dump()
    )
