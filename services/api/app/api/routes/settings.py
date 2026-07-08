from fastapi import APIRouter, HTTPException

from app import schemas
from app.services import mock_store

router = APIRouter()


@router.put("/profile", response_model=schemas.User)
async def update_profile(input_data: schemas.ProfileUpdate) -> schemas.User:
    mock_store.user.nickname = input_data.nickname
    mock_store.user.email = input_data.email
    mock_store.user.avatar_url = input_data.avatar_url
    return mock_store.user


@router.get("/data-context", response_model=schemas.DataContextSettings)
async def get_data_context_settings() -> schemas.DataContextSettings:
    return mock_store.data_context_settings


@router.put("/data-context", response_model=schemas.DataContextSettings)
async def update_data_context_settings(
    input_data: schemas.DataContextSettings,
) -> schemas.DataContextSettings:
    mock_store.data_context_settings = input_data
    return mock_store.data_context_settings


@router.post("/models", response_model=schemas.ModelConfig)
async def add_model(input_data: dict) -> schemas.ModelConfig:
    model = schemas.ModelConfig(
        base_url=input_data.get("baseUrl") or input_data.get("base_url"),
        id=mock_store.new_id("model"),
        is_available=True,
        name=input_data.get("name", "Custom model"),
        provider=input_data.get("provider", "custom"),
        is_default=False,
        masked_api_key="sk-****" if input_data.get("apiKey") or input_data.get("api_key") else None,
    )
    mock_store.models.insert(0, model)
    return model


@router.put("/models/{model_id}", response_model=schemas.ModelConfig)
async def update_model(model_id: str, input_data: dict) -> schemas.ModelConfig:
    existing = next((item for item in mock_store.models if item.id == model_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Model not found")
    update_data = {
        "base_url": input_data.get("baseUrl", input_data.get("base_url", existing.base_url)),
        "name": input_data.get("name", existing.name),
        "provider": input_data.get("provider", existing.provider),
        "masked_api_key": "sk-****"
        if input_data.get("apiKey") or input_data.get("api_key")
        else existing.masked_api_key,
    }
    updated = existing.model_copy(update=update_data)
    mock_store.models[:] = [updated if item.id == model_id else item for item in mock_store.models]
    return updated


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(model_id: str) -> None:
    mock_store.models[:] = [item for item in mock_store.models if item.id != model_id]
    return None


@router.post("/models/default", response_model=list[schemas.ModelConfig])
async def set_default_model(payload: dict[str, str]) -> list[schemas.ModelConfig]:
    model_id = payload.get("modelId") or payload.get("model_id")
    mock_store.models[:] = [
        item.model_copy(update={"is_default": item.id == model_id}) for item in mock_store.models
    ]
    return mock_store.models


@router.post("/models/{model_id}/test", response_model=schemas.ModelConfig)
async def test_model_connection(model_id: str) -> schemas.ModelConfig:
    model = next((item for item in mock_store.models if item.id == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    updated = model.model_copy(update={"is_available": True})
    mock_store.models[:] = [updated if item.id == model_id else item for item in mock_store.models]
    return updated


@router.post("/skills/default", response_model=list[schemas.Skill])
async def set_default_skill(payload: dict[str, str]) -> list[schemas.Skill]:
    skill_key = payload.get("skillKey") or payload.get("skill_key")
    mock_store.skills[:] = [
        item.model_copy(update={"is_default": item.key == skill_key}) for item in mock_store.skills
    ]
    return mock_store.skills


@router.post("/skills/{skill_key}/toggle", response_model=list[schemas.Skill])
async def toggle_skill_enabled(skill_key: str) -> list[schemas.Skill]:
    mock_store.skills[:] = [
        item.model_copy(update={"enabled": not item.enabled}) if item.key == skill_key else item
        for item in mock_store.skills
    ]
    return mock_store.skills


@router.post("/skills/{skill_key}/version", response_model=list[schemas.Skill])
async def update_skill_version(skill_key: str, payload: dict[str, str]) -> list[schemas.Skill]:
    direction = payload.get("direction", "upgrade")
    mock_store.skills[:] = [
        item.model_copy(update={"version": "0.1.1" if direction == "upgrade" else "0.1.0"})
        if item.key == skill_key
        else item
        for item in mock_store.skills
    ]
    return mock_store.skills
