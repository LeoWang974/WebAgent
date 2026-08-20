# File purpose: Defines SQLAlchemy persistence models for artifact.
# Main declarations: Artifact defines artifact state or behavior; RunArtifact records durable
# per-Run ownership; FileAsset defines uploaded file state or behavior.

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class Artifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_conversation_run_type", "conversation_id", "run_id", "type"),
        Index(
            "ix_artifacts_conversation_status_created",
            "conversation_id",
            "status",
            "created_at",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    conversation = relationship("Conversation")
    run_artifacts = relationship(
        "RunArtifact",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )


class RunArtifact(IdMixin, TimestampMixin, Base):
    """Records that an Agent Run owns an artifact, independently of file reuse."""

    __tablename__ = "run_artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "artifact_id", name="uq_run_artifacts_run_artifact"),
        Index("ix_run_artifacts_run_created", "run_id", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        index=True,
    )

    run = relationship("AgentRun", back_populates="run_artifacts")
    artifact = relationship("Artifact", back_populates="run_artifacts")


class FileAsset(IdMixin, TimestampMixin, Base):
    __tablename__ = "files"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024))
    file_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
