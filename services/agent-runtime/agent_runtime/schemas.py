

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
        model_id: str | None = None,
        run_id: str | None = None,
        working_dir: str | None = None,
        artifacts_dir: str | None = None,
    ):
        self.content = content
        self.session_id = session_id
        self.model_id = model_id
        self.run_id = run_id
        self.working_dir = working_dir
        self.artifacts_dir = artifacts_dir


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
