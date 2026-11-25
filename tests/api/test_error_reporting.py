from src.api import error_reporting


def test_report_mobile_error_uses_fixed_safe_context(monkeypatch):
    called = {}

    def notify(feature, telegram_user_id):
        called.update(feature=feature, telegram_user_id=telegram_user_id)

    monkeypatch.setattr(error_reporting.webhook, "_notify_owner_of_error", notify)

    error_reporting.report_mobile_error(object(), "mobile_login", None)

    assert called["feature"] == "mobile_login"
    assert called["telegram_user_id"] is None


def test_report_mobile_error_swallows_notify_failure(monkeypatch):
    def notify(feature, telegram_user_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(error_reporting.webhook, "_notify_owner_of_error", notify)

    # 不應該往外拋例外。
    error_reporting.report_mobile_error(object(), "mobile_login", 1)
