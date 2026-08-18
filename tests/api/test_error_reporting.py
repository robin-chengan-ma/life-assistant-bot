from src.api import error_reporting


def test_report_mobile_error_uses_fixed_safe_context(monkeypatch):
    called = {}

    def notify(feature, telegram_user_id, input_summary, **kwargs):
        called.update(
            feature=feature,
            telegram_user_id=telegram_user_id,
            input_summary=input_summary,
            kwargs=kwargs,
        )
        return 9

    monkeypatch.setattr(error_reporting.webhook, "_notify_robin_of_error", notify)

    result = error_reporting.report_mobile_error(object(), "mobile_login", None)

    assert result == 9
    assert called["telegram_user_id"] is None
    assert called["input_summary"] == "Mobile App 請求發生未預期錯誤"
    assert called["kwargs"]["source_platform"] == "mobile"
    assert called["kwargs"]["affected_user_id"] is None
