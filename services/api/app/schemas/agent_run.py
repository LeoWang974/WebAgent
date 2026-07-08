from typing import Literal

from app.schemas.base import ApiModel
from app.schemas.session import SkillKey

AgentRunStatus = Literal[
    "queued", "running", "tool_calling", "rendering", "completed", "failed", "cancelled"
]
AgentRunStepStatus = Literal["pending", "running", "completed", "failed"]


class AgentRunStep(ApiModel):
    id: str
    label: str
    status: AgentRunStepStatus
    timestamp: str


class AgentRun(ApiModel):
    id: str
    session_id: str
    status: AgentRunStatus
    title: str
    progress: int
    steps: list[AgentRunStep]
    started_at: str
    completed_at: str | None = None
    error: str | None = None


class AgentRunCreate(ApiModel):
    content: str
    model_id: str | None = None
    session_id: str
    skill_key: SkillKey | None = None


class AgentRunEvent(ApiModel):
    run_id: str
    status: AgentRunStatus
    progress: int
    step: AgentRunStep
    completed_at: str | None = None
    error: str | None = None

