from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import select

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.models import FileAsset
from app.services.persistence import get_conversation_or_404, to_file_asset

router = APIRouter()


def upload_storage_root() -> Path:
    root = Path(__file__).resolve().parents[4] / "runtime" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


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
    file_asset = FileAsset(
        conversation_id=session_id,
        content_type=file.content_type or "application/octet-stream",
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
