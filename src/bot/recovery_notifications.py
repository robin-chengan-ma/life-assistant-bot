"""FR-20：Owner 選擇事故與收件人後，二次確認康復通知。"""

import logging
from datetime import datetime, timezone

from src.bot import menu
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

RECOVERY_TEXT = "🎉 主任，我已經完全康復了！剛剛的問題已經修好，現在可以正常為大家服務囉！"


def _rows(db: CloudSQLClient, report_id: int, notification_type: str) -> list[dict]:
    return db.select(
        "system_error_notification_recipients",
        where="system_error_report_id = %s AND notification_type = %s",
        params=(report_id, notification_type),
    )


def _eligible_users(db: CloudSQLClient, report_id: int) -> list[dict]:
    incident_sent = {row["user_id"] for row in _rows(db, report_id, "incident") if row["delivery_status"] == "sent"}
    recovery_sent = {row["user_id"] for row in _rows(db, report_id, "recovery") if row["delivery_status"] == "sent"}
    candidates = incident_sent - recovery_sent
    users = db.select("users")
    return [row for row in users if row.get("id") in candidates and row.get("telegram_user_id") is not None]


def start_menu(db: CloudSQLClient) -> tuple[str, dict]:
    reports = [
        row for row in db.select("system_error_reports")
        if row.get("recovery_status", "pending") in {"pending", "partial"} and _eligible_users(db, row["id"])
    ]
    reports.sort(key=lambda row: str(row.get("occurred_at", "")), reverse=True)
    if not reports:
        return "目前沒有尚待發送康復通知的事故。", menu.back_to_main_menu_keyboard()
    buttons = []
    lines = ["請先選擇要處理的事故："]
    for report in reports:
        label = f"#{report['id']} {report.get('triggering_feature') or '未知功能'}"
        lines.append(f"• {label}：{report.get('error_summary', '無摘要')}")
        buttons.append([{"text": label, "callback_data": f"recovery:incident:{report['id']}"}])
    buttons.append([{"text": "🔙 返回主選單", "callback_data": "menu:main"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def _selection_reply(db: CloudSQLClient, state: dict) -> tuple[str, dict]:
    report_id = state["report_id"]
    selected = set(state["selected_user_ids"])
    users = _eligible_users(db, report_id)
    lines = [f"事故 #{report_id}：請勾選要收到康復通知的家人："]
    buttons = []
    for user in users:
        name = user.get("role") or f"使用者 {user['id']}"
        checked = user["id"] in selected
        lines.append(f"{'✅' if checked else '⬜'} {name}")
        buttons.append([{"text": f"{'✅' if checked else '⬜'} {name}", "callback_data": f"recovery:toggle:{user['id']}"}])
    buttons.append([{"text": "繼續預覽", "callback_data": "recovery:preview"}])
    buttons.append([{"text": "❌ 取消", "callback_data": "recovery:cancel"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def select_incident(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, report_id: int):
    users = _eligible_users(db, report_id)
    if not users:
        return start_menu(db)
    state = {"flow": "recovery_select", "report_id": report_id, "selected_user_ids": [row["id"] for row in users]}
    state_store.set(telegram_user_id, state)
    return _selection_reply(db, state)


def toggle(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "recovery_select":
        return start_menu(db)
    eligible = {row["id"] for row in _eligible_users(db, state["report_id"])}
    if user_id not in eligible:
        return _selection_reply(db, state)
    selected = set(state["selected_user_ids"])
    selected.symmetric_difference_update({user_id})
    state["selected_user_ids"] = sorted(selected)
    state_store.set(telegram_user_id, state)
    return _selection_reply(db, state)


def preview(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "recovery_select":
        return start_menu(db)
    if not state["selected_user_ids"]:
        text, keyboard = _selection_reply(db, state)
        return "至少選擇一位收件人。\n\n" + text, keyboard
    users = {row["id"]: row for row in _eligible_users(db, state["report_id"])}
    names = [users[user_id].get("role") or f"使用者 {user_id}" for user_id in state["selected_user_ids"] if user_id in users]
    state["flow"] = "recovery_confirm"
    state_store.set(telegram_user_id, state)
    text = f"將發送給：{'、'.join(names)}\n\n通知內容：\n{RECOVERY_TEXT}\n\n確定發送嗎？"
    keyboard = {"inline_keyboard": [
        [{"text": "✅ 確認發送", "callback_data": "recovery:confirm"}],
        [{"text": "❌ 取消", "callback_data": "recovery:cancel"}],
    ]}
    return text, keyboard


def confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, telegram_client):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "recovery_confirm":
        return start_menu(db)
    report_id = state["report_id"]
    eligible = {row["id"]: row for row in _eligible_users(db, report_id)}
    selected = [user_id for user_id in state["selected_user_ids"] if user_id in eligible]
    success = 0
    failed = 0
    for user_id in selected:
        user = eligible[user_id]
        status = "sent"
        notified_at = datetime.now(timezone.utc)
        try:
            telegram_client.send_text(chat_id=user["telegram_user_id"], text=RECOVERY_TEXT)
            success += 1
        except Exception:
            status = "failed"
            notified_at = None
            failed += 1
            _logger.exception("康復通知發送給 user_id=%s 失敗", user_id)
        db.insert("system_error_notification_recipients", {
            "system_error_report_id": report_id, "user_id": user_id, "notification_type": "recovery",
            "delivery_status": status, "notified_at": notified_at,
        })
    db.update(
        "system_error_reports",
        {"recovery_status": "sent" if failed == 0 and success > 0 else "partial",
         "recovery_sent_at": datetime.now(timezone.utc) if success else None},
        where="id = %s", params=(report_id,),
    )
    state_store.clear(telegram_user_id)
    return f"康復通知已處理：{success} 位成功、{failed} 位失敗。", menu.back_to_main_menu_keyboard()


def cancel(state_store: ConversationStateStore, telegram_user_id: int):
    state_store.clear(telegram_user_id)
    return "已取消發送康復通知。", menu.back_to_main_menu_keyboard()

