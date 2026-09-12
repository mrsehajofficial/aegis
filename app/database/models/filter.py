from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import BigInteger, Text, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.database.models.group import Group


class Filter(Base):
    __tablename__ = "filters"
    __table_args__ = (
        UniqueConstraint("group_id", "trigger", name="uq_group_filter_trigger"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    trigger: Mapped[str] = mapped_column(String(255), nullable=False)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(String(64), default="reply", server_default="reply", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    # Relationship
    group: Mapped["Group"] = relationship("Group", back_populates="filters")

    def __repr__(self) -> str:
        return f"<Filter id={self.id} group_id={self.group_id} trigger={self.trigger!r}>"
