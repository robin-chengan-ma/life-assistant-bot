"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
import re

from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, chat, commands, image, templates, toggles, voice
from src.bot.state import ConversationStateStore

_NOT_BOUND_REPLY = "請輸入通關密碼才能開始使用羅賓森喔！"

# 2026-08-01（Step 1.4，robinson SPEC.md FR-14／FR-15）：語音訊息的兩種擋下情境固定文案，
# 都在下載/上傳/轉文字之前就先擋下，避免浪費 Drive／Groq 額度，見 src/bot/voice.py 模組 docstring。
_VOICE_DURATION_LIMIT_REPLY = "這則語音超過 10 分鐘囉，我沒辦法處理這麼長的語音，麻煩分段傳送或改用打字喔！"
_VOICE_CORRECTION_WINDOW_REPLY = "你剛剛才傳過語音，15 分鐘內麻煩先用打字修正或補充喔，超過 15 分鐘語音模式就會自動恢復！"

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

# 2026-08-02（FR-16a）：這幾個「最終執行確認」狀態是唯二不能被新語音訊息直接覆蓋清除的 flow，
# 見 handle_voice_message() 內的說明。
_FINAL_CONFIRM_FLOWS = {
    "pending_clean_all_dialog_final_confirm",
    "pending_clean_target_dialog_final_confirm",
    "pending_save_knowledge_final_confirm",
}


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
    llm_client=None,
    text_llm_client=None,
    image_llm_clients: list | None = None,
    via_voice: bool = False,
) -> str:
    """處理一則來自 Telegram 的文字訊息，回傳要回覆的文字。

    `llm_client`（`GEMINI_API_BOT_KEY`）與 `text_llm_client`（`GEMINI_API_TEXT_KEY`，長記憶摘要用，
    見 chat-core SPEC.md ADR-3）在訊息落入一般聊天核心、或 `pending_clean_all_dialog_confirm`
    反問確認流程（見 FR-10 追加修正）時會用到，`image_llm_clients`
    （`GEMINI_API_IMAGE_KEY1`/`KEY2`，見 robinson SPEC.md ADR-13）只有在使用者處於圖片辨識反問
    澄清流程（`pending_image_confirm`）時才會用到，其餘指令/對話流程分支都不需要；正式環境一律由
    webhook.py 注入，這裡預設 None 只是為了讓不涉及該流程的既有測試不用逐一補上假的 LLM Client。

    `via_voice`（2026-08-02，robinson SPEC.md FR-16a）：這則文字是不是語音轉出來的——由
    `handle_voice_message()` 呼叫這裡時固定傳 `True`，webhook.py 處理一般文字訊息時維持預設的
    `False`。只有 `pending_*_final_confirm` 這幾個「最終執行確認」狀態會用到，見
    `_dispatch_active_flow()`；其餘分支不受影響。
    """
    text = (text or "").strip()
    is_owner = auth.is_owner(telegram_user_id)

    if is_owner:
        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(
                db, state_store, telegram_user_id, text, state,
                llm_client, text_llm_client, image_llm_clients, via_voice,
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
                llm_client, text_llm_client, image_llm_clients, via_voice,
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


def handle_voice_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    file_id: str,
    duration_seconds: int | None,
    telegram_client,
    gdrive_client,
    voice_client,
    llm_client=None,
    text_llm_client=None,
    mime_type: str = "audio/ogg",
) -> str:
    """處理使用者傳來的語音/音檔訊息（對應 robinson SPEC.md FR-14、FR-15、FR-17、ADR-12、ADR-13）。

    涵蓋 Telegram 的 `voice`（錄音鍵語音訊息）與 `audio`（使用者上傳的音檔）兩種類型，
    FR-17 承諾「圖片與音檔」都支援，不限定只有錄音鍵那種；`mime_type` 由呼叫端
    （webhook.py）依實際訊息類型傳入，供 `voice.transcribe_and_upload()` 決定正確的
    Drive 副檔名與轉錄請求格式（見 src/bot/voice.py 模組 docstring）。

    FR-14（10 分鐘上限）／FR-15（15 分鐘修正窗口）刻意排在下載語音檔之前檢查，通過後才
    下載、上傳 Drive、記錄 media_uploads、呼叫 Groq Whisper 轉文字。轉出來的文字不會
    另外走一套獨立流程，而是直接當成使用者「打字輸入」，呼叫既有的 `handle_message()`
    走完整的指令/pending flow/一般聊天分派——這是 Step 1.4 刻意的架構選擇：語音只負責
    「變成文字」，「文字要怎麼處理」全部復用既有邏輯，不重複。

    2026-08-02（FR-16a）：`via_voice=True` 會一路帶進 `handle_message()`。但如果目前卡在
    `_FINAL_CONFIRM_FLOWS` 這幾個「最終執行確認」狀態，**刻意不比照下面清除舊流程的慣例**——
    要是先清掉，`handle_message()` 就看不到這個 flow，via_voice 檢查也永遠不會被觸發，語音
    訊息就會被當成完全無關的新對話處理，使用者會搞不清楚原本在確認的操作到底算不算數。
    """
    user = _get_identified_user(db, telegram_user_id)
    if user is None:
        return _NOT_BOUND_REPLY

    if voice.exceeds_duration_limit(duration_seconds):
        return _VOICE_DURATION_LIMIT_REPLY
    if voice.is_within_correction_window(db, user["id"]):
        return _VOICE_CORRECTION_WINDOW_REPLY

    current_state = state_store.get(telegram_user_id)
    if current_state is None or current_state.get("flow") not in _FINAL_CONFIRM_FLOWS:
        # 比照 handle_photo_message：新語音訊息直接覆蓋任何未完成的舊流程狀態，避免卡死。
        state_store.clear(telegram_user_id)

    voice_bytes = telegram_client.get_file_bytes(file_id)
    transcribed_text = voice.transcribe_and_upload(
        db, gdrive_client, voice_client, user["id"], user["role"], voice_bytes, mime_type=mime_type
    )

    # via_voice=True（FR-16a）：讓 pending_*_final_confirm 這幾個最終執行確認狀態能認出這則訊息
    # 是語音轉出來的，一律拒絕、不允許用語音完成最後一步。
    return handle_message(
        db, state_store, telegram_user_id, transcribed_text,
        llm_client=llm_client, text_llm_client=text_llm_client, via_voice=True,
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
    via_voice: bool = False,
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
        # 2026-08-01：/clean-all-dialog 先反問確認，這一輪由使用者的回覆判斷要不要進入最終確認。
        return commands.handle_clean_all_dialog_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_clean_all_dialog_final_confirm":
        # 2026-08-02（FR-16a）：最終執行確認，只接受打字逐字輸入固定關鍵字，語音一律拒絕。
        return commands.handle_clean_all_dialog_final_confirm_step(
            db, state_store, telegram_user_id, text, via_voice
        )
    if flow == "pending_save_knowledge_confirm":
        # 2026-08-01（FR-11）：主動新增知識先反問確認，這一輪判斷確定/取消並整理出分類與內容。
        return commands.handle_save_knowledge_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_save_knowledge_final_confirm":
        # 2026-08-02（FR-16a）：最終儲存確認，只接受打字逐字輸入固定關鍵字，語音一律拒絕。
        return commands.handle_save_knowledge_final_confirm_step(db, state_store, telegram_user_id, text, via_voice)
    if flow == "pending_clean_target_dialog_confirm":
        # 2026-08-01（FR-12）：主題式清除先反問確認，這一輪判斷確定/取消並進入最終確認。
        return commands.handle_clean_target_dialog_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_clean_target_dialog_final_confirm":
        # 2026-08-02（FR-16a）：最終執行確認，只接受打字逐字輸入固定關鍵字，語音一律拒絕。
        return commands.handle_clean_target_dialog_final_confirm_step(
            db, state_store, telegram_user_id, text, via_voice
        )
    return commands.handle_toggle_step(db, state_store, telegram_user_id, text)
