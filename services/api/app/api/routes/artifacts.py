import base64
import html
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import or_, select

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.models import Artifact, Conversation, ConversationShare
from app.services.persistence import (
    get_conversation_or_404,
    require_owner,
    to_artifact,
)
from app.services.session_artifacts import is_debug_artifact
from app.services.settings_service import user_developer_mode

router = APIRouter()

MEDIA_TYPES = {
    ".csv": "text/csv; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

HTML_SLIDE_SUFFIXES = {".htm", ".html"}
IMAGE_SLIDE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
DECK_SLIDE_SUFFIXES = HTML_SLIDE_SUFFIXES | IMAGE_SLIDE_SUFFIXES


async def ensure_artifact_visible(
    db: DbSession,
    artifact: Artifact,
    current_user: CurrentUser,
) -> None:
    if not is_debug_artifact(artifact):
        return
    if not await user_developer_mode(db, current_user):
        raise HTTPException(status_code=404, detail="Artifact not found")


def artifact_download_name(artifact: Artifact) -> str:
    metadata = artifact.artifact_metadata or {}
    filename = str(metadata.get("filename") or "").strip()
    if filename:
        return filename
    suffix_by_type = {
        "chart": ".csv",
        "data_table": ".csv",
        "debug_json": ".json",
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
        path = normalize_artifact_path(raw_path)
        if path.exists() and path.is_file():
            return path
    return None


def slide_sort_key(artifact: Artifact) -> tuple[int, str]:
    metadata = artifact.artifact_metadata or {}
    filename = str(metadata.get("filename") or artifact.title or "")
    match = re.search(r"page[_-]?(\d+)", filename, re.IGNORECASE)
    return (int(match.group(1)) if match else 9999, filename)


def slide_path_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"page[_-]?(\d+)", path.stem, re.IGNORECASE)
    return (int(match.group(1)) if match else 9999, path.name)


def slide_identity(value: str) -> str:
    match = re.search(r"page[_-]?(\d+)", value, re.IGNORECASE)
    if match:
        return f"page_{int(match.group(1)):03d}"
    return value.lower()


def is_deck_slide_path(path: Path) -> bool:
    return re.search(r"page[_-]?\d+", path.stem, re.IGNORECASE) is not None


def normalize_artifact_path(raw_path: str) -> Path:
    cleaned = raw_path.strip().strip(".,;:)]}\"'")
    normalized = cleaned.replace("\\", "/")
    if normalized.startswith("/mnt/") and len(normalized) > 6 and normalized[6] == "/":
        drive = normalized[5].upper()
        rest = normalized[7:].replace("/", "\\")
        return Path(f"{drive}:\\{rest}")
    if normalized.startswith("/home/"):
        return Path(r"\\wsl.localhost\Ubuntu") / normalized.lstrip("/").replace("/", "\\")
    return Path(cleaned)


def deck_slide_directories(artifact: Artifact) -> list[Path]:
    metadata = artifact.artifact_metadata or {}
    directories: list[Path] = []
    seen: set[str] = set()
    for key in (
        "path",
        "originalPath",
        "adapterSourceDir",
        "sourceDir",
        "storageConversationDir",
    ):
        raw_path = metadata.get(key)
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = normalize_artifact_path(raw_path)
        directory = path if path.is_dir() else path.parent
        candidate_dirs = [directory, directory / "pages"]
        for candidate in candidate_dirs:
            directory_key = str(candidate).lower()
            if directory_key in seen or not candidate.exists() or not candidate.is_dir():
                continue
            seen.add(directory_key)
            directories.append(candidate)
    return directories


def discover_deck_slide_paths(artifact: Artifact) -> list[Path]:
    slide_paths: list[Path] = []
    seen_paths: set[str] = set()
    seen_slides: set[str] = set()
    for directory in deck_slide_directories(artifact):
        for path in directory.glob("*"):
            if not path.is_file() or path.suffix.lower() not in DECK_SLIDE_SUFFIXES:
                continue
            if not is_deck_slide_path(path):
                continue
            path_key = str(path).lower()
            slide_key = slide_identity(path.stem)
            if path_key in seen_paths or slide_key in seen_slides:
                continue
            seen_paths.add(path_key)
            seen_slides.add(slide_key)
            slide_paths.append(path)

    return sorted(slide_paths, key=slide_path_sort_key)


def slide_content_from_path(path: Path) -> tuple[str, str] | None:
    suffix = path.suffix.lower()
    if suffix in HTML_SLIDE_SUFFIXES:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "text/html"
        except OSError:
            return None
    if suffix in IMAGE_SLIDE_SUFFIXES:
        try:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            return None
        media_type = MEDIA_TYPES.get(suffix, "image/png")
        escaped_title = html.escape(path.stem)
        content = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<style>"
            "html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:#fff;}"
            "body{display:flex;align-items:center;justify-content:center;}"
            "img{width:100%;height:100%;object-fit:contain;display:block;}"
            "</style></head><body>"
            f"<img alt=\"{escaped_title}\" src=\"data:{media_type};base64,{encoded}\">"
            "</body></html>"
        )
        return content, "text/html"
    return None


