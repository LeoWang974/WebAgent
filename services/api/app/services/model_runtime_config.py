from dataclasses import dataclass
from os import environ

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AgentRun, ModelConfig, User

ADAPTER_MODEL_ALIASES = {"hermes", "openclaw", "sensenova", "model_hermes", "model_openclaw"}

OPENAI_COMPATIBLE_PROVIDERS = {
    "custom",
    "deepseek",
    "openai",
    "openai_compatible",
    "sensenova",
}


@dataclass(frozen=True)
class ModelRuntimeConfig:
    model_config_id: str | None
    provider: str
    model_name: str
    base_url: str | None
    api_key: str | None

    def snapshot(self) -> dict[str, str | None]:
        return {
            "model_config_id": self.model_config_id,
            "model_provider": self.provider,
            "model_name": self.model_name,
            "model_base_url": self.base_url,
            "model_api_key_snapshot": self.api_key,
        }

    def env_values(self) -> dict[str, str | None]:
        values: dict[str, str | None] = {
            "SERPER_API_KEY": environ.get("SERPER_API_KEY"),
        }
        provider = self.provider.lower()
        if provider == "sensenova":
            values.update(
                {
                    "SN_API_KEY": self.api_key,
                    "SN_BASE_URL": self.base_url,
                    "SN_CHAT_API_KEY": self.api_key,
                    "SN_TEXT_API_KEY": self.api_key,
                    "SENSENOVA_API_KEY": self.api_key,
                    "SENSENOVA_BASE_URL": self.base_url,
                    "OPENAI_API_KEY": self.api_key,
                    "OPENAI_BASE_URL": self.base_url,
                }
            )
        elif provider in OPENAI_COMPATIBLE_PROVIDERS:
            values.update(
                {
                    "SN_API_KEY": self.api_key,
                    "SN_BASE_URL": self.base_url,
                    "SN_CHAT_API_KEY": self.api_key,
                    "SN_TEXT_API_KEY": self.api_key,
                    "OPENAI_API_KEY": self.api_key,
                    "OPENAI_BASE_URL": self.base_url,
                }
            )
        elif provider == "gemini":
            values.update(
                {
                    "GEMINI_API_KEY": self.api_key,
                    "GOOGLE_API_KEY": self.api_key,
                    "GEMINI_BASE_URL": self.base_url,
                }
            )
        else:
            values.update(
                {
                    "OPENAI_API_KEY": self.api_key,
                    "OPENAI_BASE_URL": self.base_url,
                }
            )
        return values

    def hermes_config_yaml(self) -> str:
        provider = self.provider.lower()
        hermes_provider = provider if provider == "gemini" else "custom"
        lines = [
            "model:",
            f'  default: "{_yaml_scalar(self.model_name)}"',
            f'  provider: "{_yaml_scalar(hermes_provider)}"',
        ]
        if self.base_url:
            lines.append(f'  base_url: "{_yaml_scalar(self.base_url)}"')
        lines.append("")
        return "\n".join(lines)

    def supports_openai_chat_completions(self) -> bool:
        return bool(self.api_key and self.base_url and self.provider.lower() != "gemini")


def _yaml_scalar(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_provider(provider: str | None) -> str:
    normalized = (provider or "sensenova").strip().lower()
    if normalized in {"openai-compatible", "openai compatible"}:
        return "openai_compatible"
    return normalized


def _default_base_url(provider: str) -> str | None:
    if provider == "sensenova":
        return settings.sensenova_base_url or environ.get("SENSENOVA_BASE_URL")
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "deepseek":
        return "https://api.deepseek.com/v1"
    return None


def _default_api_key(provider: str) -> str | None:
    if provider == "sensenova":
        return settings.sensenova_api_key or environ.get("SENSENOVA_API_KEY")
    if provider == "openai":
        return environ.get("OPENAI_API_KEY")
    if provider == "deepseek":
        return environ.get("DEEPSEEK_API_KEY")
    if provider == "gemini":
        return environ.get("GEMINI_API_KEY") or environ.get("GOOGLE_API_KEY")
    return None


def default_model_runtime_config(model_config_id: str | None = None) -> ModelRuntimeConfig:
    provider = "sensenova"
    return ModelRuntimeConfig(
        model_config_id=model_config_id,
        provider=provider,
        model_name=settings.sensenova_default_model,
        base_url=_default_base_url(provider),
        api_key=_default_api_key(provider),
    )


def model_runtime_config_from_model(model: ModelConfig) -> ModelRuntimeConfig:
    provider = _normalize_provider(model.provider)
    name = (model.name or "").strip()
    base_url = (model.base_url or "").lower()
    has_explicit_model_runtime = bool(model.encrypted_api_key and model.base_url)
    is_runtime_selector = not has_explicit_model_runtime and (
        "hermes" in name.lower()
        or "openclaw" in name.lower()
        or "8642" in base_url
        or "18789" in base_url
    )
    if is_runtime_selector:
        return default_model_runtime_config(model.id)
    model_name = (
        settings.sensenova_default_model
        if provider == "sensenova" and name.lower() in {"sensenova", "sensenova default model"}
        else name or settings.sensenova_default_model
    )
    return ModelRuntimeConfig(
        model_config_id=model.id,
        provider=provider,
        model_name=model_name,
        base_url=model.base_url or _default_base_url(provider),
        api_key=model.encrypted_api_key or _default_api_key(provider),
    )


def model_runtime_config_from_run(run: AgentRun) -> ModelRuntimeConfig:
    if not run.model_provider and not run.model_name and not run.model_api_key_snapshot:
        return default_model_runtime_config()
    provider = _normalize_provider(run.model_provider)
    return ModelRuntimeConfig(
        model_config_id=run.model_config_id,
        provider=provider,
        model_name=run.model_name or settings.sensenova_default_model,
        base_url=run.model_base_url or _default_base_url(provider),
        api_key=run.model_api_key_snapshot or _default_api_key(provider),
    )


class ModelRuntimeConfigBuilder:
    async def build_for_user(
        self,
        db: AsyncSession,
        user: User,
        model_id: str | None = None,
    ) -> ModelRuntimeConfig:
        if model_id in ADAPTER_MODEL_ALIASES:
            return default_model_runtime_config()

        model = await self._load_user_model(db, user, model_id)
        if model is None:
            return default_model_runtime_config()
        return model_runtime_config_from_model(model)

    def build_for_run(self, run: AgentRun) -> ModelRuntimeConfig:
        return model_runtime_config_from_run(run)

    async def _load_user_model(
        self,
        db: AsyncSession,
        user: User,
        model_id: str | None,
    ) -> ModelConfig | None:
        if model_id:
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

        result = await db.execute(
            select(ModelConfig)
            .where(ModelConfig.user_id == user.id, ModelConfig.is_default.is_(True))
            .order_by(ModelConfig.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


model_runtime_config_builder = ModelRuntimeConfigBuilder()
