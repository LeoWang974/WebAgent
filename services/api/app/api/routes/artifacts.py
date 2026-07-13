from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.db.session import get_db
from app.models import Artifact, Conversation, ConversationShare, User
from app.services.persistence import get_current_user, get_conversation_or_404, require_owner, to_artifact

router = APIRouter()


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
    return Response(
        content=artifact.content or artifact.title,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artifact.id}.txt"'},
    )
