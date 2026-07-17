from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models import User
from app.services.persistence import ensure_user


@pytest.fixture
def auth_headers() -> dict[str, dict[str, str]]:
    return {
        "owner": {"Authorization": "Bearer dev_token_owner@example.com"},
        "shared": {"Authorization": "Bearer dev_token_shared@example.com"},
        "stranger": {"Authorization": "Bearer dev_token_stranger@example.com"},
        "admin": {"Authorization": "Bearer dev_token_admin@example.com"},
    }


@pytest_asyncio.fixture
async def db_sessionmaker(tmp_path) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    database_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessionmaker
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(db_sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, User]:
    async with db_sessionmaker() as db:
        owner = await ensure_user(
            db,
            "owner@example.com",
            "ownerpass",
            nickname="Owner",
            username="owner",
        )
        shared = await ensure_user(db, "shared@example.com", nickname="Shared", username="shared")
        stranger = await ensure_user(
            db,
            "stranger@example.com",
            nickname="Stranger",
            username="stranger",
        )
        admin = await ensure_user(
            db,
            "admin@example.com",
            "adminpass",
            nickname="Admin",
            role="admin",
            username="admin",
        )
        return {
            "owner": owner,
            "shared": shared,
            "stranger": stranger,
            "admin": admin,
        }


@pytest_asyncio.fixture
async def api_client(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
) -> AsyncGenerator[AsyncClient, None]:
    settings.cleanup_enabled = False
    settings.allow_dev_auth_fallback = True
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
