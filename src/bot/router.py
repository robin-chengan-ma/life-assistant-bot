"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, commands, templates
from src.bot.state import ConversationStateStore

_SET_INVITE_CODES_TRIGGERS = {"/set_invite_codes", "設定通關密碼"}
_RULE_TRIGGERS = {"/rule", "我要看使用規則"}
_FUNCTION_TRIGGERS = {"/function", "我要看所有功能"}
_PLACEHOLDER_REPLY = "（一般對話功能尚未上線，敬請期待！）"


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
) -> str:
    """處理一則來自 Telegram 的文字訊息，回傳要回覆的文字。"""
    text = (text or "").strip()

    if auth.is_owner(telegram_user_id):
        state = state_store.get(telegram_user_id)
        if state is not None:
            return commands.handle_set_invite_codes_step(db, state_store, telegram_user_id, text)

        if text in _SET_INVITE_CODES_TRIGGERS:
            return commands.start_set_invite_codes(state_store, telegram_user_id)

        # Robin 免通關密碼視為管理者兼使用者，確保他一定有一筆 users 記錄（FR-5）
        auth.get_or_create_owner(db, telegram_user_id)
    else:
        user = auth.find_user_by_telegram_id(db, telegram_user_id)
        if user is None:
            if auth.try_bind_invite_code(db, telegram_user_id, text):
                return templates.APPENDIX_A_TEXT
            return "請輸入通關密碼才能開始使用羅賓森喔！"

    if text in _RULE_TRIGGERS:
        return commands.handle_rule()
    if text in _FUNCTION_TRIGGERS:
        return commands.handle_function()

    return _PLACEHOLDER_REPLY
