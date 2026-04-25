from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.response import ApiResponse, success
from app.schemas.sync import SyncHealthRead

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
