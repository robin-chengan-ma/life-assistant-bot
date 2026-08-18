from datetime import datetime, timezone

from src.bot import system_error_management
from src.bot.state import ConversationStateStore


def _report(fake_db, **overrides):
    data = {
        "occurred_at": datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc),
        "last_occurred_at": datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc),
        "severity": "general",
        "triggering_feature": "mobile_dashboard",
        "error_summary": "Database unavailable",
        "source_platform": "mobile",
        "occurrence_count": 2,
        "resolution": None,
        "owner_notification_method": "email",
        "owner_notification_status": "sent",
    }
    data.update(overrides)
    return fake_db.insert("system_error_reports", data)


def test_menu_and_detail_show_platform_delivery_and_count(fake_db):
    report_id = _report(fake_db)

    text, keyboard = system_error_management.start_menu(fake_db)
    detail, _ = system_error_management.detail(fake_db, report_id)

    assert "待處理：1 筆" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "system_errors:list:pending:0"
    assert "來源：Mobile App" in detail
    assert "發生次數：2" in detail
    assert "Owner 通知：Email 備援已送達" in detail


def test_resolution_requires_preview_and_second_confirmation(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 1, "is_owner": True, "role": "Robin"})
    report_id = _report(fake_db)
    store = ConversationStateStore()

    system_error_management.start_resolution(fake_db, store, 1, report_id)
    preview, keyboard = system_error_management.handle_resolution_text(store, 1, "重新啟動資料庫連線")

    assert f"錯誤 #{report_id}" in preview
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "system_errors:confirm"
    assert fake_db.select("system_error_reports", fetch_one=True)["resolution"] is None

    reply, _ = system_error_management.confirm(fake_db, store, 1, owner_id)
    row = fake_db.select("system_error_reports", fetch_one=True)
    assert "已結案" in reply
    assert row["resolution"] == "重新啟動資料庫連線"
    assert row["resolved_by_user_id"] == owner_id


def test_resolution_does_not_overwrite_resolved_report(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 1, "is_owner": True})
    report_id = _report(
        fake_db,
        resolution="舊處理方式",
        resolved_by_user_id=owner_id,
        resolved_at=datetime.now(timezone.utc),
    )
    store = ConversationStateStore()

    text, _ = system_error_management.start_resolution(fake_db, store, 1, report_id)

    assert "已經處理" in text
    assert store.get(1) is None
