from datetime import datetime
from typing import Optional
from sqlalchemy import Text, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, utc_now


class Blacklist(Base):
    __tablename__ = "blacklists"
    __table_args__ = (
        UniqueConstraint("group_id", "word", name="uq_group_blacklist_word"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    word: Mapped[str] = mapped_column(String(500), nullable=False)
    action: Mapped[str] = mapped_column(
        String(32), default="delete", server_default="delete", nullable=False
    )  # delete | warn | mute | ban
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    group: Mapped["Group"] = relationship("Group", back_populates="blacklists", overlaps="blacklists")

    def __repr__(self) -> str:
        return f"<Blacklist id={self.id} group_id={self.group_id} word={self.word!r}>"


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("group_id", "keyword", name="uq_group_note_keyword"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    group: Mapped["Group"] = relationship("Group", back_populates="notes", overlaps="notes")

    def __repr__(self) -> str:
        return f"<Note id={self.id} group_id={self.group_id} keyword={self.keyword!r}>"