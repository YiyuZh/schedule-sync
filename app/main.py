from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import admin, auth, devices, health, sync
from app.core.config import get_settings
from app.core.database import initialize_database
from app.core.response import AppException, app_exception_handler, fail, unhandled_exception_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

ADMIN_STATIC_DIR = Path(__file__).resolve().parent / "admin_static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content=fail(f"请求参数不正确：{exc.errors()}", code=4220))

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(devices.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    @app.get("/admin", include_in_schema=False)
    def admin_index() -> FileResponse:
        return FileResponse(ADMIN_STATIC_DIR / "index.html")

    @app.get("/admin/{asset_path:path}", include_in_schema=False)
    def admin_asset(asset_path: str) -> FileResponse:
        base_dir = ADMIN_STATIC_DIR.resolve()
        target = (ADMIN_STATIC_DIR / asset_path).resolve()
        if target.is_file() and (target == base_dir or base_dir in target.parents):
            return FileResponse(target)
        return FileResponse(ADMIN_STATIC_DIR / "index.html")

    return app


app = create_app()
