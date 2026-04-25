from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.datetime_utils import utc_now


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "setting_key", name="uq_user_settings_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    setting_key: Mapped[str] = mapped_column(String(100), nullable=False)
    setting_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(30), default="string", nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
