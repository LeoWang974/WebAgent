from fastapi import APIRouter, File, Form, UploadFile

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.get("", response_model=list[schemas.FileAsset])
async def list_files() -> list[schemas.FileAsset]:
    return mock_store.files


@router.post("", response_model=schemas.FileAsset)
async def upload_file(
    file: UploadFile = File(...), session_id: str | None = Form(default=None)
) -> schemas.FileAsset:
    content = await file.read()
    file_asset = schemas.FileAsset(
        content_type=file.content_type or "application/octet-stream",
        created_at=mock_store.now_iso(),
        filename=file.filename or "upload.bin",
        id=mock_store.new_id("file"),
        session_id=session_id,
        size=len(content),
    )
    mock_store.files.insert(0, file_asset)
    return file_asset

