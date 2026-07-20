from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import ModelConfig, SkillConfig, SkillVersion, User, UserSettings
from app.services.persistence import (
    get_user_by_username,
    normalize_email,
    normalize_username,
)

router = APIRouter()

DEFAULT_DATA_CONTEXT = {
    "auto_summarize_context": True,
    "context_retention_days": 30,
    "max_context_messages": 40,
    "save_conversation_history": True,
    "save_uploaded_files": True,
}

DEFAULT_MODELS = [
    {
        "name": "SenseNova default model",
        "provider": "sensenova",
        "base_url": None,
        "encrypted_api_key": None,
        "is_default": False,
        "is_available": True,
    },
    {
        "name": "OpenClaw Agent",
        "provider": "openai_compatible",
        "base_url": "ws://127.0.0.1:18789",
        "encrypted_api_key": None,
        "is_default": False,
        "is_available": True,
    },
    {
        "name": "Hermes Agent",
        "provider": "openai_compatible",
        "base_url": "http://localhost:8642",
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


def mask_api_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def get_input_value(input_data: dict[str, Any], camel_key: str, snake_key: str, default=None):
    if camel_key in input_data:
        return input_data[camel_key]
    if snake_key in input_data:
        return input_data[snake_key]
    return default


def to_user_schema(user: User) -> schemas.User:
    return schemas.User(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        username=user.username,
        avatar_url=user.avatar_url,
        role=user.role,
    )


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
        masked_api_key=mask_api_key(model.encrypted_api_key),
        runtime_status=runtime_status,
    )


async def test_runtime_model(
    db: AsyncSession,
    current_user: User,
    model: ModelConfig,
) -> dict[str, Any]:
    from app.api.routes.agent_runs import resolve_adapter_for_model

    adapter_key, adapter = await resolve_adapter_for_model(db, current_user, model.id)
    if adapter is None:
        return {
            "adapterKey": adapter_key,
            "ok": False,
            "status": "unavailable",
            "message": "Runtime adapter is unavailable.",
        }

    if not hasattr(adapter, "health_check"):
        return {
            "adapterKey": adapter_key,
            "ok": True,
            "status": "available",
            "message": "Runtime adapter is available; no active health check is implemented.",
        }

    try:
        health = await adapter.health_check()
    except Exception as error:
        return {
            "adapterKey": adapter_key,
            "ok": False,
            "status": "unavailable",
            "message": str(error),
        }

    ok = bool(health.get("ok")) if isinstance(health, dict) else False
    return {
        "adapterKey": adapter_key,
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
    data = {**DEFAULT_DATA_CONTEXT, **(settings.data_context or {})}
    return schemas.DataContextSettings(**data)


async def ensure_default_models(db: AsyncSession, user: User) -> None:
    result = await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id))
    existing_models = list(result.scalars().all())
    if existing_models:
        for model in existing_models:
            if model.name == "OpenClaw Agent" and model.base_url == "http://localhost:8643":
                model.base_url = "ws://127.0.0.1:18789"
        await db.commit()
        return

    for item in DEFAULT_MODELS:
        db.add(ModelConfig(user_id=user.id, **item))
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

    settings = UserSettings(user_id=user.id, data_context=DEFAULT_DATA_CONTEXT, interface={})
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def ensure_default_skills(db: AsyncSession) -> None:
    result = await db.execute(select(SkillConfig))
    existing_keys = {item.key for item in result.scalars().all()}
    changed = False

    for item in DEFAULT_SKILLS:
        if item["key"] in existing_keys:
            continue
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


