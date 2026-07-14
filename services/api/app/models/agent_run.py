from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_conversation_status_updated", "conversation_id", "status", "updated_at"),
    )

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    title: Mapped[str] = mapped_column(String(255))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_key: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AgentRunEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_run_events"

    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
