# File purpose: Verifies test model runtime config behavior and its regression contracts.
# Main declarations: test_runtime_selector_model_uses_default_sensenova_snapshot verifies runtime
# selector model uses default sensenova snapshot;
# test_custom_openai_compatible_model_uses_user_snapshot verifies custom openai compatible model
# uses user snapshot; test_explicit_custom_model_is_not_treated_as_runtime_selector verifies
# explicit custom model is not treated as runtime selector;
# test_adapter_model_alias_does_not_query_database verifies adapter model alias does not query
# database.

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models import ModelConfig
from app.services.model_runtime_config import (
    model_runtime_config_builder,
    model_runtime_config_from_model,
)
from app.services.model_secret_encryption import decrypt_model_secret


def test_runtime_selector_model_uses_default_sensenova_snapshot(monkeypatch):
    monkeypatch.setattr(settings, "sensenova_default_model", "sensenova-6.7-flash-lite")
    monkeypatch.setattr(settings, "sensenova_base_url", "https://token.sensenova.cn/v1")
    monkeypatch.setattr(settings, "sensenova_api_key", "default-key")

    config = model_runtime_config_from_model(
        ModelConfig(
            id="model-hermes",
            user_id="user-1",
            name="Hermes Agent",
            provider="openai_compatible",
            base_url="http://localhost:8642",
            encrypted_api_key=None,
            is_default=True,
            is_available=True,
        )
    )

    assert config.model_config_id == "model-hermes"
    assert config.provider == "sensenova"
    assert config.model_name == "sensenova-6.7-flash-lite"
    assert config.base_url == "https://token.sensenova.cn/v1"
    assert config.api_key == "default-key"


def test_custom_openai_compatible_model_uses_user_snapshot():
    config = model_runtime_config_from_model(
        ModelConfig(
            id="model-custom",
            user_id="user-1",
            name="deepseek-chat",
            provider="deepseek",
            base_url=None,
            encrypted_api_key="user-key",
            is_default=False,
            is_available=True,
        )
    )

    snapshot = config.snapshot()
    assert snapshot["model_config_id"] == "model-custom"
    assert snapshot["model_provider"] == "deepseek"
    assert snapshot["model_name"] == "deepseek-chat"
    assert snapshot["model_base_url"] == "https://api.deepseek.com/v1"
    assert snapshot["model_api_key_snapshot"].startswith("enc:v1:")
    assert decrypt_model_secret(snapshot["model_api_key_snapshot"]) == "user-key"
    assert config.env_values()["OPENAI_API_KEY"] == "user-key"
    assert config.env_values()["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"


@pytest.mark.parametrize(
    ("provider", "name", "expected"),
    [
        ("sensenova", "SenseNova", "sensenova-6.8-flash-lite"),
        ("deepseek", "DeepSeek", "deepseek-chat"),
        ("openai", "GPT-5.5", "gpt-5.5"),
    ],
)
def test_named_models_resolve_to_provider_model_ids(provider, name, expected):
    config = model_runtime_config_from_model(
        ModelConfig(
            id=f"model-{provider}",
            user_id="user-1",
            name=name,
            provider=provider,
            base_url=None,
            encrypted_api_key="user-key",
            is_default=False,
            is_available=True,
        )
    )

    assert config.model_name == expected


def test_explicit_custom_model_is_not_treated_as_runtime_selector():
    config = model_runtime_config_from_model(
        ModelConfig(
            id="model-custom-hermes",
            user_id="user-1",
            name="bailian/deepseek-v4-pro",
            provider="custom",
            base_url="https://tokenhub.sensetime.com/v1",
            encrypted_api_key="user-key",
            is_default=True,
            is_available=True,
        )
    )

    assert config.model_config_id == "model-custom-hermes"
    assert config.provider == "custom"
    assert config.model_name == "bailian/deepseek-v4-pro"
    assert config.base_url == "https://tokenhub.sensetime.com/v1"
    assert config.api_key == "user-key"


@pytest.mark.asyncio
async def test_adapter_model_alias_does_not_query_database(monkeypatch):
    monkeypatch.setattr(settings, "sensenova_default_model", "sensenova-6.7-flash-lite")
    monkeypatch.setattr(settings, "sensenova_base_url", "https://token.sensenova.cn/v1")
    monkeypatch.setattr(settings, "sensenova_api_key", "default-key")

    class ExplodingDb:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("adapter model aliases must not query model_configs")

    config = await model_runtime_config_builder.build_for_user(
        ExplodingDb(),
        SimpleNamespace(id="user-1"),
        "hermes",
    )

    assert config.model_config_id is None
    assert config.provider == "sensenova"
    assert config.api_key == "default-key"
