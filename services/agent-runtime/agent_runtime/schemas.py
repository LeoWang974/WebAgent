from typing import List, Optional
from datetime import datetime


class AgentRunStep:
    def __init__(self, id: str, label: str, status: str, timestamp: Optional[str] = None):
        self.id = id
        self.label = label
        self.status = status
        self.timestamp = timestamp


class AgentRunCreate:
    def __init__(self, content: str, session_id: str, skill_key: Optional[str] = None, model_id: Optional[str] = None):
        self.content = content
        self.session_id = session_id
        self.skill_key = skill_key
        self.model_id = model_id


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


class AgentRunEvent:
    def __init__(
        self,
        run_id: str,
        status: str,
        progress: int,
        completed_at: Optional[str] = None,
        step: Optional[AgentRunStep] = None,
    ):
        self.run_id = run_id
        self.status = status
        self.progress = progress
        self.completed_at = completed_at
        self.step = step
