# File purpose: Verifies test settings service behavior and its regression contracts.
# Main declarations: test_listing_models_removes_legacy_runtime_models verifies listing
# models removes legacy runtime adapter entries;
# test_default_model_repair_leaves_exactly_one_default verifies default model repair leaves
# exactly one default.

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ModelConfig, User
from app.services.settings_service import ensure_default_models, list_user_models


@pytest.mark.asyncio
async def test_listing_models_removes_legacy_runtime_models(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
):
    user = seeded_users["owner"]
    async with db_sessionmaker() as db:
        legacy_model = ModelConfig(
            user_id=user.id,
            name="Hermes local runtime",
            provider="custom",
            base_url="http://localhost:8642",
            encrypted_api_key=None,
            is_default=False,
            is_available=True,
        )
        db.add(legacy_model)
        await db.commit()
        legacy_model_id = legacy_model.id

        models = await list_user_models(db, user)

        assert legacy_model_id not in {model.id for model in models}
        assert {model.name for model in models} == {"SenseNova"}


@pytest.mark.asyncio
async def test_default_model_repair_leaves_exactly_one_default(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
):
    user = seeded_users["owner"]
    async with db_sessionmaker() as db:
        db.add_all(
            [
                ModelConfig(
                    user_id=user.id,
                    name="first",
                    provider="custom",
                    is_default=True,
                    is_available=True,
                ),
                ModelConfig(
                    user_id=user.id,
                    name="second",
                    provider="custom",
                    is_default=True,
                    is_available=True,
                ),
            ]
        )
        await db.commit()

        await ensure_default_models(db, user)
        result = await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id))
        models = list(result.scalars().all())

        assert sum(model.is_default for model in models) == 1


@pytest.mark.asyncio
async def test_user_configured_optional_model_is_preserved(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    seeded_users: dict[str, User],
):
    user = seeded_users["owner"]
    async with db_sessionmaker() as db:
        configured = ModelConfig(
            user_id=user.id,
            name="DeepSeek",
            provider="deepseek",
            base_url="https://api.deepseek.com/v1",
            encrypted_api_key="encrypted-key",
            is_default=False,
            is_available=True,
        )
        db.add(configured)
        await db.commit()

        models = await list_user_models(db, user)

        assert "DeepSeek" in {model.name for model in models}
