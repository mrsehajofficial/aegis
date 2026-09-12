from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import BigInteger, Integer, Boolean, Text, DateTime, ForeignKey, String, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.database.models.group import Group


class GroupSettings(Base):
    __tablename__ = "group_settings"

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True
    )

    warn_limit: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    goodbye_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    anti_flood_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    anti_spam_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    flood_msg_limit: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    flood_window_seconds: Mapped[float] = mapped_column(Float, default=3.0, server_default="3.0", nullable=False)
    flood_mute_minutes: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    spam_action: Mapped[str] = mapped_column(String(32), default="delete", server_default="delete", nullable=False)
    log_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    # Relationship
    group: Mapped["Group"] = relationship("Group", back_populates="settings")

    def __repr__(self) -> str:
        return f"<GroupSettings group_id={self.group_id} warn_limit={self.warn_limit}>"