def slides_from_paths(artifact: Artifact, paths: list[Path]) -> list[schemas.SlidePreview]:
    slides: list[schemas.SlidePreview] = []
    for index, path in enumerate(paths, start=1):
        slide_content = slide_content_from_path(path)
        if slide_content is None:
            continue
        content, content_type = slide_content
        slides.append(
            schemas.SlidePreview(
                content=content,
                content_type=content_type,
                id=f"{artifact.id}_path_{index}",
                index=index,
                title=path.stem,
            )
        )
    return slides


def dedupe_slide_artifacts(artifacts: list[Artifact]) -> list[Artifact]:
    deduped: list[Artifact] = []
    seen: set[str] = set()
    for artifact in artifacts:
        metadata = artifact.artifact_metadata or {}
        filename = str(metadata.get("filename") or artifact.title or artifact.id)
        key = slide_identity(filename)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped


@router.get("", response_model=list[schemas.Artifact])
async def list_artifacts(
    db: DbSession,
    current_user: CurrentUser,
    session_id: str | None = Query(default=None, alias="sessionId"),
    session_id_snake: str | None = Query(default=None, alias="session_id"),
    run_id: str | None = Query(default=None, alias="runId"),
    run_id_snake: str | None = Query(default=None, alias="run_id"),
) -> list[schemas.Artifact]:
    resolved_session_id = session_id or session_id_snake
    resolved_run_id = run_id or run_id_snake
    visibility_filter = or_(
        Conversation.user_id == current_user.id,
        Conversation.visibility == "public",
        (Conversation.visibility == "shared")
        & (ConversationShare.user_id == current_user.id),
    )
    filters = [visibility_filter]
    if resolved_session_id:
        filters.append(Artifact.conversation_id == resolved_session_id)
    if resolved_run_id:
        filters.append(Artifact.run_id == resolved_run_id)

    result = await db.execute(
        select(Artifact)
        .join(Conversation)
        .outerjoin(ConversationShare, ConversationShare.conversation_id == Conversation.id)
        .where(*filters)
        .order_by(Artifact.created_at.desc())
    )
    developer_mode = await user_developer_mode(db, current_user)
    return [
        to_artifact(item, include_payload=False)
        for item in result.scalars().unique().all()
        if developer_mode or not is_debug_artifact(item)
    ]


@router.get("/{artifact_id}", response_model=schemas.Artifact)
async def get_artifact(
    artifact_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.Artifact:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    await ensure_artifact_visible(db, artifact, current_user)
    return to_artifact(artifact)


@router.get("/{artifact_id}/slides", response_model=schemas.ArtifactSlides)
async def get_artifact_slides(
    artifact_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ArtifactSlides:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    await ensure_artifact_visible(db, artifact, current_user)
    if artifact.type != "ppt_deck":
        raise HTTPException(status_code=400, detail="Artifact is not a PPT deck")

    metadata = artifact.artifact_metadata or {}
    deck_slide_paths = discover_deck_slide_paths(artifact)
    deck_slides = slides_from_paths(artifact, deck_slide_paths)
    if deck_slides:
        return schemas.ArtifactSlides(
            artifact_id=artifact.id,
            slides=deck_slides,
            source="deck_slide_paths",
        )

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
        html_artifacts = dedupe_slide_artifacts(
            sorted(html_result.scalars().all(), key=slide_sort_key)
        )
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
            return schemas.ArtifactSlides(
                artifact_id=artifact.id, slides=slides, source="html_artifacts"
            )

    return schemas.ArtifactSlides(artifact_id=artifact.id, slides=[], source="unavailable")


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        return None
    conversation = await get_conversation_or_404(db, artifact.conversation_id, current_user)
    await ensure_artifact_visible(db, artifact, current_user)
    require_owner(conversation, current_user)
    await db.delete(artifact)
    await db.commit()
    return None


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await get_conversation_or_404(db, artifact.conversation_id, current_user)
    await ensure_artifact_visible(db, artifact, current_user)
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
