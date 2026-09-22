from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, Text, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now


class BusinessConnection(Base):
    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    greeting_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    greeting_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    away_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    away_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    # Relationships
    rules: Mapped[List["BusinessRule"]] = relationship(
        "BusinessRule",
        back_populates="connection",
        cascade="all, delete-orphan",
        primaryjoin="foreign(BusinessRule.connection_id) == BusinessConnection.connection_id"
    )

    def __repr__(self) -> str:
        return f"<BusinessConnection id={self.id} connection_id={self.connection_id!r} user_id={self.user_id}>"


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    connection_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        ForeignKey("business_connections.connection_id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    trigger: Mapped[str] = mapped_column(String(255), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(String(32), default="contains", server_default="contains", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    # Relationship
    connection: Mapped[Optional["BusinessConnection"]] = relationship(
        "BusinessConnection",
        back_populates="rules",
        primaryjoin="foreign(BusinessRule.connection_id) == BusinessConnection.connection_id"
    )

    def __repr__(self) -> str:
        return f"<BusinessRule id={self.id} user_id={self.user_id} trigger={self.trigger!r}>"
