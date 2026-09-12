from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import BigInteger, Text, String, DateTime, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, utc_now


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} group_id={self.group_id} action={self.action} target_id={self.target_id}>"
