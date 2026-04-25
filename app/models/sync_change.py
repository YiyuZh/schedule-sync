from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.datetime_utils import utc_now


class SyncChange(Base):
    __tablename__ = "sync_changes"
    __table_args__ = (
        Index("ix_sync_changes_user_id_id", "user_id", "id"),
        Index("ix_sync_changes_user_entity", "user_id", "entity_type", "entity_id"),
        Index("ix_sync_changes_changed_at", "user_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    changed_by_device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    changed_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