@router.put("/profile", response_model=schemas.User)
async def update_profile(
    input_data: schemas.ProfileUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.User:
    current_user.nickname = input_data.nickname
    current_user.email = normalize_email(input_data.email)
    username = normalize_username(input_data.username)
    if username and username != current_user.username:
        existing_user = await get_user_by_username(db, username)
        if existing_user is not None and existing_user.id != current_user.id:
            raise HTTPException(status_code=409, detail="Username is already in use")
    current_user.username = username
    current_user.avatar_url = input_data.avatar_url
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email is already in use") from error
    await db.refresh(current_user)
    return to_user_schema(current_user)


@router.put("/profile/password", response_model=schemas.AuthResult | None)
async def update_password(
    input_data: schemas.PasswordUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.AuthResult | None:
    if len(input_data.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

    if not verify_password(input_data.current_password, current_user.hashed_password):
        if current_user.hashed_password != input_data.current_password:
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(input_data.new_password)
    await db.commit()
    await db.refresh(current_user)

    if input_data.relogin:
        return schemas.AuthResult(
            access_token=create_access_token(current_user.id),
            user=to_user_schema(current_user),
        )

    return None


@router.get("/data-context", response_model=schemas.DataContextSettings)
async def get_data_context_settings(
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.DataContextSettings:
    settings = await ensure_user_settings(db, current_user)
    return to_data_context_schema(settings)


@router.put("/data-context", response_model=schemas.DataContextSettings)
async def update_data_context_settings(
    input_data: schemas.DataContextSettings,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.DataContextSettings:
    settings = await ensure_user_settings(db, current_user)
    settings.data_context = input_data.model_dump()
    await db.commit()
    await db.refresh(settings)
    return to_data_context_schema(settings)


@router.post("/models", response_model=schemas.ModelConfig)
async def add_model(
    input_data: dict[str, Any],
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ModelConfig:
    await ensure_default_models(db, current_user)
    api_key = get_input_value(input_data, "apiKey", "api_key")
    model = ModelConfig(
        user_id=current_user.id,
        base_url=get_input_value(input_data, "baseUrl", "base_url"),
        encrypted_api_key=api_key,
        is_available=True,
        name=input_data.get("name", "Custom model"),
        provider=input_data.get("provider", "custom"),
        is_default=False,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return to_model_schema(model)


@router.put("/models/{model_id}", response_model=schemas.ModelConfig)
async def update_model(
    model_id: str,
    input_data: dict[str, Any],
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ModelConfig:
    model = await get_user_model(db, current_user, model_id)
    model.name = input_data.get("name", model.name)
    model.provider = input_data.get("provider", model.provider)
    model.base_url = get_input_value(input_data, "baseUrl", "base_url", model.base_url)
    api_key = get_input_value(input_data, "apiKey", "api_key")
    if api_key:
        model.encrypted_api_key = api_key
    await db.commit()
    await db.refresh(model)
    return to_model_schema(model)


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    model = await get_user_model(db, current_user, model_id)
    was_default = model.is_default
    await db.delete(model)
    await db.commit()

    if was_default:
        models = await list_user_models(db, current_user)
        if models:
            models[0].is_default = True
            await db.commit()
    return None


@router.post("/models/default", response_model=list[schemas.ModelConfig])
async def set_default_model(
    payload: dict[str, str],
    db: DbSession,
    current_user: CurrentUser,
) -> list[schemas.ModelConfig]:
    model_id = payload.get("modelId") or payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
    await get_user_model(db, current_user, model_id)

    models = await list_user_models(db, current_user)
    for model in models:
        model.is_default = model.id == model_id
    await db.commit()
    models = await list_user_models(db, current_user)
    return [to_model_schema(item) for item in models]


@router.post("/models/{model_id}/test", response_model=schemas.ModelConfig)
async def test_model_connection(
    model_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.ModelConfig:
    model = await get_user_model(db, current_user, model_id)
    runtime_status = await test_runtime_model(db, current_user, model)
    model.is_available = bool(runtime_status.get("ok"))
    await db.commit()
    await db.refresh(model)
    return to_model_schema(model, runtime_status=runtime_status)


@router.post("/skills/default", response_model=list[schemas.Skill])
async def set_default_skill(
    payload: dict[str, str],
    db: DbSession,
) -> list[schemas.Skill]:
    skill_key = payload.get("skillKey") or payload.get("skill_key")
    if not skill_key:
        raise HTTPException(status_code=400, detail="skill_key is required")
    await get_skill_config(db, skill_key)

    skills = await list_skill_configs(db)
    for skill in skills:
        skill.is_default = skill.key == skill_key
    await db.commit()
    skills = await list_skill_configs(db)
    return [to_skill_schema(item) for item in skills]


@router.post("/skills/{skill_key}/toggle", response_model=list[schemas.Skill])
async def toggle_skill_enabled(
    skill_key: str,
    db: DbSession,
) -> list[schemas.Skill]:
    skill = await get_skill_config(db, skill_key)
    skill.enabled = not skill.enabled
    await db.commit()
    skills = await list_skill_configs(db)
    return [to_skill_schema(item) for item in skills]


@router.post("/skills/{skill_key}/version", response_model=list[schemas.Skill])
async def update_skill_version(
    skill_key: str,
    payload: dict[str, str],
    db: DbSession,
) -> list[schemas.Skill]:
    skill = await get_skill_config(db, skill_key)
    direction = payload.get("direction", "update")
    skill.current_version = "0.1.1" if direction == "update" else "0.1.0"
    db.add(
        SkillVersion(
            skill_key=skill.key,
            version=skill.current_version,
            changelog=f"{direction} via settings API",
            status="published",
        )
    )
    await db.commit()
    skills = await list_skill_configs(db)
    return [to_skill_schema(item) for item in skills]
