# File purpose: Defines the durable Artifact Manifest v2 contract shared by adapters and services.
# Main declarations: ArtifactManifestEntry describes one output; ArtifactManifest describes a run.

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.artifact import ArtifactType

ARTIFACT_MANIFEST_SCHEMA = "webagent.artifacts.v2"

ArtifactManifestStatus = Literal["collecting", "finalized", "failed"]
ArtifactManifestEntryStatus = Literal["ready", "missing"]
ArtifactManifestRole = Literal["primary", "intermediate", "preview_fallback"]
ArtifactManifestDiscoverySource = Literal[
    "adapter_event",
    "terminal_output",
    "recovery_scan",
]


class ArtifactManifestEntry(BaseModel):
    entry_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    artifact_type: ArtifactType
    title: str = Field(min_length=1)
    role: ArtifactManifestRole = "primary"
    status: ArtifactManifestEntryStatus = "ready"
    discovered_by: ArtifactManifestDiscoverySource
    source_dir: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["webagent.artifacts.v2"] = Field(
        default=ARTIFACT_MANIFEST_SCHEMA,
        alias="schema",
    )
    run_id: str = Field(min_length=1)
    conversation_id: str | None = None
    producer: Literal["hermes_cli_adapter"] = "hermes_cli_adapter"
    status: ArtifactManifestStatus = "collecting"
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None = None
    artifacts: list[ArtifactManifestEntry] = Field(default_factory=list)
    recovery_used: bool = False
    errors: list[str] = Field(default_factory=list)
