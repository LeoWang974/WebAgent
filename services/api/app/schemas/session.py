from typing import Literal

from app.schemas.base import ApiModel

SkillKey = Literal["data_analysis", "deep_research", "ppt_generation", "u1_image"]
SessionType = Literal["chat", "data_analysis", "deep_research", "ppt_generation", "u1_image"]
SessionStatus = Literal["active", "running", "failed", "completed"]


class Session(ApiModel):
    id: str
    title: str
    type: SessionType
    pinned: bool
    status: SessionStatus
    updated_at: str


class SessionCreate(ApiModel):
    skill_key: SkillKey | None = None
    title: str | None = None


class SessionUpdate(ApiModel):
    pinned: bool | None = None
    title: str | None = None

