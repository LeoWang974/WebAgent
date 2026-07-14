from typing import Any, Literal

from app.schemas.base import ApiModel

ArtifactType = Literal[
    "markdown_report",
    "html_page",
    "ppt_deck",
    "image_result",
    "data_table",
    "chart",
]
ArtifactStatus = Literal["pending", "rendering", "ready", "failed"]


class Artifact(ApiModel):
    content: str | None = None
    created_at: str | None = None
    id: str
    metadata: dict[str, Any] | None = None
    run_id: str | None = None
    session_id: str
    type: ArtifactType
    title: str
    status: ArtifactStatus


class SlidePreview(ApiModel):
    content: str | None = None
    content_type: str = "text/html"
    id: str
    index: int
    title: str


class ArtifactSlides(ApiModel):
    artifact_id: str
    slides: list[SlidePreview]
    source: str


class FileAsset(ApiModel):
    content_type: str
    created_at: str
    filename: str
    id: str
    metadata: dict[str, Any] | None = None
    session_id: str | None = None
    size: int
    url: str | None = None
