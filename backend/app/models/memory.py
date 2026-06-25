import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class MemoryType(str, enum.Enum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    GOAL = "GOAL"


class Memory(BaseModel):
    __tablename__ = "memories"

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