from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    pass


DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:1420,"
    "http://localhost:1420,"
    "http://127.0.0.1:5173,"
    "http://localhost:5173,"
    "http://127.0.0.1:5174,"
    "http://localhost:5174,"
    "http://localhost,"
    "tauri://localhost,"
    "capacitor://localhost,"
    "ionic://localhost,"
    "https://sync.example.com"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="schedule-sync-server", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_base_url: str = Field(default="http://127.0.0.1:18130", alias="APP_BASE_URL")

    database_url: str = Field(default="sqlite:///./data/schedule_sync.db", alias="DATABASE_URL")
    run_migrations_on_start: bool = Field(default=True, alias="RUN_MIGRATIONS_ON_START")

    jwt_secret: str = Field(default="dev-only-change-me-schedule-sync", alias="JWT_SECRET")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    auth_rate_limit_max_attempts: int = Field(default=20, alias="AUTH_RATE_LIMIT_MAX_ATTEMPTS")
    auth_rate_limit_window_seconds: int = Field(default=300, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS")

    schedule_sync_domain: str = Field(default="sync.example.com", alias="SCHEDULE_SYNC_DOMAIN")
    uvicorn_workers: int = Field(default=1, alias="UVICORN_WORKERS")
    allowed_origins: str = Field(default=DEFAULT_ALLOWED_ORIGINS, alias="ALLOWED_ORIGINS")

    @field_validator("app_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def validate_for_runtime(self) -> None:
        if not self.is_production:
            return

        errors: list[str] = []
        if self.jwt_secret == "dev-only-change-me-schedule-sync" or self.jwt_secret.startswith("replace-with"):
            errors.append("JWT_SECRET 仍是默认值或占位值")
        if self.database_url.startswith("sqlite"):
            errors.append("生产环境 DATABASE_URL 不能使用 SQLite")
        if "replace-with" in self.database_url:
            errors.append("DATABASE_URL 仍包含 replace-with 占位值")
        if self.database_url.startswith("postgresql") and "schedule_sync:" in self.database_url:
            errors.append("DATABASE_URL 仍在使用旧数据库用户 schedule_sync")
        if "autsky6666@gmail.com" in self.database_url or "autsky6666%40gmail.com" in self.database_url:
            errors.append("DATABASE_URL 仍在使用旧邮箱数据库用户，请改为 autsky")
        if self.database_url.startswith("postgresql") and "://autsky:" not in self.database_url:
            errors.append("DATABASE_URL 必须使用数据库用户 autsky")
        if "sync.example.com" in self.app_base_url:
            errors.append("APP_BASE_URL 仍是 sync.example.com 示例域名")
        if self.schedule_sync_domain == "sync.example.com":
            errors.append("SCHEDULE_SYNC_DOMAIN 仍是 sync.example.com 示例域名")
        if "sync.example.com" in self.allowed_origins:
            errors.append("ALLOWED_ORIGINS 仍包含 sync.example.com 示例域名")
        if self.access_token_expire_minutes <= 0:
            errors.append("ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")
        if self.refresh_token_expire_days <= 0:
            errors.append("REFRESH_TOKEN_EXPIRE_DAYS 必须大于 0")

        if errors:
            raise SettingsError("生产配置不安全：" + "；".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
