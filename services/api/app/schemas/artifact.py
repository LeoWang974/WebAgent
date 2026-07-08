from typing import Any, Literal

from app.schemas.base import ApiModel

ArtifactType = Literal["markdown_report", "ppt_deck", "image_result", "data_table", "chart"]
ArtifactStatus = Literal["pending", "rendering", "ready", "failed"]


class Artifact(ApiModel):
    content: str | None = None
    id: str
    metadata: dict[str, Any] | None = None
    session_id: str
    type: ArtifactType
    title: str
    status: ArtifactStatus


class FileAsset(ApiModel):
    content_type: str
    created_at: str
    filename: str
    id: str
    metadata: dict[str, Any] | None = None
    session_id: str | None = None
    size: int
    url: str | None = None

