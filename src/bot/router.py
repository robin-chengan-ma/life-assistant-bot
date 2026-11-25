"""Telegram 文字訊息／callback_query 的最小分派邏輯。

2026-11（功能大幅精簡，見 repo 根目錄的重新定案說明）：Telegram 機器人只剩下三件事：
1. `/start` 通關密碼綁定（一般使用者）／Owner 免密碼直接視為已登入。
2. Owner 專屬的「權限管理」對話流程（建立使用者／停用／恢復／重發通關密碼），由
   `/permission` 這個 Slash Command 觸發（取代舊版「主選單→🔑 權限管理」按鈕，主選單本身
   已經整個拿掉，沒有其餘項目可以放在同一個選單裡，直接做成獨立指令最單純）。
3. 待辦事項／生日的推播提醒——這兩個是單向推播，不經過這裡的對話分派，由 `main.py` 排程直接
   呼叫 `src/bot/todo.py`／`src/bot/important_days.py` 的 `check_and_push_*()`。

其餘所有舊版選單分支（日常紀錄、記帳、待辦 CRUD、重要日子 CRUD、收藏與旅遊、成果展示、目標
追蹤、資料查詢、求職、證照、心情小記、好友模式、語音/圖片輸入…）隨著 Mobile App 接手全部資料
輸入而一併移除。
"""

from __future__ import annotations

from src.bot import auth, commands, templates
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_START_TRIGGERS = {"/start"}
_PERMISSION_TRIGGERS = {"/permission"}
_EXIT_PHRASES = {"沒有了", "結束"}

_AWAITING_PASSCODE_REPLY = "請輸入你的通關密碼："
_PASSCODE_BIND_FAILED_REPLY = "通關密碼不正確或已失效，請重新輸入，或輸入 /start 重新開始。"
_NOT_BOUND_REPLY = "請先輸入 /start 並依指示輸入通關密碼完成綁定喔！"
_OWNER_WELCOME_REPLY = (
    "歡迎回來，Robin！這個機器人現在只負責待辦事項／生日推播提醒，"
    "以及權限管理（輸入 /permission）。其餘功能請到 App 操作。"
)
_PERMISSION_DENIED_REPLY = "這個功能只有 Robin 可以使用喔！"
_ALREADY_BOUND_REPLY = "你已經綁定完成囉！這個機器人只會主動推播待辦事項／生日提醒，其餘功能請到 App 操作。"


def _owner_active_flow(flow: str | None) -> bool:
    return flow in ("permission_create", "permission_disable", "permission_enable", "permission_resend")


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
) -> tuple[str, dict | None]:
    """處理一則來自 Telegram 的文字訊息，回傳 `(text, reply_markup)`。"""
    text = (text or "").strip()
    is_owner = auth.is_owner(telegram_user_id)

    if text in _START_TRIGGERS:
        state_store.clear(telegram_user_id)
        if is_owner:
            auth.get_or_create_owner(db, telegram_user_id)
            return _OWNER_WELCOME_REPLY, None

        user = auth.find_user_by_telegram_id(db, telegram_user_id)
        if user is None:
            state_store.set(telegram_user_id, {"flow": "awaiting_passcode"})
            return _AWAITING_PASSCODE_REPLY, None
        return _ALREADY_BOUND_REPLY, None

    if is_owner:
        auth.get_or_create_owner(db, telegram_user_id)
        state = state_store.get(telegram_user_id)
        if state is not None and _owner_active_flow(state.get("flow")):
            return commands.handle_permission_step(db, state_store, telegram_user_id, text), None

        if text in _PERMISSION_TRIGGERS:
            return commands.start_permission_menu()

        return _OWNER_WELCOME_REPLY, None

    user = auth.find_user_by_telegram_id(db, telegram_user_id)
    if user is None:
        state = state_store.get(telegram_user_id)
        if state is not None and state.get("flow") == "awaiting_passcode":
            if auth.try_bind_invite_code(db, telegram_user_id, text):
                state_store.clear(telegram_user_id)
                return templates.APPENDIX_A_TEXT, None
            return _PASSCODE_BIND_FAILED_REPLY, None
        return _NOT_BOUND_REPLY, None

    return _ALREADY_BOUND_REPLY, None


def handle_callback_query(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    data: str,
) -> tuple[str, dict | None]:
    """處理按下 Inline Keyboard 按鈕觸發的 callback_query。

    目前只有「權限管理」選單用到 Inline Keyboard，且全程 Owner-only（見 FR-6c：任何選單／
    callback 都要重新驗證權限，不能只靠「一開始選單沒顯示這顆按鈕」來擋，避免偽造 callback_data
    繞過）。
    """
    is_owner = auth.is_owner(telegram_user_id)
    if data.startswith("permission:"):
        action = data[len("permission:") :]
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, None
        if action == "menu":
            return commands.start_permission_menu()
        return commands.handle_permission_callback(db, state_store, telegram_user_id, action)

    raise ValueError(f"未知的 callback_data：{data}")
