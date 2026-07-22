from app.api.routes.sessions import resolve_skill_key


def test_resolve_skill_key_detects_report_html_v2():
    assert (
        resolve_skill_key(
            "请使用上述生成的《二次元正在改变消费市场》markdown报告。"
            "使用report-html-v2为我输出HTML文件",
            None,
        )
        == "html_generation"
    )


def test_resolve_skill_key_respects_explicit_skill_key():
    assert resolve_skill_key("输出HTML文件", "ppt_generation") == "ppt_generation"
