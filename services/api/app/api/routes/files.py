from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.models import FileAsset
from app.services.persistence import get_conversation_or_404, to_file_asset

router = APIRouter()

ALLOWED_EXTENSIONS_BY_CONTENT_TYPE = {
    "application/json": {".json"},
    "application/pdf": {".pdf"},
    "application/vnd.ms-excel": {".csv", ".xls"},
    "application/vnd.ms-powerpoint": {".ppt"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "image/gif": {".gif"},
    "image/jpeg": {".jpeg", ".jpg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "text/csv": {".csv"},
    "text/html": {".htm", ".html"},
    "text/markdown": {".markdown", ".md"},
    "text/plain": {".csv", ".json", ".log", ".markdown", ".md", ".txt"},
}


def upload_storage_root() -> Path:
    root = Path(__file__).resolve().parents[4] / "runtime" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_upload_type(filename: str, content_type: str) -> None:
    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_content_type in {"", "application/octet-stream"}:
        return

    allowed_extensions = ALLOWED_EXTENSIONS_BY_CONTENT_TYPE.get(normalized_content_type)
    if allowed_extensions is None:
        return

    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Upload content type {normalized_content_type} does not match "
                f"file extension {extension or '<none>'}. Expected one of: {allowed}."
            ),
        )


@router.get("", response_model=list[schemas.FileAsset])
async def list_files(db: DbSession, current_user: CurrentUser) -> list[schemas.FileAsset]:
    result = await db.execute(
        select(FileAsset)
        .where(FileAsset.conversation_id.is_(None))
        .order_by(FileAsset.created_at.desc())
    )
    return [to_file_asset(item) for item in result.scalars().all()]


@router.post("", response_model=schemas.FileAsset)
async def upload_file(
    db: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
    session_id: Annotated[str | None, Form()] = None,
) -> schemas.FileAsset:
    if session_id:
        await get_conversation_or_404(db, session_id, current_user, require_write=True)

    content = await file.read()
    filename = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"
    validate_upload_type(filename, content_type)
    file_asset = FileAsset(
        conversation_id=session_id,
        content_type=content_type,
        filename=filename,
        file_metadata={},
        size=len(content),
        storage_key="pending",
    )
    db.add(file_asset)
    await db.flush()

    storage_dir = upload_storage_root() / (session_id or "global")
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{file_asset.id}-{filename}"
    storage_path.write_bytes(content)
    file_asset.storage_key = str(storage_path)
    file_asset.file_metadata = {"path": str(storage_path)}

    await db.commit()
    await db.refresh(file_asset)
    return to_file_asset(file_asset)
