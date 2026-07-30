from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel

SkillKey = Literal[
    "data_analysis",
    "deep_research",
    "html_generation",
    "ppt_generation",
    "u1_image",
]
SessionType = Literal[
    "chat",
    "data_analysis",
    "deep_research",
    "html_generation",
    "ppt_generation",
    "u1_image",
]
SessionStatus = Literal["active", "running", "failed", "completed"]
SessionVisibility = Literal["private", "shared", "public"]


class SessionShare(ApiModel):
    id: str
    email: str
    nickname: str
    role: str


class Session(ApiModel):
    id: str
    folder_id: str | None = None
    title: str
    type: SessionType
    pinned: bool
    status: SessionStatus
    updated_at: str
    owner_id: str = "demo_user"
    visibility: SessionVisibility = "private"
    shared_with: list[SessionShare] = Field(default_factory=list)


class SessionCreate(ApiModel):
    folder_id: str | None = None
    skill_key: SkillKey | None = None
    title: str | None = None
    visibility: SessionVisibility | None = None


class SessionUpdate(ApiModel):
    folder_id: str | None = None
    pinned: bool | None = None
    title: str | None = None
    visibility: SessionVisibility | None = None
    share_with_email: str | None = None
    unshare_user_id: str | None = None


class ConversationFolder(ApiModel):
    id: str
    name: str
    created_at: str
    updated_at: str


class ConversationFolderCreate(ApiModel):
    name: str


class ConversationFolderUpdate(ApiModel):
    name: str
