"""Telegram「重要日子」選單流程（Phase 6 第二批 2b，見 docs/ADR/discuss/robinson.md
2026-08-15「Phase 6 第二批 2b 起子批次分組順序」與「2b 重要日子實作計畫」）。

直接複用既有 `AppImportantDayService`（Mobile App 已在用的同一套驗證與 CRUD 邏輯），
不重寫欄位規則，符合 FR-6h「兩端共用相同欄位、必填、數值範圍、驗證與讀取結果」。

本模組只負責 Telegram 對話流程（選單、多步驟輸入、摘要→二次確認），不含主動推播提醒
（FR-72a 提到的「通用 Telegram 重要日子發送器」留給 2b～2k 順序中的「排程設定」批次）。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from datetime import time as time_cls
from typing import Any

from src.bot import menu
from src.bot.state import ConversationStateStore
from src.services.app_important_days import (
    AppImportantDayService,
    ImportantDayNotFoundError,
    ImportantDayValidationError,
)
from submodules.cloudsql.client import CloudSQLClient

_EXIT_PHRASES = {"沒有了", "結束"}
_SKIP_PHRASES = {"略過", "skip"}

_RECURRENCE_LABELS = {
    "fixed_annual": "每年固定日期",
    "flexible_annual": "每年浮動日期",
    "one_time": "單次事件",
}
_AUDIENCE_LABELS = {"self": "只有自己", "all": "全部家人", "specific": "指定家人"}

_MMDD_PATTERN = re.compile(r"^(?P<month>\d{1,2})-(?P<day>\d{1,2})$")
_DUMMY_YEAR = 2000  # 閏年，容許 2/29；fixed_annual 只取月/日，年份純粹是計算用途不落地。


def _service(db: CloudSQLClient) -> AppImportantDayService:
    return AppImportantDayService(db)


# ---------------------------------------------------------------------------
# 選單／清單
# ---------------------------------------------------------------------------

def start_important_days_menu() -> tuple[str, dict]:
    """主選單按下「📅 重要日子」後的子選單首頁。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "📋 查看清單", "callback_data": "important_days:list"}],
            [{"text": "➕ 新增", "callback_data": "important_days:add"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    return "重要日子，請選擇要進行的操作：", keyboard


def _format_list_item(item: dict[str, Any], index: int) -> str:
    label = _RECURRENCE_LABELS.get(item["recurrence_type"], item["recurrence_type"])
    next_occurrence = item.get("next_occurrence") or "尚未排定"
    audience = _AUDIENCE_LABELS.get(item.get("audience_mode"), item.get("audience_mode"))
    active = "" if item.get("is_active", True) else "（已停用）"
    owner_mark = "" if item.get("can_edit") else "（其他家人建立，僅供檢視）"
    return (
        f"{index}. {item['title']}{active}{owner_mark}\n"
        f"　　類型：{label}／下次日期：{next_occurrence}／通知對象：{audience}"
    )


def handle_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    """FR-6e：查看重要日子清單；只有建立者本人才會拿到編輯／刪除按鈕。"""
    service = _service(db)
    items = service.list_for_user(user_id)
    if not items:
        return "目前還沒有任何重要日子紀錄，可以按「➕ 新增」建立第一筆！", menu.back_to_main_menu_keyboard()

    lines = ["目前的重要日子：", ""]
    buttons = []
    for index, item in enumerate(items, start=1):
        lines.append(_format_list_item(item, index))
        if item.get("can_edit"):
            buttons.append([
                {"text": f"✏️ 編輯 {index}", "callback_data": f"important_days:edit:{item['id']}"},
                {"text": f"🗑 刪除 {index}", "callback_data": f"important_days:delete:{item['id']}"},
            ])
    buttons.append([{"text": "🔙 返回主選單", "callback_data": "menu:main"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


# ---------------------------------------------------------------------------
# 新增／編輯（共用同一組多步驟流程）
# ---------------------------------------------------------------------------

def start_add(state_store: ConversationStateStore, telegram_user_id: int) -> str:
    state_store.set(
        telegram_user_id,
        {"flow": "important_days", "step": "awaiting_title", "mode": "add", "target_id": None, "data": {}},
    )
    return "請輸入重要日子的名稱（例如：媽媽生日）："


def start_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, important_day_id: int) -> str:
    row = db.select(
        "important_days",
        where="id = %s AND owner_user_id = %s",
        params=(important_day_id, user_id),
        fetch_one=True,
    )
    if row is None:
        return "找不到這筆重要日子，可能已經被刪除了。"

    state_store.set(
        telegram_user_id,
        {
            "flow": "important_days",
            "step": "awaiting_title",
            "mode": "edit",
            "target_id": important_day_id,
            "data": {},
            "existing": {"title": row["title"]},
        },
    )
    return f"目前名稱是「{row['title']}」，請輸入新的名稱（不需要改的話請直接重打一次原名稱）："


def start_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, important_day_id: int) -> tuple[str, dict]:
    row = db.select(
        "important_days",
        where="id = %s AND owner_user_id = %s",
        params=(important_day_id, user_id),
        fetch_one=True,
    )
    if row is None:
        return "找不到這筆重要日子，可能已經被刪除了。", menu.back_to_main_menu_keyboard()

    state_store.set(telegram_user_id, {"flow": "important_days_delete_confirm", "target_id": important_day_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"important_days:confirm_delete:{important_day_id}"}],
            [{"text": "❌ 取消", "callback_data": "important_days:list"}],
        ]
    }
    return f"確定要刪除「{row['title']}」嗎？此動作無法復原。", keyboard


def handle_delete_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`important_days_delete_confirm` 這個狀態只接受按鈕操作；使用者改用打字時，
    比照其餘按鈕式流程的保守做法，直接結束流程並導回主選單，不當成未知狀態拋例外。"""
    state_store.clear(telegram_user_id)
    return "刪除確認請用上面的按鈕操作喔，這次先幫你取消了。", menu.back_to_main_menu_keyboard()


def handle_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, important_day_id: int) -> tuple[str, dict]:
    state_store.clear(telegram_user_id)
    service = _service(db)
    try:
        service.delete(important_day_id, user_id)
    except ImportantDayNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return "已刪除該筆重要日子。", menu.back_to_main_menu_keyboard()


def _family_candidates(db: CloudSQLClient) -> list[dict[str, Any]]:
    users = db.select("users")
    return [
        {"id": u["id"], "display_name": u.get("nickname") or u.get("family_title") or u["role"]}
        for u in users
    ]


def _parse_mmdd(text: str, label: str) -> date:
    match = _MMDD_PATTERN.match(text.strip())
    if not match:
        raise ImportantDayValidationError(f"{label}格式不正確，請用「月-日」，例如 8-15")
    month, day = int(match.group("month")), int(match.group("day"))
    try:
        return date(_DUMMY_YEAR, month, day)
    except ValueError as exc:
        raise ImportantDayValidationError(f"{label}不是有效的日期") from exc


def _parse_full_date(text: str, label: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise ImportantDayValidationError(f"{label}格式不正確，請用「YYYY-MM-DD」，例如 2026-09-20") from exc


def _parse_hhmm(text: str) -> time_cls:
    try:
        # ruff（DTZ007）誤判：這裡只是借用 strptime 解析「HH:MM」格式，最後只取 .time()
        # 丟棄日期部分，回傳的是不含時區概念的單純鐘面時刻（例如「每天 19:30 提醒」），
        # 不是某個時區下的具體時間點，加時區資訊沒有意義。
        return datetime.strptime(text.strip(), "%H:%M").time()  # noqa: DTZ007
    except ValueError as exc:
        raise ImportantDayValidationError("時間格式不正確，請用「HH:MM」，例如 19:30") from exc


def _summary_text(data: dict[str, Any]) -> str:
    recurrence_label = _RECURRENCE_LABELS.get(data["recurrence_type"], data["recurrence_type"])
    if data["recurrence_type"] == "fixed_annual":
        date_line = f"每年 {data['_display_start']} 至 {data['_display_end']}"
    elif data["recurrence_type"] == "one_time":
        date_line = f"{data['_display_start']} 至 {data['_display_end']}"
    else:
        date_line = f"今年日期：{data.get('_display_start') or '尚未指定'}"
    time_line = "全天" if data["is_all_day"] else data.get("event_time", "未指定")
    audience_label = _AUDIENCE_LABELS.get(data["audience_mode"], data["audience_mode"])
    recipients_line = f"（{data['_recipients_display']}）" if data.get("_recipients_display") else ""
    notes_line = data.get("notes") or "（無）"
    return (
        "請確認以下內容：\n\n"
        f"名稱：{data['title']}\n"
        f"重複方式：{recurrence_label}\n"
        f"日期：{date_line}\n"
        f"時間：{time_line}\n"
        f"提前提醒：{data['reminder_days_before']} 天\n"
        f"通知對象：{audience_label}{recipients_line}\n"
        f"備註：{notes_line}"
    )


def handle_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    text: str,
) -> tuple[str, dict | None]:
    """依目前對話狀態處理重要日子新增／編輯流程中輸入的下一句話。"""
    state = state_store.get(telegram_user_id)
    step = state.get("step")
    data: dict[str, Any] = state.get("data", {})

    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束重要日子設定！", menu.back_to_main_menu_keyboard()

    try:
        if step == "awaiting_title":
            title = text.strip()
            if not title:
                return "名稱不可以是空白，請重新輸入：", None
            data["title"] = title
            state["step"] = "awaiting_recurrence_type"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return (
                "請選擇重複方式：\n"
                "1. 每年固定日期（例如國曆生日）\n"
                "2. 每年浮動日期（例如農曆節日，日期每年不同）\n"
                "3. 單次事件（只發生一次）"
            ), None

        if step == "awaiting_recurrence_type":
            mapping = {"1": "fixed_annual", "2": "flexible_annual", "3": "one_time"}
            choice = mapping.get(text.strip())
            if not choice:
                return "請輸入 1、2 或 3：", None
            data["recurrence_type"] = choice
            if choice == "fixed_annual":
                state["step"] = "awaiting_start_mmdd"
                prompt = "請輸入每年的開始日期（月-日，例如 8-15）："
            elif choice == "one_time":
                state["step"] = "awaiting_start_date"
                prompt = "請輸入日期（YYYY-MM-DD，例如 2026-09-20）："
            else:
                state["step"] = "awaiting_occurrence_date"
                prompt = "若已經知道今年確切日期，請輸入（YYYY-MM-DD）；還不知道的話請輸入「略過」："
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return prompt, None

        if step == "awaiting_start_mmdd":
            start = _parse_mmdd(text, "開始日期")
            data["_start_mmdd"] = (start.month, start.day)
            data["_display_start"] = f"{start.month}-{start.day}"
            state["step"] = "awaiting_end_mmdd"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return "請輸入每年的結束日期（月-日；只有一天的話重打一次開始日期即可）：", None

        if step == "awaiting_end_mmdd":
            end = _parse_mmdd(text, "結束日期")
            start_month, start_day = data["_start_mmdd"]
            start_date = date(_DUMMY_YEAR, start_month, start_day)
            if end < start_date:
                return "結束日期不可早於開始日期，請重新輸入：", None
            data["event_date"] = start_date.isoformat()
            data["event_end_date"] = end.isoformat()
            data["_display_end"] = f"{end.month}-{end.day}"
            return _advance_to_all_day(state, state_store, telegram_user_id, data)

        if step == "awaiting_start_date":
            start = _parse_full_date(text, "開始日期")
            data["_start_date"] = start.isoformat()
            data["_display_start"] = start.isoformat()
            state["step"] = "awaiting_end_date"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return "請輸入結束日期（只有一天的話重打一次開始日期即可）：", None

        if step == "awaiting_end_date":
            end = _parse_full_date(text, "結束日期")
            start = date.fromisoformat(data["_start_date"])
            if end < start:
                return "結束日期不可早於開始日期，請重新輸入：", None
            data["event_date"] = data["_start_date"]
            data["event_end_date"] = end.isoformat()
            data["_display_end"] = end.isoformat()
            return _advance_to_all_day(state, state_store, telegram_user_id, data)

        if step == "awaiting_occurrence_date":
            if text.strip() in _SKIP_PHRASES:
                data["occurrence_date"] = None
                data["_display_start"] = None
            else:
                occurrence = _parse_full_date(text, "日期")
                data["occurrence_date"] = occurrence.isoformat()
                data["occurrence_end_date"] = occurrence.isoformat()
                data["_display_start"] = occurrence.isoformat()
            return _advance_to_all_day(state, state_store, telegram_user_id, data)

        if step == "awaiting_all_day":
            if text.strip() in ("是", "全天", "yes"):
                data["is_all_day"] = True
                state["step"] = "awaiting_reminder_days"
                state["data"] = data
                state_store.set(telegram_user_id, state)
                return "請輸入提前幾天提醒（0～365，輸入 0 代表當天才提醒）：", None
            if text.strip() in ("否", "no"):
                data["is_all_day"] = False
                state["step"] = "awaiting_time"
                state["data"] = data
                state_store.set(telegram_user_id, state)
                return "請輸入事件時間（HH:MM，例如 19:30）：", None
            return "請回答「是」（全天）或「否」（指定時間）：", None

        if step == "awaiting_time":
            event_time = _parse_hhmm(text)
            data["event_time"] = event_time.strftime("%H:%M")
            state["step"] = "awaiting_reminder_days"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return "請輸入提前幾天提醒（0～365，輸入 0 代表當天才提醒）：", None

        if step == "awaiting_reminder_days":
            if not text.strip().isdigit() or not 0 <= int(text.strip()) <= 365:
                return "請輸入 0～365 之間的整數：", None
            data["reminder_days_before"] = int(text.strip())
            state["step"] = "awaiting_audience"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return (
                "請選擇通知對象：\n"
                "1. 只有自己\n"
                "2. 全部家人\n"
                "3. 指定家人"
            ), None

        if step == "awaiting_audience":
            mapping = {"1": "self", "2": "all", "3": "specific"}
            choice = mapping.get(text.strip())
            if not choice:
                return "請輸入 1、2 或 3：", None
            data["audience_mode"] = choice
            if choice != "specific":
                data["recipient_ids"] = []
                data["_recipients_display"] = ""
                return _advance_to_notes(state, state_store, telegram_user_id, data)

            candidates = _family_candidates(db)
            state["_audience_candidates"] = [c["id"] for c in candidates]
            state["step"] = "awaiting_recipients"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            lines = ["請輸入要通知的家人編號，多位用逗號分隔（例如 1,3）：", ""]
            for index, candidate in enumerate(candidates, start=1):
                lines.append(f"{index}. {candidate['display_name']}")
            return "\n".join(lines), None

        if step == "awaiting_recipients":
            candidates_ids = state.get("_audience_candidates", [])
            candidates = _family_candidates(db)
            raw_indices = [part.strip() for part in text.split(",") if part.strip()]
            if not raw_indices or not all(part.isdigit() and 1 <= int(part) <= len(candidates_ids) for part in raw_indices):
                return f"請輸入 1～{len(candidates_ids)} 之間的編號，多位用逗號分隔：", None
            picked = sorted({int(part) for part in raw_indices})
            data["recipient_ids"] = [candidates_ids[i - 1] for i in picked]
            data["_recipients_display"] = "、".join(candidates[i - 1]["display_name"] for i in picked)
            return _advance_to_notes(state, state_store, telegram_user_id, data)

        if step == "awaiting_notes":
            data["notes"] = None if text.strip() in _SKIP_PHRASES else text.strip()
            state["step"] = "awaiting_confirm"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "✅ 確認送出", "callback_data": "important_days:confirm_save"}],
                    [{"text": "❌ 取消", "callback_data": "menu:main"}],
                ]
            }
            return _summary_text(data), keyboard

    except ImportantDayValidationError as exc:
        return str(exc), None

    raise ValueError(f"未知的對話狀態：{state}")


def _advance_to_all_day(state: dict, state_store: ConversationStateStore, telegram_user_id: int, data: dict) -> tuple[str, None]:
    state["step"] = "awaiting_all_day"
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return "這個事件是全天嗎？請回答「是」或「否」：", None


def _advance_to_notes(state: dict, state_store: ConversationStateStore, telegram_user_id: int, data: dict) -> tuple[str, None]:
    state["step"] = "awaiting_notes"
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return "有想補充的備註嗎？沒有的話請輸入「略過」：", None


def handle_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "important_days" or state.get("step") != "awaiting_confirm":
        return "目前沒有進行中的重要日子設定。", menu.back_to_main_menu_keyboard()

    data = dict(state["data"])
    mode = state.get("mode", "add")
    target_id = state.get("target_id")
    payload = {k: v for k, v in data.items() if not k.startswith("_")}

    service = _service(db)
    state_store.clear(telegram_user_id)
    try:
        if mode == "edit" and target_id is not None:
            service.update(target_id, user_id, payload)
            return "已更新該筆重要日子！", menu.back_to_main_menu_keyboard()
        service.create(user_id, payload)
        return "已新增重要日子！", menu.back_to_main_menu_keyboard()
    except ImportantDayValidationError as exc:
        return f"儲存失敗：{exc}\n請重新從「重要日子」選單開始設定。", menu.back_to_main_menu_keyboard()
    except ImportantDayNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
