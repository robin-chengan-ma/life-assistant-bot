"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
import re

from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, chat, commands, image, templates, toggles
from src.bot.state import ConversationStateStore

_NOT_BOUND_REPLY = "請輸入通關密碼才能開始使用羅賓森喔！"

_SET_INVITE_CODES_TRIGGERS = {"/set_invite_codes", "設定通關密碼"}
_RULE_TRIGGERS = {"/rule", "我要看使用規則"}
_FUNCTION_TRIGGERS = {"/function", "我要看所有功能"}
_MY_TOGGLES_TRIGGERS = {"/my_toggles", "我的功能設定"}
_SET_TOGGLE_TRIGGERS = {"/set_toggle", "設定家人功能開關"}
_CLEAN_ALL_DIALOG_TRIGGERS = {"/clean-all-dialog", "我想要刪除所有對話紀錄"}
# 2026-08-01（chat-core SPEC.md FR-12）：/clean-target-dialog 的主題是自由文字，無法用固定
# 觸發詞集合窮舉，改用 regex 擷取「我想刪除有關 OOO 的紀錄」或 `/clean-target-dialog OOO` 的主題。
_CLEAN_TARGET_DIALOG_PATTERN = re.compile(
    r"^(?:/clean-target-dialog\s+(?P<topic1>.+)|我想刪除有關(?P<topic2>.+)的紀錄)$"
)


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
    llm_client=None,
    text_llm_client=None,
    image_llm_clients: list | None = None,
) -> str:
    """處理一則來自 Telegram 的文字訊息，回傳要回覆的文字。

    `llm_client`（`GEMINI_API_BOT_KEY`）與 `text_llm_client`（`GEMINI_API_TEXT_KEY`，長記憶摘要用，
    見 chat-core SPEC.md ADR-3）在訊息落入一般聊天核心、或 `pending_clean_all_dialog_confirm`
    反問確認流程（見 FR-10 追加修正）時會用到，`image_llm_clients`
    （`GEMINI_API_IMAGE_KEY1`/`KEY2`，見 robinson SPEC.md ADR-13）只有在使用者處於圖片辨識反問
    澄清流程（`pending_image_confirm`）時才會用到，其餘指令/對話流程分支都不需要；正式環境一律由
    webhook.py 注入，這裡預設 None 只是為了讓不涉及該流程的既有測試不用逐一補上假的 LLM Client。
    """
    text = (text or "").strip()
    is_owner = auth.is_owner(telegram_user_id)

    if is_owner:
        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(
                db, state_store, telegram_user_id, text, state,
                llm_client, text_llm_client, image_llm_clients,
            )

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
            return _NOT_BOUND_REPLY

        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(
                db, state_store, telegram_user_id, text, state,
                llm_client, text_llm_client, image_llm_clients,
            )

        user_id = user["id"]

        if text in _MY_TOGGLES_TRIGGERS:
            return commands.start_my_toggles(db, state_store, telegram_user_id, user_id)

    if text in _RULE_TRIGGERS:
        return commands.handle_rule()
    if text in _FUNCTION_TRIGGERS:
        return commands.handle_function(db, llm_client)
    if text in _CLEAN_ALL_DIALOG_TRIGGERS:
        # 2026-08-01 起改為先反問確認，不再直接刪除，見 commands.start_clean_all_dialog_confirm。
        return commands.start_clean_all_dialog_confirm(db, state_store, telegram_user_id, user_id)
    target_match = _CLEAN_TARGET_DIALOG_PATTERN.match(text)
    if target_match:
        # 2026-08-01（FR-12）：主題式清除，範圍依 is_owner 決定要不要納入共用知識庫，見
        # commands.start_clean_target_dialog_confirm。
        topic = (target_match.group("topic1") or target_match.group("topic2")).strip()
        return commands.start_clean_target_dialog_confirm(
            db, llm_client, state_store, telegram_user_id, user_id, is_owner, topic
        )

    return chat.handle_chat_message(
        db, llm_client, text_llm_client, state_store, telegram_user_id, user_id, text
    )


def _get_identified_user(db: CloudSQLClient, telegram_user_id: int) -> dict | None:
    """依身分找出對應的 users 記錄；Robin（Owner）一定有記錄，其餘家人未綁定通關密碼則回傳 None。"""
    if auth.is_owner(telegram_user_id):
        return auth.get_or_create_owner(db, telegram_user_id)
    return auth.find_user_by_telegram_id(db, telegram_user_id)


def handle_photo_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    file_id: str,
    caption: str | None,
    telegram_client,
    gdrive_client,
    image_llm_clients: list,
) -> str:
    """處理使用者傳來的圖片訊息（對應 robinson SPEC.md FR-17、ADR-13）。

    未綁定通關密碼者一律先擋下，不消耗任何 Drive/Gemini 額度；已綁定者才下載圖片並交給
    `src/bot/image.py` 的商業邏輯處理。若使用者原本卡在某個未完成的對話流程（例如上一輪的
    圖片澄清問答還沒回答完就又傳了新圖片），直接以新圖片覆蓋、清除舊流程狀態，避免卡死。
    """
    user = _get_identified_user(db, telegram_user_id)
    if user is None:
        return _NOT_BOUND_REPLY

    state_store.clear(telegram_user_id)

    image_bytes = telegram_client.get_file_bytes(file_id)
    return image.handle_image_message(
        db,
        gdrive_client,
        image_llm_clients,
        state_store,
        telegram_user_id,
        user["id"],
        user["role"],
        image_bytes,
        caption,
    )


def _dispatch_active_flow(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    state: dict,
    llm_client=None,
    text_llm_client=None,
    image_llm_clients: list | None = None,
) -> str:
    """依進行中對話流程的 `flow` 標記分派到對應處理函式（見各 flow 對應 spec 的 ADR）。"""
    flow = state.get("flow")
    if flow == "set_invite_codes":
        return commands.handle_set_invite_codes_step(db, state_store, telegram_user_id, text)
    if flow == "pending_user_knowledge":
        # 2026-07-31（ADR-6）：不再無條件把這則訊息當成答案存檔，改由同一次 LLM 呼叫判斷
        # 這是在提供答案、拒絕記錄、還是問了個無關的新問題，見 chat.handle_chat_message。
        return chat.handle_chat_message(
            db, llm_client, text_llm_client, state_store, telegram_user_id,
            state["target_user_id"], text, pending_question=state.get("original_question"),
        )
    if flow == "pending_name_confirm":
        # 2026-08-01（ADR-7）：打字誤植改為先反問確認，等使用者這則回覆才真正回答原本的問題。
        return chat.handle_chat_message(
            db, llm_client, text_llm_client, state_store, telegram_user_id,
            state["target_user_id"], text, confirming_question=state.get("original_question"),
        )
    if flow == "pending_image_confirm":
        return image.handle_image_confirm_step(image_llm_clients, state_store, telegram_user_id, text)
    if flow == "pending_clean_all_dialog_confirm":
        # 2026-08-01：/clean-all-dialog 先反問確認，這一輪由使用者的回覆判斷要不要真的執行刪除。
        return commands.handle_clean_all_dialog_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_save_knowledge_confirm":
        # 2026-08-01（FR-11）：主動新增知識先反問確認，這一輪判斷確定/取消並整理出分類與內容。
        return commands.handle_save_knowledge_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_clean_target_dialog_confirm":
        # 2026-08-01（FR-12）：主題式清除先反問確認，這一輪判斷確定/取消並真正執行刪除。
        return commands.handle_clean_target_dialog_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    return commands.handle_toggle_step(db, state_store, telegram_user_id, text)
