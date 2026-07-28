from app.core.config import settings
from app.models import ModelConfig
from app.services.model_runtime_config import model_runtime_config_from_model


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

    assert config.snapshot() == {
        "model_config_id": "model-custom",
        "model_provider": "deepseek",
        "model_name": "deepseek-chat",
        "model_base_url": "https://api.deepseek.com/v1",
        "model_api_key_snapshot": "user-key",
    }
    assert config.env_values()["OPENAI_API_KEY"] == "user-key"
    assert config.env_values()["OPENAI_BASE_URL"] == "https://api.deepseek.com/v1"
