import pytest
from fastapi import HTTPException

from app.services.model_config_directive import parse_model_config_directive
from app.services.session_message_service import get_explicit_skill_key


def test_get_explicit_skill_key_does_not_parse_user_prompt_markers():
    assert get_explicit_skill_key(None) is None


def test_get_explicit_skill_key_respects_explicit_value():
    assert get_explicit_skill_key("deep_research") == "deep_research"


def test_parse_model_config_directive_supports_hermes_yaml_block():
    values = parse_model_config_directive(
        """
        Update the active model based on this config:
        t ~/.hermes/config.yaml
        model:
          default: bailian/deepseek-v4-pro
          provider: custom
          base_url: https://tokenhub.sensetime.com/v1
          api_key: sk-valid-local-test-key
        """
    )

    assert values == {
        "default": "bailian/deepseek-v4-pro",
        "provider": "custom",
        "base_url": "https://tokenhub.sensetime.com/v1",
        "api_key": "sk-valid-local-test-key",
    }


def test_parse_model_config_directive_ignores_incomplete_block():
    assert parse_model_config_directive("model:\n  default: deepseek-chat") is None


def test_parse_model_config_directive_rejects_placeholder_api_key():
    with pytest.raises(HTTPException):
        parse_model_config_directive(
            """
            model:
              default: bailian/deepseek-v4-pro
              provider: custom
              base_url: https://tokenhub.sensetime.com/v1
              api_key: sk-xxx
            """
        )
