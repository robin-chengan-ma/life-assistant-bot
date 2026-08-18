"""Owner 康復通知選單與二次確認流程。"""

from src.bot import recovery_notifications, router
from src.bot.state import ConversationStateStore


class _TelegramClient:
    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    def send_text(self, chat_id, text):
        if chat_id in self.fail_for:
            raise RuntimeError("send failed")
        self.sent.append((chat_id, text))


def _seed_incident(fake_db):
    mom_id = fake_db.insert("users", {"telegram_user_id": 2, "role": "媽媽", "is_owner": False})
    dad_id = fake_db.insert("users", {"telegram_user_id": 3, "role": "爸爸", "is_owner": False})
    report_id = fake_db.insert(
        "system_error_reports",
        {"severity": "critical", "triggering_feature": "text", "error_summary": "boom",
         "recovery_status": "pending", "occurred_at": "2026-08-18T10:00:00"},
    )
    for user_id in (mom_id, dad_id):
        fake_db.insert(
            "system_error_notification_recipients",
            {"system_error_report_id": report_id, "user_id": user_id, "notification_type": "incident",
             "delivery_status": "sent", "notified_at": "2026-08-18T10:00:01"},
        )
    return report_id, mom_id, dad_id


def test_start_menu_lists_unrecovered_incident(fake_db):
    report_id, _, _ = _seed_incident(fake_db)

    text, keyboard = recovery_notifications.start_menu(fake_db)

    assert "text" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"recovery:incident:{report_id}"


def test_select_incident_defaults_to_all_successfully_notified_family(fake_db):
    report_id, mom_id, dad_id = _seed_incident(fake_db)
    store = ConversationStateStore()

    text, keyboard = recovery_notifications.select_incident(fake_db, store, 1, report_id)

    assert "媽媽" in text and "爸爸" in text
    assert store.get(1)["selected_user_ids"] == [mom_id, dad_id]
    callbacks = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert f"recovery:toggle:{mom_id}" in callbacks


def test_preview_requires_at_least_one_recipient(fake_db):
    report_id, _, _ = _seed_incident(fake_db)
    store = ConversationStateStore()
    store.set(1, {"flow": "recovery_select", "report_id": report_id, "selected_user_ids": []})

    text, _ = recovery_notifications.preview(fake_db, store, 1)

    assert "至少選擇一位" in text


def test_confirm_sends_only_selected_users_and_records_result(fake_db):
    report_id, mom_id, _ = _seed_incident(fake_db)
    store = ConversationStateStore()
    store.set(1, {"flow": "recovery_confirm", "report_id": report_id, "selected_user_ids": [mom_id]})
    telegram = _TelegramClient()

    text, _ = recovery_notifications.confirm(fake_db, store, 1, telegram)

    assert [chat_id for chat_id, _ in telegram.sent] == [2]
    assert "1 位成功" in text
    recovery_rows = fake_db.select(
        "system_error_notification_recipients",
        where="system_error_report_id = %s AND notification_type = %s",
        params=(report_id, "recovery"),
    )
    assert recovery_rows[0]["user_id"] == mom_id
    assert recovery_rows[0]["delivery_status"] == "sent"
    assert fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)["recovery_status"] == "sent"


def test_confirm_keeps_partial_incident_available_when_send_fails(fake_db):
    report_id, mom_id, dad_id = _seed_incident(fake_db)
    store = ConversationStateStore()
    store.set(1, {"flow": "recovery_confirm", "report_id": report_id, "selected_user_ids": [mom_id, dad_id]})

    text, _ = recovery_notifications.confirm(fake_db, store, 1, _TelegramClient(fail_for={3}))

    assert "1 位失敗" in text
    report = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert report["recovery_status"] == "partial"


def test_router_owner_menu_opens_recovery_incidents(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "1")
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    report_id, _, _ = _seed_incident(fake_db)
    store = ConversationStateStore()

    text, keyboard = router.handle_callback_query(fake_db, store, 1, "menu:recovered")

    assert f"#{report_id}" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"recovery:incident:{report_id}"


def test_router_rejects_forged_recovery_callback_from_non_owner(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": 2, "role": "媽媽", "is_owner": False})

    text, _ = router.handle_callback_query(fake_db, ConversationStateStore(), 2, "recovery:confirm")

    assert text == "無法使用這個功能。"


def test_mobile_incident_uses_affected_user_and_mobile_recovery_text(fake_db):
    affected_id = fake_db.insert(
        "users", {"telegram_user_id": 222, "role": "爸爸", "is_owner": False}
    )
    report_id = fake_db.insert("system_error_reports", {
        "occurred_at": "2026-08-18T01:00:00+00:00", "triggering_feature": "mobile_dashboard",
        "error_summary": "boom", "source_platform": "mobile", "recovery_status": "pending",
    })
    fake_db.insert("system_error_affected_users", {
        "system_error_report_id": report_id, "user_id": affected_id,
    })
    store = ConversationStateStore()

    recovery_notifications.select_incident(fake_db, store, 1, report_id)
    preview, _ = recovery_notifications.preview(fake_db, store, 1)

    assert "爸爸" in preview
    assert "Mobile App 的問題已經修復" in preview
