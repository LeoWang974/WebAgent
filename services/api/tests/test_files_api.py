from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import FileAsset


@pytest.mark.asyncio
async def test_file_upload_persists_and_links_to_session(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
    db_sessionmaker: async_sessionmaker[AsyncSession],
):
    session_response = await api_client.post(
        "/api/sessions",
        json={"title": "File upload session"},
        headers=auth_headers["owner"],
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    upload_response = await api_client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("note.txt", b"hello from db", "text/plain")},
        headers=auth_headers["owner"],
    )
    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["filename"] == "note.txt"
    assert uploaded["sessionId"] == session_id

    session_files_response = await api_client.get(
        f"/api/sessions/{session_id}/files",
        headers=auth_headers["owner"],
    )
    assert session_files_response.status_code == 200
    assert [item["id"] for item in session_files_response.json()] == [uploaded["id"]]

    async with db_sessionmaker() as db:
        file_asset = await db.get(FileAsset, uploaded["id"])
        assert file_asset is not None
        assert file_asset.conversation_id == session_id
        assert file_asset.filename == "note.txt"
        assert file_asset.storage_key
        assert Path(file_asset.storage_key).exists()


@pytest.mark.asyncio
async def test_file_upload_rejects_mismatched_content_type(
    api_client: AsyncClient,
    auth_headers: dict[str, dict[str, str]],
):
    upload_response = await api_client.post(
        "/api/files",
        files={"file": ("report.pdf", b"not really a png", "image/png")},
        headers=auth_headers["owner"],
    )

    assert upload_response.status_code == 400
    assert "does not match file extension" in upload_response.json()["detail"]
