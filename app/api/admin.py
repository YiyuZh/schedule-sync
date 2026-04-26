from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.rate_limit import check_auth_rate_limit
from app.core.response import ApiResponse, AppException, success
from app.core.security import decode_admin_access_token
from app.schemas.admin import (
    AdminDeleteRequest,
    AdminLoginRequest,
    AdminMeRead,
    AdminOverviewRead,
    AdminResetPasswordRead,
    AdminResetPasswordRequest,
    AdminTokenRead,
    AdminUserDetailRead,
    AdminUserListRead,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])
admin_bearer_scheme = HTTPBearer(auto_error=False)


def get_admin_email(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_bearer_scheme)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise AppException("请先登录管理员后台", code=4412, status_code=401)
    payload = decode_admin_access_token(credentials.credentials)
    email = str(payload.get("email") or "").strip().lower()
    if email != get_settings().admin_email.strip().lower():
        raise AppException("无管理员权限", code=4413, status_code=403)
    return email


AdminEmail = Annotated[str, Depends(get_admin_email)]


@router.post("/login", response_model=ApiResponse[AdminTokenRead])
def login(payload: AdminLoginRequest, db: DbSession, request: Request) -> dict[str, object]:
    check_auth_rate_limit(request, "admin-login", payload.email)
    token = AdminService(db).authenticate(email=payload.email, password=payload.password)
    return success(token.model_dump())


@router.get("/me", response_model=ApiResponse[AdminMeRead])
def me(email: AdminEmail) -> dict[str, object]:
    return success(AdminMeRead(email=email).model_dump())


@router.get("/overview", response_model=ApiResponse[AdminOverviewRead])
def overview(_: AdminEmail, db: DbSession) -> dict[str, object]:
    data = AdminService(db).overview()
    return success(data.model_dump())


@router.get("/users", response_model=ApiResponse[AdminUserListRead])
def users(
    _: AdminEmail,
    db: DbSession,
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    data = AdminService(db).list_users(search=search, page=page, page_size=page_size)
    return success(data.model_dump())


@router.get("/users/{user_id}", response_model=ApiResponse[AdminUserDetailRead])
def user_detail(user_id: int, _: AdminEmail, db: DbSession) -> dict[str, object]:
    data = AdminService(db).get_user_detail(user_id)
    return success(data.model_dump())


@router.delete("/users/{user_id}", response_model=ApiResponse[dict[str, bool]])
def delete_user(user_id: int, payload: AdminDeleteRequest, _: AdminEmail, db: DbSession) -> dict[str, object]:
    AdminService(db).delete_user(user_id, payload)
    return success({"ok": True})


@router.post("/users/{user_id}/password", response_model=ApiResponse[AdminResetPasswordRead])
def reset_user_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    _: AdminEmail,
    db: DbSession,
) -> dict[str, object]:
    data = AdminService(db).reset_user_password(user_id, payload)
    return success(data.model_dump())
