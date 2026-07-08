from typing import Literal

from app.schemas.base import ApiModel
from app.schemas.session import Session, SkillKey

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
    skill_key: SkillKey | None = None


class SendMessageResult(ApiModel):
    messages: list[Message]
    session: Session

