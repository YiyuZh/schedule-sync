from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import AppException
from app.core.security import decode_access_token
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AppException("请先登录", code=4012, status_code=401)
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise AppException("Token 缺少用户信息", code=4013, status_code=401)
    user = db.get(User, int(user_id))
    if user is None or not bool(user.is_active):
        raise AppException("账号不存在或已停用", code=4014, status_code=401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
