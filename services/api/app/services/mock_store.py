from datetime import UTC, datetime
from uuid import uuid4

from app.schemas import (
    AgentRun,
    Artifact,
    DataContextSettings,
    Message,
    ModelConfig,
    Session,
    Skill,
    User,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


user = User(
    id="user_demo",
    nickname="WebAgent User",
    email="demo@webagent.local",
    avatar_url=None,
)

sessions: list[Session] = [
    Session(
        id="session_demo",
        title="Deep research demo",
        type="deep_research",
        pinned=True,
        status="active",
        updated_at=now_iso(),
    )
]

messages: list[Message] = [
    Message(
        id="message_demo_user",
        session_id="session_demo",
        role="user",
        content="Research AI Agent product patterns.",
        created_at=now_iso(),
    ),
    Message(
        id="message_demo_assistant",
        session_id="session_demo",
        role="assistant",
        content="This is a FastAPI mock response. The real Agent runtime comes next.",
        created_at=now_iso(),
        artifact_ids=["artifact_demo"],
    ),
]

artifacts: list[Artifact] = [
    Artifact(
        id="artifact_demo",
        session_id="session_demo",
        type="markdown_report",
        title="AI Agent research report",
        status="ready",
        content=(
            "# AI Agent research report\n\n"
            "This backend mock artifact will be replaced by generated content."
        ),
    )
]

runs: list[AgentRun] = []

models: list[ModelConfig] = [
    ModelConfig(
        id="model_sensenova_default",
        name="SenseNova default model",
        provider="sensenova",
        is_default=False,
        is_available=True,
    ),
    ModelConfig(
        id="model_openclaw",
        name="OpenClaw Agent",
        provider="openai_compatible",
        base_url="http://localhost:8643",
        is_default=False,
        is_available=True,
    ),
    ModelConfig(
        id="model_hermes",
        name="Hermes Agent",
        provider="openai_compatible",
        base_url="http://localhost:8642",
        is_default=True,
        is_available=True,
    ),
]

skills: list[Skill] = [
    Skill(
        key="data_analysis",
        name="Data analysis",
        description="Upload datasets and analyze trends, charts, and summaries.",
        version="0.1.0",
        enabled=True,
    ),
    Skill(
        key="deep_research",
        name="Deep research",
        description="Turn a topic into a structured research report.",
        version="0.1.0",
        enabled=True,
        is_default=True,
    ),
    Skill(
        key="ppt_generation",
        name="PPT generation",
        description="Generate slide structures and preview presentation drafts.",
        version="0.1.0",
        enabled=True,
    ),
    Skill(
        key="u1_image",
        name="u1 image",
        description="Generate image concepts from prompts.",
        version="0.1.0",
        enabled=True,
    ),
]

data_context_settings = DataContextSettings(
    auto_summarize_context=True,
    context_retention_days=30,
    max_context_messages=40,
    save_conversation_history=True,
    save_uploaded_files=True,
)
