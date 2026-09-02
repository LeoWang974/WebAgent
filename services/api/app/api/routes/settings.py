# File purpose: Defines FastAPI endpoints for the settings API surface.
# Main declarations: get_input_value retrieves input value; get_model_name_input retrieves model
# name input; to_user_schema converts user schema; update_profile updates profile; update_password
# updates password; get_data_context_settings retrieves data context settings;
# update_data_context_settings updates data context settings; get_interface_settings retrieves
# interface settings; update_interface_settings updates interface settings; add_model handles add
# model; update_model updates model; delete_model deletes model; set_default_model handles set
# default model; test_model_connection verifies model connection; set_default_skill handles set
# default skill; toggle_skill_enabled handles toggle skill enabled; update_skill_version updates
# skill version.

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app import schemas
from app.api.dependencies import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AgentRun, ModelConfig, SkillVersion, User
from app.schemas.model import ModelProvider
from app.services.model_secret_encryption import encrypt_model_secret
from app.services.persistence import (
    get_user_by_username,
    normalize_email,
    normalize_username,
)
from app.services.settings_service import (
    check_runtime_model,
    ensure_default_models,
    ensure_user_settings,
    get_skill_config,
    get_user_model,
    list_skill_configs,
    list_user_models,
    to_data_context_schema,
    to_interface_schema,
    to_model_schema,
    to_skill_schema,
)

router = APIRouter()
MODEL_PROVIDER_ADAPTER = TypeAdapter(ModelProvider)

def get_input_value(input_data: dict[str, Any], camel_key: str, snake_key: str, default=None):
    if camel_key in input_data:
        return input_data[camel_key]
    if snake_key in input_data:
        return input_data[snake_key]
    return default


def get_model_name_input(input_data: dict[str, Any], default: str) -> str:
    value = (
        get_input_value(input_data, "modelName", "model_name")
        or input_data.get("model")
        or input_data.get("name")
        or default
    )
    return str(value).strip() or default


def get_model_provider_input(input_data: dict[str, Any], default: str) -> str:
    raw_value = input_data.get("provider", default)
    normalized = str(raw_value or default).strip().lower()
    if normalized in {"openai-compatible", "openai compatible"}:
        normalized = "openai_compatible"
    try:
        return MODEL_PROVIDER_ADAPTER.validate_python(normalized)
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid model provider. Supported providers: sensenova, deepseek, "
                "openai, openai_compatible, custom."
            ),
        ) from error


def to_user_schema(user: User) -> schemas.User:
    return schemas.User(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        username=user.username,
        avatar_url=user.avatar_url,
        role=user.role,
    )


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


@router.get("/interface", response_model=schemas.InterfaceSettings)
async def get_interface_settings(
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.InterfaceSettings:
    settings = await ensure_user_settings(db, current_user)
    return to_interface_schema(settings)


@router.put("/interface", response_model=schemas.InterfaceSettings)
async def update_interface_settings(
    input_data: schemas.InterfaceSettings,
    db: DbSession,
    current_user: CurrentUser,
) -> schemas.InterfaceSettings:
    settings = await ensure_user_settings(db, current_user)
    settings.interface = input_data.model_dump()
    await db.commit()
    await db.refresh(settings)
    return to_interface_schema(settings)


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
        encrypted_api_key=encrypt_model_secret(api_key),
        is_available=True,
        name=get_model_name_input(input_data, "Custom model"),
        provider=get_model_provider_input(input_data, "custom"),
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
    model.name = get_model_name_input(input_data, model.name)
    model.provider = get_model_provider_input(input_data, model.provider)
    model.base_url = get_input_value(input_data, "baseUrl", "base_url", model.base_url)
    api_key = get_input_value(input_data, "apiKey", "api_key")
    if api_key:
        model.encrypted_api_key = encrypt_model_secret(api_key)
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
    await db.execute(
        update(AgentRun)
        .where(AgentRun.model_config_id == model.id)
        .values(model_config_id=None)
    )
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
    runtime_status = await check_runtime_model(db, current_user, model)
    model.is_available = bool(runtime_status.get("ok"))
    await db.commit()
    await db.refresh(model)
    return to_model_schema(model, runtime_status=runtime_status)


@router.post("/skills/default", response_model=list[schemas.Skill])
async def set_default_skill(
    payload: dict[str, str],
    db: DbSession,
    _current_user: CurrentUser,
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
    _current_user: CurrentUser,
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
    _current_user: CurrentUser,
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
