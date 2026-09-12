from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import BigInteger, Text, String, DateTime, ForeignKey, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now

if TYPE_CHECKING:
    from app.database.models.group import Group


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("group_id", "telegram_id", name="uq_group_telegram_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="member", server_default="member", nullable=False)  # 'owner', 'admin', 'member'
    
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    # Relationship
    group: Mapped["Group"] = relationship("Group", back_populates="members")

    def __repr__(self) -> str:
        return f"<Member id={self.id} group_id={self.group_id} telegram_id={self.telegram_id} role={self.role}>"
