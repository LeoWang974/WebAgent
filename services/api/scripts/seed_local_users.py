import asyncio

from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import Conversation, User
from app.services.persistence import get_user_by_email, get_user_by_username, normalize_email


async def upsert_user(
    *,
    email: str,
    username: str,
    password: str,
    nickname: str,
    role: str,
) -> User:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if user is None:
            user = await get_user_by_email(db, email)

        if user is None:
            user = User(
                email=normalize_email(email),
                username=username,
                hashed_password=hash_password(password),
                nickname=nickname,
                role=role,
            )
            db.add(user)
        else:
            user.email = normalize_email(email)
            user.username = username
            user.hashed_password = hash_password(password)
            user.nickname = nickname
            user.role = role

        await db.commit()
        await db.refresh(user)
        return user


async def move_conversations_to_user(user: User) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Conversation)
            .where(Conversation.user_id != user.id)
            .values(user_id=user.id)
        )
        await db.commit()
        return result.rowcount or 0


async def count_conversations_for_user(user: User) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Conversation).where(Conversation.user_id == user.id))
        return len(result.scalars().all())


async def main() -> None:
    if settings.is_production:
        raise RuntimeError("seed_local_users.py is for local development only.")

    test_user = await upsert_user(
        email="test@webagent.local",
        username="test",
        password="test",
        nickname="test",
        role="user",
    )
    admin_user = await upsert_user(
        email="admin@webagent.local",
        username="admin",
        password="admin",
        nickname="admin",
        role="admin",
    )
    moved_count = await move_conversations_to_user(test_user)
    test_conversation_count = await count_conversations_for_user(test_user)
    print(
        "Seeded users: "
        f"test={test_user.id}, admin={admin_user.id}; "
        f"moved_conversations={moved_count}; "
        f"test_conversations={test_conversation_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
