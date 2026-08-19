# File purpose: Defines SQLAlchemy persistence models for conversation.
# Main declarations: Conversation defines conversation state or behavior; Message defines message
# state or behavior; ConversationShare defines conversation share state or behavior;
# ConversationFolder defines conversation folder state or behavior.

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation_folders.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50), default="chat")
    pinned: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    visibility: Mapped[str] = mapped_column(String(20), default="private")

    user = relationship("User", back_populates="conversations")
    folder = relationship("ConversationFolder", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    shares = relationship(
        "ConversationShare", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    artifact_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class ConversationShare(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversation_shares"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_share_user"),
    )

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(50), default="viewer")

    conversation = relationship("Conversation", back_populates="shares")
    user = relationship("User", back_populates="conversation_shares")


class ConversationFolder(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversation_folders"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_conversation_folder_user_name"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))

    conversations = relationship("Conversation", back_populates="folder")
