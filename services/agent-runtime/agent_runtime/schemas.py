

class AgentRunStep:
    def __init__(self, id: str, label: str, status: str, timestamp: str | None = None):
        self.id = id
        self.label = label
        self.status = status
        self.timestamp = timestamp


class AgentRunCreate:
    def __init__(
        self,
        content: str,
        session_id: str,
        skill_key: str | None = None,
        model_id: str | None = None,
        run_id: str | None = None,
    ):
        self.content = content
        self.session_id = session_id
        self.skill_key = skill_key
        self.model_id = model_id
        self.run_id = run_id


class AgentRun:
    def __init__(
        self,
        id: str,
        session_id: str,
        status: str,
        title: str,
        progress: int,
        steps: list[AgentRunStep],
        started_at: str | None = None,
        completed_at: str | None = None,
        error: str | None = None,
        output: str | None = None,
        artifacts: list["AgentArtifactRef"] | None = None,
    ):
        self.id = id
        self.session_id = session_id
        self.status = status
        self.title = title
        self.progress = progress
        self.steps = steps
        self.started_at = started_at
        self.completed_at = completed_at
        self.error = error
        self.output = output
        self.artifacts = artifacts or []


class AgentArtifactRef:
    def __init__(
        self,
        path: str,
        artifact_type: str | None = None,
        run_id: str | None = None,
        source_dir: str | None = None,
        title: str | None = None,
    ):
        self.path = path
        self.artifact_type = artifact_type
        self.run_id = run_id
        self.source_dir = source_dir
        self.title = title


class AgentRunEvent:
    def __init__(
        self,
        run_id: str,
        status: str,
        progress: int,
        completed_at: str | None = None,
        event_type: str = "stage_update",
        error: str | None = None,
        payload: dict | None = None,
        step: AgentRunStep | None = None,
        output: str | None = None,
    ):
        self.run_id = run_id
        self.event_type = event_type
        self.status = status
        self.progress = progress
        self.completed_at = completed_at
        self.error = error
        self.payload = payload or {}
        self.step = step
        self.output = output
