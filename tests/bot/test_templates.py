from src.bot import templates


def test_appendix_a_text_mentions_binding_success_and_app_scope():
    assert "綁定成功" in templates.APPENDIX_A_TEXT
    assert "App" in templates.APPENDIX_A_TEXT
