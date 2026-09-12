from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import BigInteger, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.database.models.group import Group


class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    issued_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    # Relationship
    group: Mapped["Group"] = relationship("Group", back_populates="warnings")

    def __repr__(self) -> str:
        return f"<Warning id={self.id} group_id={self.group_id} user_id={self.user_id}>"
