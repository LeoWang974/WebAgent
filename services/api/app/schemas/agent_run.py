# File purpose: Defines Pydantic API contracts for agent run.
# Main declarations: AgentRunStep defines agent run step state or behavior; AgentRun defines agent
# run state or behavior; AgentRunCreate defines agent run create state or behavior; AgentRunEvent
# defines agent run event state or behavior.

from typing import Any, Literal

from app.schemas.base import ApiModel

AgentRunStatus = Literal[
    "queued",
    "running",
    "tool_calling",
    "rendering",
    "completed",
    "failed",
    "cancelled",
    "disconnected",
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
    output: str | None = None
    adapter_key: str | None = None
    model_config_id: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    model_base_url: str | None = None
    queue_name: str | None = None
    queue_position: int | None = None
    queue_reason: str | None = None


class AgentRunCreate(ApiModel):
    content: str
    model_id: str | None = None
    session_id: str


class AgentRunEvent(ApiModel):
    run_id: str
    event_type: str
    status: AgentRunStatus
    progress: int
    step: AgentRunStep
    payload: dict[str, Any] | None = None
    completed_at: str | None = None
    error: str | None = None
    output: str | None = None
