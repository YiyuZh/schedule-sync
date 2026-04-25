from __future__ import annotations

import logging
from typing import Any, Generic, TypeVar

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


class AppException(Exception):
    def __init__(self, message: str, *, code: int = 4000, status_code: int = 400) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def fail(message: str, *, code: int = 4000) -> dict[str, Any]:
    return {"code": code, "message": message, "data": None}


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=fail(exc.message, code=exc.code))


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error", exc_info=exc)
    try:
        from app.core.config import get_settings

        message = "服务器内部错误" if get_settings().is_production else f"服务器内部错误：{exc}"
    except Exception:
        message = "服务器内部错误"
    return JSONResponse(status_code=500, content=fail(message, code=5000))
