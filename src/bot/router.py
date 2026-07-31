"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, chat, commands, templates, toggles
from src.bot.state import ConversationStateStore

_SET_INVITE_CODES_TRIGGERS = {"/set_invite_codes", "設定通關密碼"}
_RULE_TRIGGERS = {"/rule", "我要看使用規則"}
_FUNCTION_TRIGGERS = {"/function", "我要看所有功能"}
_MY_TOGGLES_TRIGGERS = {"/my_toggles", "我的功能設定"}
_SET_TOGGLE_TRIGGERS = {"/set_toggle", "設定家人功能開關"}


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
    llm_client=None,
    text_llm_client=None,
) -> str:
    """處理一則來自 Telegram 的文字訊息，回傳要回覆的文字。

    `llm_client`（`GEMINI_API_BOT_KEY`）與 `text_llm_client`（`GEMINI_API_TEXT_KEY`，長記憶摘要用，
    見 chat-core SPEC.md ADR-3）只有在訊息最終落入一般聊天核心時才會用到，其餘指令/對話流程分支
    都不需要；正式環境一律由 webhook.py 注入，這裡預設 None 只是為了讓不涉及聊天核心的既有測試
    不用逐一補上假的 LLM Client。
    """
    text = (text or "").strip()

    if auth.is_owner(telegram_user_id):
        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(db, state_store, telegram_user_id, text, state.get("flow"))

        if text in _SET_INVITE_CODES_TRIGGERS:
            return commands.start_set_invite_codes(state_store, telegram_user_id)

        # Robin 免通關密碼視為管理者兼使用者，確保他一定有一筆 users 記錄（FR-5）
        owner_row = auth.get_or_create_owner(db, telegram_user_id)
        user_id = owner_row["id"]

        if text in _SET_TOGGLE_TRIGGERS:
            return commands.start_set_toggle(db, state_store, telegram_user_id)
        if text in _MY_TOGGLES_TRIGGERS:
            return commands.start_my_toggles(db, state_store, telegram_user_id, user_id)
    else:
        user = auth.find_user_by_telegram_id(db, telegram_user_id)
        if user is None:
            if auth.try_bind_invite_code(db, telegram_user_id, text):
                bound_user = auth.find_user_by_telegram_id(db, telegram_user_id)
                toggles.ensure_default_toggles(db, bound_user["id"])
                return templates.APPENDIX_A_TEXT
            return "請輸入通關密碼才能開始使用羅賓森喔！"

        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(db, state_store, telegram_user_id, text, state.get("flow"))

        user_id = user["id"]

        if text in _MY_TOGGLES_TRIGGERS:
            return commands.start_my_toggles(db, state_store, telegram_user_id, user_id)

    if text in _RULE_TRIGGERS:
        return commands.handle_rule()
    if text in _FUNCTION_TRIGGERS:
        return commands.handle_function()

    return chat.handle_chat_message(
        db, llm_client, text_llm_client, state_store, telegram_user_id, user_id, text
    )


def _dispatch_active_flow(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    flow: str | None,
) -> str:
    """依進行中對話流程的 `flow` 標記分派到對應處理函式（見各 flow 對應 spec 的 ADR）。"""
    if flow == "set_invite_codes":
        return commands.handle_set_invite_codes_step(db, state_store, telegram_user_id, text)
    if flow == "pending_kb_save":
        return chat.handle_pending_kb_save_step(db, state_store, telegram_user_id, text)
    return commands.handle_toggle_step(db, state_store, telegram_user_id, text)
