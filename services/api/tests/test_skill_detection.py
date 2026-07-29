import pytest
from fastapi import HTTPException

from app.api.routes.sessions import parse_model_config_directive, resolve_skill_key


def test_resolve_skill_key_requires_explicit_skill_markers():
    assert resolve_skill_key("请使用 sn-deep-research 调研主题乐园", None) == "deep_research"
    assert resolve_skill_key("请使用 sn-da 分析这份表格", None) == "data_analysis"
    assert resolve_skill_key("请使用 sn-ppt-workbench 生成 12 页 PPT", None) == "ppt_generation"
    assert resolve_skill_key("请使用 u1_image 生成图片", None) == "u1_image"
    assert resolve_skill_key("使用 report-html-v2 输出 HTML 文件", None) == "html_generation"


def test_resolve_skill_key_does_not_guess_from_generic_words():
    assert resolve_skill_key("帮我调研主题乐园并输出报告", None) is None
    assert resolve_skill_key("最后生成一份 12 页 PPT 演示文稿", None) is None
    assert resolve_skill_key("你好，请确认 HTML 和 PPT 产物链路测评开始。", None) is None


def test_resolve_skill_key_respects_explicit_value():
    assert resolve_skill_key("普通聊天", "deep_research") == "deep_research"


def test_parse_model_config_directive_supports_hermes_yaml_block():
    values = parse_model_config_directive(
        """
        基于以下格式，调整正在使用的模型
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
