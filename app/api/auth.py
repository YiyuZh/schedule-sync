from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import check_auth_rate_limit
from app.core.response import ApiResponse, success
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairRead,
    UserRead,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[UserRead])
def register(payload: RegisterRequest, db: DbSession, request: Request) -> dict[str, object]:
    check_auth_rate_limit(request, "register", payload.email)
    user = AuthService(db).register(payload)
    return success(UserRead.model_validate(user).model_dump())


@router.post("/login", response_model=ApiResponse[TokenPairRead])
def login(payload: LoginRequest, db: DbSession, request: Request) -> dict[str, object]:
    check_auth_rate_limit(request, "login", payload.email)
    token = AuthService(db).login(payload)
    return success(token.model_dump())


@router.post("/refresh", response_model=ApiResponse[TokenPairRead])
def refresh(payload: RefreshRequest, db: DbSession, request: Request) -> dict[str, object]:
    check_auth_rate_limit(request, "refresh", payload.device_id)
    token = AuthService(db).refresh(payload)
    return success(token.model_dump())


@router.post("/logout", response_model=ApiResponse[dict[str, bool]])
def logout(payload: LogoutRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    AuthService(db).logout(user, refresh_token=payload.refresh_token, device_id=payload.device_id)
    return success({"ok": True})


@router.get("/me", response_model=ApiResponse[UserRead])
def me(user: CurrentUser) -> dict[str, object]:
    return success(UserRead.model_validate(user).model_dump())
