from __future__ import annotations

from pydantic import BaseModel


class AppVersionRead(BaseModel):
    platform: str
    latest_version: str
    minimum_supported_version: str
    update_required: bool
    release_notes: str
    testflight_url: str | None = None
    app_store_url: str | None = None
    checked_at: str
