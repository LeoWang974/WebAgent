import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.settings import is_runtime_adapter_model
from app.models import ModelConfig
from app.services.model_runtime_config import ADAPTER_MODEL_ALIASES

MODEL_CONFIG_DIRECTIVE_RE = re.compile(
    r"(?:~?/\.hermes/config\.yaml|model:\s*)",
    re.IGNORECASE,
)
PLACEHOLDER_API_KEYS = {"sk-xxx", "sk-test", "sk-smoke", "xxx", "your-api-key"}


def parse_model_config_directive(content: str) -> dict[str, str] | None:
    if not MODEL_CONFIG_DIRECTIVE_RE.search(content):
        return None

    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower().replace("-", "_")
        if normalized_key not in {"default", "provider", "base_url", "api_key"}:
            continue
        cleaned_value = value.strip().strip("'\"")
        if cleaned_value:
            values[normalized_key] = cleaned_value

    required = {"default", "base_url", "api_key"}
    if not required.issubset(values):
        return None
    if values["api_key"].strip().lower() in PLACEHOLDER_API_KEYS:
        raise HTTPException(
            status_code=400,
            detail="API key is a placeholder. Please provide a valid key before saving.",
        )
    values.setdefault("provider", "custom")
    return values


async def apply_model_config_directive(
    db: AsyncSession,
    current_user,
    model_id: str | None,
    values: dict[str, str],
) -> ModelConfig:
    model: ModelConfig | None = None
    if model_id and model_id not in ADAPTER_MODEL_ALIASES:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.id == model_id,
                ModelConfig.user_id == current_user.id,
            )
        )
        model = result.scalar_one_or_none()
        if model is not None and is_runtime_adapter_model(model):
            model = None

    if model is None:
        result = await db.execute(
            select(ModelConfig)
            .where(
                ModelConfig.user_id == current_user.id,
                ModelConfig.is_default.is_(True),
            )
            .order_by(ModelConfig.is_default.desc(), ModelConfig.updated_at.desc())
        )
        model = next(
            (item for item in result.scalars().all() if not is_runtime_adapter_model(item)),
            None,
        )

    if model is None:
        model = ModelConfig(
            user_id=current_user.id,
            name=values["default"],
            provider="custom",
            is_default=True,
            is_available=True,
        )
        db.add(model)

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.id != model.id,
        )
    )
    for item in result.scalars().all():
        item.is_default = False

    model.name = values["default"]
    model.provider = values.get("provider", "custom")
    model.base_url = values["base_url"]
    model.encrypted_api_key = values["api_key"]
    model.is_default = True
    model.is_available = True

    await db.flush()
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == current_user.id,
            ModelConfig.is_default.is_(True),
        )
    )
    default_models = result.scalars().all()
    if len(default_models) != 1 or default_models[0].id != model.id:
        raise RuntimeError("Model configuration directive must preserve one default model.")

    await db.commit()
    await db.refresh(model)
    return model
