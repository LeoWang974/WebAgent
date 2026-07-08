from fastapi import APIRouter, HTTPException, Response

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.Artifact])
async def list_artifacts() -> list[schemas.Artifact]:
    return mock_store.artifacts


@router.get("/{artifact_id}", response_model=schemas.Artifact)
async def get_artifact(artifact_id: str) -> schemas.Artifact:
    artifact = next((item for item in mock_store.artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(artifact_id: str) -> None:
    mock_store.artifacts[:] = [item for item in mock_store.artifacts if item.id != artifact_id]
    return None


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str) -> Response:
    artifact = next((item for item in mock_store.artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return Response(
        content=artifact.content or artifact.title,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artifact.id}.txt"'},
    )

