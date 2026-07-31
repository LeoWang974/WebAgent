from app.services.session_message_service import resolve_skill_key


def test_resolve_skill_key_does_not_detect_report_html_v2_from_prompt():
    assert (
        resolve_skill_key(
            "请使用上述生成的《二次元正在改变消费市场》markdown报告。"
            "使用report-html-v2为我输出HTML文件",
            None,
        )
        is None
    )


def test_resolve_skill_key_does_not_detect_plain_html_request():
    assert resolve_skill_key("输出HTML文件", None) is None


def test_resolve_skill_key_respects_explicit_skill_key():
    assert resolve_skill_key("输出HTML文件", "ppt_generation") == "ppt_generation"
