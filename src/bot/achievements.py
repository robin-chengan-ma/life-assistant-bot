"""Telegram「成果展示」選單流程（Phase 6 第二批 2e，見 docs/ADR/discuss/robinson.md
2026-08-16「Phase 6 第二批 2e（成果展示）實作計畫」）。

直接複用既有 `AppLifeExplorationService`（Mobile App 已在用的同一套驗證與 CRUD 邏輯），
不重寫欄位規則，符合 FR-6h「兩端共用相同欄位、必填、數值範圍、驗證與讀取結果」。

候選機制維持「被動」：使用者按下「📋 查看成果」時，`list_achievements()` 內建才會重新
掃描一次候選（體態達標、考試達標、運動累積、探索地點/國家數、行程完成、待辦里程碑），
不在目標達成的當下主動推播按鈕——2026-08-16 決策，見上述 ADR 條目與對應的 SPEC.md
FR-45／FR-76 文字修正。

刪除採 Telegram 端簡化規則：按下「🗑 刪除」直接呼叫 `delete_achievement()`，沒有二次
確認、也沒有 5 秒復原（跟 Mobile App 維持既有復原機制不同，這是本批刻意決策，見 ADR）。
"""

from __future__ import annotations

from typing import Any

from src.bot import menu
from src.bot.state import ConversationStateStore
from src.services.app_life_exploration import (
    AppLifeExplorationService,
    LifeNotFoundError,
    LifeValidationError,
)
from src.services.geocoding import NominatimGeocoder
from submodules.cloudsql.client import CloudSQLClient

_EXIT_PHRASES = {"沒有了", "結束"}
_SKIP_PHRASES = {"略過", "skip"}

_CATEGORY_LABELS = {
    "body": "體態",
    "exam": "考試",
    "exercise": "運動",
    "exploration": "探索",
    "trip": "旅遊",
    "todo": "待辦",
    "other": "其他",
}
_CATEGORY_ORDER = ("body", "exam", "exercise", "exploration", "trip", "todo", "other")


def _service(db: CloudSQLClient) -> AppLifeExplorationService:
    return AppLifeExplorationService(db, NominatimGeocoder(db))


# ---------------------------------------------------------------------------
# 選單／清單
# ---------------------------------------------------------------------------

