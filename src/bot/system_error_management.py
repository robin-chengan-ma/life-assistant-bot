"""FR-19j～FR-19l：Owner 專屬 Telegram 系統錯誤管理選單。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.bot import menu, system_errors
from src.bot.state import ConversationStateStore

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PAGE_SIZE = 10
_MAX_RESOLUTION_LENGTH = 2000


def start_menu(db) -> tuple[str, dict]:
    reports = system_errors.list_error_reports(db)
    pending_count = sum(row.get("resolution") is None for row in reports)
    resolved_count = len(reports) - pending_count
    return (
        f"🚨 系統錯誤管理\n待處理：{pending_count} 筆\n已處理：{resolved_count} 筆",
        {"inline_keyboard": [
            [{"text": f"🔴 待處理錯誤（{pending_count}）", "callback_data": "system_errors:list:pending:0"}],
            [{"text": "✅ 最近已處理", "callback_data": "system_errors:list:resolved:0"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]},
    )


def list_reports(db, status: str, page: int = 0) -> tuple[str, dict]:
    pending = status == "pending"
    reports = [row for row in system_errors.list_error_reports(db) if (row.get("resolution") is None) == pending]
    page = max(0, page)
    start = page * _PAGE_SIZE
    items = reports[start:start + _PAGE_SIZE]
    title = "🔴 待處理錯誤" if pending else "✅ 最近已處理"
    if not items:
        text = f"{title}\n目前沒有紀錄。"
    else:
        lines = [title]
        for row in items:
            lines.append(
                f"#{row['id']} · {_platform_label(row)} · "
                f"{row.get('triggering_feature') or '未知功能'} · {_format_time(row.get('last_occurred_at') or row.get('occurred_at'))}"
            )
        text = "\n".join(lines)
    buttons = [
        [{"text": f"#{row['id']} {_short(system_errors.safe_display_summary(row.get('error_summary')))}", "callback_data": f"system_errors:detail:{row['id']}"}]
        for row in items
    ]
    nav = []
    if page > 0:
        nav.append({"text": "⬅️ 上一頁", "callback_data": f"system_errors:list:{status}:{page - 1}"})
    if start + _PAGE_SIZE < len(reports):
        nav.append({"text": "下一頁 ➡️", "callback_data": f"system_errors:list:{status}:{page + 1}"})
    if nav:
        buttons.append(nav)
    buttons.append([{"text": "🔙 返回錯誤管理", "callback_data": "system_errors:menu"}])
    return text, {"inline_keyboard": buttons}


def detail(db, report_id: int) -> tuple[str, dict]:
    report = db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    if report is None:
        return "找不到這筆錯誤紀錄。", menu.back_to_main_menu_keyboard()
    affected = _affected_names(db, report_id)
    lines = [
        f"🚨 錯誤 #{report_id}",
        f"來源：{_platform_label(report)}",
        f"功能：{report.get('triggering_feature') or '未知功能'}",
        f"最近發生：{_format_time(report.get('last_occurred_at') or report.get('occurred_at'))}",
        f"發生次數：{report.get('occurrence_count', 1)}",
        f"摘要：{system_errors.safe_display_summary(report.get('error_summary'))}",
        f"Owner 通知：{_notification_label(report)}",
        f"受影響使用者：{'、'.join(affected) if affected else '未知'}",
        f"狀態：{'待處理' if report.get('resolution') is None else '已處理'}",
    ]
    buttons = []
    if report.get("resolution") is None:
        buttons.append([{"text": "✅ 標記已處理", "callback_data": f"system_errors:resolve:{report_id}"}])
    else:
        lines.extend([
            f"處理說明：{report['resolution']}",
            f"處理時間：{_format_time(report.get('resolved_at'))}",
        ])
    buttons.append([{"text": "🔙 返回錯誤管理", "callback_data": "system_errors:menu"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def start_resolution(db, state_store: ConversationStateStore, telegram_user_id: int, report_id: int):
    report = db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    if report is None:
        return "找不到這筆錯誤紀錄。", menu.back_to_main_menu_keyboard()
    if report.get("resolution") is not None:
        return "這筆錯誤已經處理。", menu.back_to_main_menu_keyboard()
    state_store.set(
        telegram_user_id,
        {"flow": "system_error_resolution", "report_id": report_id},
        feature="system_errors",
        is_draft=True,
    )
    return f"請輸入錯誤 #{report_id} 的處理說明（最多 {_MAX_RESOLUTION_LENGTH} 字）：", None


def handle_resolution_text(state_store: ConversationStateStore, telegram_user_id: int, text: str):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") not in {"system_error_resolution", "system_error_resolution_confirm"}:
        return "處理草稿已逾時，請重新進入系統錯誤管理。", menu.back_to_main_menu_keyboard()
    resolution = text.strip()
    if not resolution:
        return "處理說明不能為空，請重新輸入。", None
    if len(resolution) > _MAX_RESOLUTION_LENGTH:
        return f"處理說明不可超過 {_MAX_RESOLUTION_LENGTH} 字，請重新輸入。", None
    state.update({"flow": "system_error_resolution_confirm", "resolution": resolution})
    state_store.set(telegram_user_id, state, feature="system_errors", is_draft=True)
    return (
        f"錯誤 #{state['report_id']}\n處理說明：{resolution}\n\n確定結案嗎？",
        {"inline_keyboard": [
            [{"text": "✅ 確認結案", "callback_data": "system_errors:confirm"}],
            [{"text": "✏️ 重新輸入", "callback_data": "system_errors:edit"}],
            [{"text": "❌ 取消", "callback_data": "system_errors:cancel"}],
        ]},
    )


def confirm(db, state_store: ConversationStateStore, telegram_user_id: int, owner_user_id: int):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "system_error_resolution_confirm":
        return start_menu(db)
    updated = system_errors.update_resolution(db, state["report_id"], state["resolution"], owner_user_id)
    state_store.clear(telegram_user_id)
    if not updated:
        return "這筆錯誤已經處理，沒有重複寫入。", menu.back_to_main_menu_keyboard()
    return f"錯誤 #{state['report_id']} 已結案。", menu.back_to_main_menu_keyboard()


def edit(state_store: ConversationStateStore, telegram_user_id: int):
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "system_error_resolution_confirm":
        return "處理草稿已逾時。", menu.back_to_main_menu_keyboard()
    state.update({"flow": "system_error_resolution"})
    state.pop("resolution", None)
    state_store.set(telegram_user_id, state, feature="system_errors", is_draft=True)
    return "請重新輸入處理說明：", None


def cancel(state_store: ConversationStateStore, telegram_user_id: int):
    state_store.clear(telegram_user_id)
    return "已取消結案，未修改錯誤紀錄。", menu.back_to_main_menu_keyboard()


def _affected_names(db, report_id: int) -> list[str]:
    user_ids = {
        row["user_id"] for row in db.select("system_error_affected_users")
        if row.get("system_error_report_id") == report_id
    }
    return [row.get("family_title") or row.get("role") or f"使用者 {row['id']}" for row in db.select("users") if row["id"] in user_ids]


def _platform_label(report: dict) -> str:
    return "Mobile App" if report.get("source_platform") == "mobile" else "Telegram"


def _notification_label(report: dict) -> str:
    if report.get("owner_notification_status") == "undelivered":
        return "未送達"
    if report.get("owner_notification_method") == "email":
        return "Email 備援已送達"
    if report.get("owner_notification_method") == "telegram":
        return "Telegram 已送達"
    return "待送達"


def _format_time(value) -> str:
    if value is None:
        return "未知"
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=_TAIWAN_TZ)
    return value.astimezone(_TAIWAN_TZ).strftime("%Y-%m-%d %H:%M")


def _short(value, maximum: int = 40) -> str:
    text = str(value or "無摘要").replace("\n", " ")
    return text if len(text) <= maximum else text[:maximum - 1] + "…"
