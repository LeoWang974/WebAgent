# File purpose: Implements the settings service backend service workflow.
# Main declarations: to_model_schema converts model schema; check_runtime_model checks runtime
# model; to_skill_schema converts skill schema; to_data_context_schema converts data context
# schema; to_interface_schema converts interface schema; ensure_default_models ensures default
# models; list_user_models lists user models; get_user_model retrieves user model;
# ensure_user_settings ensures user settings; user_developer_mode handles user developer mode;
# ensure_default_skills ensures default skills; list_skill_configs lists skill configs;
# get_skill_config retrieves skill config.

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models import ModelConfig, SkillConfig, User, UserSettings
from app.services.model_runtime_config import model_runtime_config_builder
from app.services.model_secret_encryption import mask_model_secret

DEFAULT_DATA_CONTEXT = {
    "auto_summarize_context": True,
    "context_retention_days": 30,
    "max_context_messages": 40,
    "save_conversation_history": True,
    "save_uploaded_files": True,
}

DEFAULT_INTERFACE = {"developer_mode": False}

DEFAULT_MODELS = [
    {
        "name": "SenseNova default model",
        "provider": "sensenova",
        "base_url": None,
        "encrypted_api_key": None,
        "is_default": True,
        "is_available": True,
    },
]

DEFAULT_SKILLS = [
    {
        "key": "data_analysis",
        "name": "Data analysis",
        "description": "Upload datasets and analyze trends, charts, and summaries.",
        "enabled": True,
        "is_default": False,
        "current_version": "0.1.0",
    },
    {
        "key": "deep_research",
        "name": "Deep research",
        "description": "Turn a topic into a structured research report.",
        "enabled": True,
        "is_default": True,
        "current_version": "0.1.0",
    },
    {
        "key": "ppt_generation",
        "name": "PPT generation",
        "description": "Generate slide structures and preview presentation drafts.",
        "enabled": True,
        "is_default": False,
        "current_version": "0.1.0",
    },
    {
        "key": "u1_image",
        "name": "u1 image",
        "description": "Generate image concepts from prompts.",
        "enabled": True,
        "is_default": False,
        "current_version": "0.1.0",
    },
]


def to_model_schema(
    model: ModelConfig,
    runtime_status: dict[str, Any] | None = None,
) -> schemas.ModelConfig:
    return schemas.ModelConfig(
        id=model.id,
        name=model.name,
        provider=model.provider,
        base_url=model.base_url,
        is_default=model.is_default,
        is_available=model.is_available,
        masked_api_key=mask_model_secret(model.encrypted_api_key),
        runtime_status=runtime_status,
    )


async def check_runtime_model(
    db: AsyncSession,
    current_user: User,
    model: ModelConfig,
) -> dict[str, Any]:
    from app.services.agent_runs import create_hermes_adapter

    runtime_config = await model_runtime_config_builder.build_for_user(
        db,
        current_user,
        model.id,
    )
    adapter = create_hermes_adapter(
        current_user,
        model_runtime_config=runtime_config,
    )
    if adapter is None:
        return {
            "adapterKey": "hermes",
            "ok": False,
            "status": "unavailable",
            "message": "Runtime adapter is unavailable.",
        }

    if not hasattr(adapter, "health_check"):
        return {
            "adapterKey": "hermes",
            "ok": True,
            "status": "available",
            "message": "Runtime adapter is available; no active health check is implemented.",
        }

    try:
        health = await adapter.health_check()
    except Exception as error:
        return {
            "adapterKey": "hermes",
            "ok": False,
            "status": "unavailable",
            "message": str(error),
        }

    ok = bool(health.get("ok")) if isinstance(health, dict) else False
    return {
        "adapterKey": "hermes",
        "ok": ok,
        "status": "connected" if ok else "unavailable",
        "message": "Runtime health check passed." if ok else "Runtime health check failed.",
        "health": health,
    }


def to_skill_schema(skill: SkillConfig) -> schemas.Skill:
    return schemas.Skill(
        key=skill.key,
        name=skill.name,
        description=skill.description,
        version=skill.current_version,
        enabled=skill.enabled,
        is_default=skill.is_default,
        last_updated_at=skill.updated_at.isoformat() if skill.updated_at else None,
    )


def to_data_context_schema(settings: UserSettings) -> schemas.DataContextSettings:
    return schemas.DataContextSettings(
        **{**DEFAULT_DATA_CONTEXT, **(settings.data_context or {})}
    )


def to_interface_schema(settings: UserSettings) -> schemas.InterfaceSettings:
    return schemas.InterfaceSettings(**{**DEFAULT_INTERFACE, **(settings.interface or {})})


async def ensure_default_models(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.user_id == user.id)
        .order_by(ModelConfig.created_at.asc())
    )
    existing_models = list(result.scalars().all())
    existing_by_name = {model.name: model for model in existing_models}
    changed = False

    for item in DEFAULT_MODELS:
        if item["name"] not in existing_by_name:
            model = ModelConfig(user_id=user.id, **item)
            db.add(model)
            existing_models.append(model)
            changed = True

    default_models = [model for model in existing_models if model.is_default]
    if existing_models and not default_models:
        existing_models[0].is_default = True
        changed = True
    elif len(default_models) > 1:
        for model in default_models[1:]:
            model.is_default = False
        changed = True

    if changed:
        await db.commit()


async def list_user_models(db: AsyncSession, user: User) -> list[ModelConfig]:
    await ensure_default_models(db, user)
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.user_id == user.id)
        .order_by(ModelConfig.is_default.desc(), ModelConfig.created_at.asc())
    )
    return list(result.scalars().all())


async def get_user_model(db: AsyncSession, user: User, model_id: str) -> ModelConfig:
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_id,
            ModelConfig.user_id == user.id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


async def ensure_user_settings(db: AsyncSession, user: User) -> UserSettings:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    settings = result.scalar_one_or_none()
    if settings is not None:
        return settings

    settings = UserSettings(
        user_id=user.id,
        data_context=DEFAULT_DATA_CONTEXT,
        interface=DEFAULT_INTERFACE,
    )
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def user_developer_mode(db: AsyncSession, user: User) -> bool:
    settings = await ensure_user_settings(db, user)
    return to_interface_schema(settings).developer_mode


async def ensure_default_skills(db: AsyncSession) -> None:
    result = await db.execute(select(SkillConfig))
    existing_keys = {item.key for item in result.scalars().all()}
    changed = False

    for item in DEFAULT_SKILLS:
        if item["key"] not in existing_keys:
            db.add(SkillConfig(**item))
            changed = True

    if changed:
        await db.commit()


async def list_skill_configs(db: AsyncSession) -> list[SkillConfig]:
    await ensure_default_skills(db)
    result = await db.execute(select(SkillConfig).order_by(SkillConfig.created_at.asc()))
    return list(result.scalars().all())


async def get_skill_config(db: AsyncSession, skill_key: str) -> SkillConfig:
    await ensure_default_skills(db)
    result = await db.execute(select(SkillConfig).where(SkillConfig.key == skill_key))
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill
