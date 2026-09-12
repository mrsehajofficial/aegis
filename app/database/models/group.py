from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, BigInteger, Text, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.database.models.member import Member
    from app.database.models.settings import GroupSettings
    from app.database.models.warning import Warning
    from app.database.models.filter import Filter
    from app.database.models.protection import Blacklist, Note


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # 'group', 'supergroup', 'channel'

    # Relationships
    settings: Mapped[Optional["GroupSettings"]] = relationship(
        "GroupSettings",
        back_populates="group",
        cascade="all, delete-orphan",
        uselist=False
    )
    members: Mapped[List["Member"]] = relationship(
        "Member",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    warnings: Mapped[List["Warning"]] = relationship(
        "Warning",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    filters: Mapped[List["Filter"]] = relationship(
        "Filter",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    blacklists: Mapped[List["Blacklist"]] = relationship(
        "Blacklist",
        back_populates="group",
        cascade="all, delete-orphan",
        overlaps="group"
    )
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        back_populates="group",
        cascade="all, delete-orphan",
        overlaps="group"
    )
    blacklists: Mapped[List["Blacklist"]] = relationship(
        "Blacklist",
        cascade="all, delete-orphan"
    )
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} telegram_id={self.telegram_id} title={self.title!r}>"
