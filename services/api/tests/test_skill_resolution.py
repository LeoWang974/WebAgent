from app.services.session_message_service import get_explicit_skill_key


def test_get_explicit_skill_key_does_not_detect_report_html_v2_from_prompt():
    assert get_explicit_skill_key(None) is None


def test_get_explicit_skill_key_does_not_detect_plain_html_request():
    assert get_explicit_skill_key(None) is None


def test_get_explicit_skill_key_respects_explicit_skill_key():
    assert get_explicit_skill_key("ppt_generation") == "ppt_generation"
