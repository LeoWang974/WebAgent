import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db.session import get_db
from app.models import Artifact, Conversation, ConversationShare, User
from app.services.persistence import get_current_user, get_conversation_or_404, require_owner, to_artifact

router = APIRouter()

MEDIA_TYPES = {
    ".csv": "text/csv; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def artifact_download_name(artifact: Artifact) -> str:
    metadata = artifact.artifact_metadata or {}
    filename = str(metadata.get("filename") or "").strip()
    if filename:
        return filename
    suffix_by_type = {
        "chart": ".csv",
        "data_table": ".csv",
        "html_page": ".html",
        "image_result": ".png",
        "markdown_report": ".md",
        "ppt_deck": ".pptx",
    }
    return f"{artifact.title or artifact.id}{suffix_by_type.get(artifact.type, '.txt')}"


def artifact_file_path(artifact: Artifact) -> Path | None:
    metadata = artifact.artifact_metadata or {}
    for key in ("path", "originalPath"):
        raw_path = metadata.get(key)
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        if path.exists() and path.is_file():
            return path
    return None


def slide_sort_key(artifact: Artifact) -> tuple[int, str]:
    metadata = artifact.artifact_metadata or {}
    filename = str(metadata.get("filename") or artifact.title or "")
    match = re.search(r"page[_-]?(\d+)", filename, re.IGNORECASE)
    return (int(match.group(1)) if match else 9999, filename)


@router.get("", response_model=list[schemas.Artifact])
async def list_artifacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[schemas.Artifact]:
    result = await db.execute(
        select(Artifact)
        .join(Conversation)
        .outerjoin(ConversationShare, ConversationShare.conversation_id == Conversation.id)
        .where(
            or_(
                Conversation.user_id == current_user.id,
                Conversation.visibility == "public",
                (Conversation.visibility == "shared")
                & (ConversationShare.user_id == current_user.id),
            )
        )
        .order_by(Artifact.created_at.desc())
    )
    return [to_artifact(item) for item in result.scalars().unique().all()]


@router.get("/{artifact_id}", response_model=schemas.Artifact)
async def get_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.Artifact:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    return to_artifact(artifact)


@router.get("/{artifact_id}/slides", response_model=schemas.ArtifactSlides)
async def get_artifact_slides(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.ArtifactSlides:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    if artifact.type != "ppt_deck":
        raise HTTPException(status_code=400, detail="Artifact is not a PPT deck")

    metadata = artifact.artifact_metadata or {}
    metadata_slides = metadata.get("slides")
    if isinstance(metadata_slides, list) and metadata_slides:
        slides = [
            schemas.SlidePreview(
                content=None,
                content_type="application/json",
                id=f"{artifact.id}_{index}",
                index=index,
                title=str(item.get("title") if isinstance(item, dict) else f"Slide {index}"),
            )
            for index, item in enumerate(metadata_slides, start=1)
        ]
        return schemas.ArtifactSlides(artifact_id=artifact.id, slides=slides, source="metadata")

    if artifact.run_id:
        html_result = await db.execute(
            select(Artifact).where(
                Artifact.run_id == artifact.run_id,
                Artifact.conversation_id == artifact.conversation_id,
                Artifact.type == "html_page",
            )
        )
        html_artifacts = sorted(html_result.scalars().all(), key=slide_sort_key)
        slides = [
            schemas.SlidePreview(
                content=html_artifact.content,
                content_type="text/html",
                id=html_artifact.id,
                index=index,
                title=html_artifact.title,
            )
            for index, html_artifact in enumerate(html_artifacts, start=1)
            if html_artifact.content
        ]
        if slides:
            return schemas.ArtifactSlides(artifact_id=artifact.id, slides=slides, source="html_artifacts")

    return schemas.ArtifactSlides(artifact_id=artifact.id, slides=[], source="unavailable")


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        return None
    conversation = await get_conversation_or_404(db, artifact.conversation_id, current_user)
    require_owner(conversation, current_user)
    await db.delete(artifact)
    await db.commit()
    return None


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    path = artifact_file_path(artifact)
    if path is not None:
        return FileResponse(
            path,
            media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
            filename=artifact_download_name(artifact),
        )

    filename = artifact_download_name(artifact)
    suffix = Path(filename).suffix.lower()
    return Response(
        content=artifact.content or artifact.title,
        media_type=MEDIA_TYPES.get(suffix, "text/plain; charset=utf-8"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
