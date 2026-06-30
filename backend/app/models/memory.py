import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class MemoryType(str, enum.Enum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    GOAL = "GOAL"


class Memory(BaseModel):
    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "ix_memories_user_type",
            "user_id",
            "memory_type",
        ),
        UniqueConstraint(
            "user_id",
            "key",
            name="uq_memories_user_key",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        back_populates="memories",
    )