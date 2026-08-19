# File purpose: Defines Pydantic API contracts for message.
# Main declarations: Message defines message state or behavior; MessageCreate defines message
# create state or behavior; SendMessageResult defines send message result state or behavior.

from typing import Literal

from app.schemas.base import ApiModel
from app.schemas.session import Session

MessageRole = Literal["user", "assistant", "system", "tool"]


class Message(ApiModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    created_at: str
    artifact_ids: list[str] | None = None


class MessageCreate(ApiModel):
    content: str
    model_id: str | None = None


class SendMessageResult(ApiModel):
    messages: list[Message]
    run_id: str | None = None
    session: Session
