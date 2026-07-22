from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import Conversation, ConversationFolder


async def get_owned_folder_or_404(
    db: AsyncSession,
    folder_id: str,
    user_id: str,
) -> ConversationFolder:
    result = await db.execute(
        select(ConversationFolder).where(
            ConversationFolder.id == folder_id,
            ConversationFolder.user_id == user_id,
        )
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Conversation folder not found")
    return folder


def to_folder_schema(folder: ConversationFolder) -> schemas.ConversationFolder:
    return schemas.ConversationFolder(
        id=folder.id,
        name=folder.name,
        created_at=folder.created_at.isoformat(),
        updated_at=folder.updated_at.isoformat(),
    )


async def list_user_folders(
    db: AsyncSession,
    user_id: str,
) -> list[schemas.ConversationFolder]:
    result = await db.execute(
        select(ConversationFolder)
        .where(ConversationFolder.user_id == user_id)
        .order_by(ConversationFolder.created_at.asc())
    )
    return [to_folder_schema(folder) for folder in result.scalars().all()]


async def create_user_folder(
    db: AsyncSession,
    user_id: str,
    name: str,
) -> schemas.ConversationFolder:
    folder_name = name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    folder = ConversationFolder(user_id=user_id, name=folder_name)
    db.add(folder)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Folder name already exists") from exc
    await db.refresh(folder)
    return to_folder_schema(folder)


async def update_user_folder(
    db: AsyncSession,
    folder_id: str,
    user_id: str,
    name: str,
) -> schemas.ConversationFolder:
    folder = await get_owned_folder_or_404(db, folder_id, user_id)
    folder_name = name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    folder.name = folder_name
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Folder name already exists") from exc
    await db.refresh(folder)
    return to_folder_schema(folder)


async def delete_user_folder(
    db: AsyncSession,
    folder_id: str,
    user_id: str,
) -> None:
    folder = await get_owned_folder_or_404(db, folder_id, user_id)
    result = await db.execute(
        select(Conversation).where(
            Conversation.folder_id == folder.id,
            Conversation.user_id == user_id,
        )
    )
    for conversation in result.scalars().all():
        conversation.folder_id = None
    await db.delete(folder)
    await db.commit()