def start_achievements_menu() -> tuple[str, dict]:
    """主選單按下「🏆 成果展示」後的子選單首頁。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "📋 查看成果", "callback_data": "achievements:list"}],
            [{"text": "➕ 新增成果", "callback_data": "achievements:add"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    return "成果展示，請選擇要進行的操作：", keyboard


def _format_candidate(candidate: dict[str, Any], index: int) -> str:
    category_label = _CATEGORY_LABELS.get(candidate["category"], candidate["category"])
    return f"候選 {index}. {candidate['title']}（{category_label}｜{candidate['completed_on']}）"


def _format_achievement(row: dict[str, Any], index: int) -> str:
    category_label = _CATEGORY_LABELS.get(row["category"], row["category"])
    source_label = "手動新增" if row["creation_source"] == "manual" else "系統候選"
    pin_label = "📌 " if row.get("pinned_at") else ""
    return f"{index}. {pin_label}{row['title']}（{category_label}｜{row['unlocked_on']}｜{source_label}）"


def handle_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    service = _service(db)
    result = service.list_achievements(user_id)
    candidates = result["candidates"]
    achievements = result["achievements"]

    lines: list[str] = []
    buttons: list[list[dict]] = []

    if candidates:
        lines.append("待確認的成果候選：")
        lines.append("")
        for index, candidate in enumerate(candidates, start=1):
            lines.append(_format_candidate(candidate, index))
            buttons.append(
                [
                    {"text": f"✅ 加入 {index}", "callback_data": f"achievements:candidate_accept:{candidate['id']}"},
                    {"text": f"⏭ 略過 {index}", "callback_data": f"achievements:candidate_reject:{candidate['id']}"},
                ]
            )
        lines.append("")

    if achievements:
        lines.append("已建立的成果：")
        lines.append("")
        for index, row in enumerate(achievements, start=1):
            lines.append(_format_achievement(row, index))
            pin_action = "unpin" if row.get("pinned_at") else "pin"
            pin_text = "取消置頂" if row.get("pinned_at") else "置頂"
            buttons.append([
                {"text": f"📌 {pin_text} {index}", "callback_data": f"achievements:{pin_action}:{row['id']}"},
                {"text": f"🗑 刪除 {index}", "callback_data": f"achievements:delete:{row['id']}"},
            ])
    elif not candidates:
        lines.append("目前還沒有任何成果，也沒有待確認的候選，可以按「➕ 新增成果」建立第一筆！")

    buttons.append([{"text": "➕ 新增成果", "callback_data": "achievements:add"}])
    buttons.append([{"text": "🔙 返回", "callback_data": "menu:achievements"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


# ---------------------------------------------------------------------------
# 候選確認
# ---------------------------------------------------------------------------

def handle_candidate_decision(
    db: CloudSQLClient, user_id: int, candidate_id: int, accept: bool
) -> tuple[str, dict]:
    service = _service(db)
    try:
        result = service.respond_candidate(candidate_id, user_id, accept)
    except LifeValidationError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    except LifeNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return result["message"], menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 新增成果（手動）
# ---------------------------------------------------------------------------

def start_add(state_store: ConversationStateStore, telegram_user_id: int) -> str:
    state_store.set(
        telegram_user_id,
        {"flow": "achievement", "step": "awaiting_category", "data": {}},
    )
    return _category_prompt()


def _category_prompt() -> str:
    lines = ["請選擇成果類別："]
    for index, key in enumerate(_CATEGORY_ORDER, start=1):
        lines.append(f"{index}. {_CATEGORY_LABELS[key]}")
    return "\n".join(lines)


def _summary_text(data: dict[str, Any]) -> str:
    category_label = _CATEGORY_LABELS.get(data["category"], data["category"])
    description = data.get("description") or "（無）"
    cover_image_url = data.get("cover_image_url") or "（無）"
    return (
        "請確認以下內容：\n\n"
        f"類別：{category_label}\n"
        f"名稱：{data['title']}\n"
        f"完成日期：{data['completed_on']}\n"
        f"說明：{description}\n"
        f"照片網址：{cover_image_url}"
    )


def handle_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> tuple[str, dict | None]:
    state = state_store.get(telegram_user_id)
    step = state.get("step")
    data: dict[str, Any] = state.get("data", {})

    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束成果設定！", menu.back_to_main_menu_keyboard()

    if step == "awaiting_category":
        mapping = {str(i): key for i, key in enumerate(_CATEGORY_ORDER, start=1)}
        choice = mapping.get(text.strip())
        if not choice:
            return f"請輸入 1～{len(_CATEGORY_ORDER)} 之間的數字：", None
        data["category"] = choice
        state["step"] = "awaiting_title"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入成果名稱：", None

    if step == "awaiting_title":
        title = text.strip()
        if not title:
            return "名稱不可以是空白，請重新輸入：", None
        data["title"] = title
        state["step"] = "awaiting_completed_on"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入完成日期（YYYY-MM-DD）：", None

    if step == "awaiting_completed_on":
        completed_on = text.strip()
        try:
            from datetime import date as _date

            _date.fromisoformat(completed_on)
        except ValueError:
            return "日期格式不正確，請用「YYYY-MM-DD」：", None
        data["completed_on"] = completed_on
        state["step"] = "awaiting_description"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "有想補充的說明嗎？沒有的話請輸入「略過」：", None

    if step == "awaiting_description":
        data["description"] = None if text.strip() in _SKIP_PHRASES else text.strip()
        state["step"] = "awaiting_cover_image_url"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "有想附上的照片網址嗎？沒有的話請輸入「略過」：", None

    if step == "awaiting_cover_image_url":
        data["cover_image_url"] = None if text.strip() in _SKIP_PHRASES else text.strip()
        state["step"] = "awaiting_confirm"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        keyboard = {
            "inline_keyboard": [
                [{"text": "✅ 確認送出", "callback_data": "achievements:confirm_save"}],
                [{"text": "❌ 取消", "callback_data": "menu:main"}],
            ]
        }
        return _summary_text(data), keyboard

    raise ValueError(f"未知的對話狀態：{state}")


def handle_confirm_save(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "achievement" or state.get("step") != "awaiting_confirm":
        return "目前沒有進行中的成果設定。", menu.back_to_main_menu_keyboard()

    data = dict(state["data"])
    state_store.clear(telegram_user_id)
    service = _service(db)
    try:
        service.create_achievement(user_id, data)
    except LifeValidationError as exc:
        return f"儲存失敗：{exc}\n請重新從「成果展示」選單開始設定。", menu.back_to_main_menu_keyboard()
    return "已新增成果！", menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 刪除（按下即直接刪除，無二次確認、無復原，見模組 docstring）
# ---------------------------------------------------------------------------

def handle_delete(db: CloudSQLClient, user_id: int, achievement_id: int) -> tuple[str, dict]:
    service = _service(db)
    try:
        service.delete_achievement(achievement_id, user_id)
    except LifeNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return "已刪除該筆成果。", menu.back_to_main_menu_keyboard()


def handle_pin(
    db: CloudSQLClient, user_id: int, achievement_id: int, pinned: bool
) -> tuple[str, dict]:
    service = _service(db)
    try:
        service.set_achievement_pinned(achievement_id, user_id, pinned)
    except LifeNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return ("已置頂該筆成果。" if pinned else "已取消置頂該筆成果。"), menu.back_to_main_menu_keyboard()
