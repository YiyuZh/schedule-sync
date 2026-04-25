from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import ApiResponse, success
from app.schemas.sync import SyncBootstrapResult, SyncPullRequest, SyncPullResult, SyncPushRequest, SyncPushResult
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/push", response_model=ApiResponse[SyncPushResult])
def push(payload: SyncPushRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    result = SyncService(db).push(user, payload)
    return success(result.model_dump())


@router.post("/pull", response_model=ApiResponse[SyncPullResult])
def pull(payload: SyncPullRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    result = SyncService(db).pull(user, payload)
    return success(result.model_dump())


@router.get("/bootstrap", response_model=ApiResponse[SyncBootstrapResult])
def bootstrap(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=500, ge=1, le=1000),
) -> dict[str, object]:
    result = SyncService(db).bootstrap(user, page=page, page_size=page_size)
    return success(result.model_dump())
