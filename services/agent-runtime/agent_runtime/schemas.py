from typing import List, Optional


class AgentRunStep:
    def __init__(self, id: str, label: str, status: str, timestamp: Optional[str] = None):
        self.id = id
        self.label = label
        self.status = status
        self.timestamp = timestamp


class AgentRunCreate:
    def __init__(
        self,
        content: str,
        session_id: str,
        skill_key: Optional[str] = None,
        model_id: Optional[str] = None,
        run_id: Optional[str] = None,
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
        steps: List[AgentRunStep],
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        error: Optional[str] = None,
        output: Optional[str] = None,
        artifacts: Optional[List["AgentArtifactRef"]] = None,
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
        artifact_type: Optional[str] = None,
        run_id: Optional[str] = None,
        source_dir: Optional[str] = None,
        title: Optional[str] = None,
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
        completed_at: Optional[str] = None,
        event_type: str = "stage_update",
        error: Optional[str] = None,
        payload: Optional[dict] = None,
        step: Optional[AgentRunStep] = None,
        output: Optional[str] = None,
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
