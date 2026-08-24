"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
import re

from src.bot import (
    achievements,
    auth,
    certificate_settings,
    chat,
    collections,
    commands,
    feature_entry,
    image,
    important_days,
    job_search,
    job_settings,
    menu,
    query,
    recovery_notifications,
    schedule_settings,
    system_error_management,
    templates,
    toggles,
    trips,
    voice,
)
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_NOT_BOUND_REPLY = "請輸入通關密碼才能開始使用羅賓森喔！"
_AWAITING_PASSCODE_REPLY = "請輸入通關密碼："
_PASSCODE_BIND_FAILED_REPLY = "通關密碼不正確或已失效，請重新輸入，或輸入 /start 重新開始。"
_PERMISSION_DENIED_REPLY = "無法使用這個功能。"

_VOICE_DURATION_LIMIT_REPLY = (
    "這則語音超過 10 分鐘囉，我沒辦法處理這麼長的語音，麻煩分段傳送或改用打字喔！"
    "接下來 5 分鐘語音功能會暫時鎖定，這段期間麻煩先用打字。"
)
_VOICE_DURATION_LOCKOUT_REPLY = (
    "剛剛語音超過 10 分鐘，語音功能鎖定中，這段期間麻煩先用打字，超過鎖定時間會自動恢復喔！"
)

# 2026-08-15（Phase 6 第二批 2a，見 docs/specs/SPEC.md FR-6a）：`/start` 是 FR-6a 定案下
# 唯一保留的 Slash Command，用於 START 首次驗證及重新顯示主選單；取代舊版 `/set_invite_codes`
# 的 Owner 建立使用者流程已改為選單驅動，見 commands.start_permission_menu()。
_START_TRIGGERS = {"/start"}
# 2026-08-16（Phase 6 第二批 2f）：待辦事項清單查詢全面改選單觸發（「✅ 待辦事項」→「📋 查看
# 清單」），舊文字觸發詞（/my_todos、「我的待辦事項」）已移除，見 menu.py／commands.py 待辦
# 事項區塊說明。
# 2026-08-16（Phase 6 第二批 2c）：心情小記全面改選單觸發，舊文字觸發詞
# （/mood_journal、/backfill_mood、/my_mood_journals 等）已移除，入口改為
# 「📝 日常紀錄」→「😊 心情」子選單，見 menu.py `DAILY_LOG_MENU_ITEMS`。
# 2026-08-08（Step 3.5，見 robinson SPEC.md FR-51、FR-52、ADR-22）：好友模式陪伴聊天，`friend_mode`
# 開關 owner_only=False，所有使用者皆可用，放在共用觸發詞區塊；單輪生成完整回覆，不需要對話狀態機。
_FRIEND_CHAT_TRIGGERS = {"陪我聊聊"}
# 2026-08-18（批次5）：記帳全面改選單觸發，舊文字觸發詞（/set_budget、/add_transaction、
# /backfill_transaction、/my_transactions、/my_finance_summary、/finance_goal、
# /my_finance_goals 等）已移除，不提供舊指令相容期，入口改為「📝 日常紀錄」→「💰 記帳」子選單，
# 見 menu.py／commands.py 記帳子選單首頁區塊說明；目標入口併入子選單的「🎯 目標」按鈕，跟
# body/collections 的做法一致。
# 2026-08-16（Phase 6 第二批 2c）：運動全面改選單觸發，舊文字觸發詞
# （/log_exercise、/backfill_exercise、/my_exercise_logs 等）已移除，入口改為
# 「📝 日常紀錄」→「🏃 運動」子選單。
# 2026-08-16（Phase 6 第二批 2g）：飲食全面改選單觸發，舊文字觸發詞
# （/log_diet、/backfill_diet、/my_diet_logs 等）已移除，入口改為
# 「📝 日常紀錄」→「🍚 飲食」子選單。
# 2026-08-17（Phase 6 第二批 2h）：體態管理全面改選單觸發，舊文字觸發詞（/set_height、
# /set_waist、/log_weight、/backfill_weight、/my_weight_logs、/set_body_goal 等）已移除，
# 不提供舊指令相容期，入口改為「📝 日常紀錄」→「⚖️ 體態」子選單，見 menu.py／commands.py
# 體態子選單首頁區塊說明。
# 2026-08-18（FR-30a）：考試管理改由 `certificate_settings:*` 選單進入，移除舊文字與 Slash 入口。
# 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md、
# docs/ADR/discuss/youtube-intel.md 對應日期條目）：YouTube 技術情報主題管理全面改選單觸發，
# 舊文字觸發詞（`/my_youtube_topics`、`/add_youtube_topic`、`/remove_youtube_topic` 等）已移除，
# 入口改為主選單「💡 Youtube 技術分享設定」，見 menu.py／commands.py 對應區塊說明。
# 2026-08-09（Step 4.1，見 robinson SPEC.md FR-33、FR-36、ADR-24 決策 2）：求職模組設定流程，
# `job_search` 開關同步改為 owner_only=True，觸發詞只放在 is_owner 分支，家人完全看不到這個功能。
# 2026-08-09（Step 4.3，見 robinson SPEC.md FR-40、ADR-27）：外部管道職缺新增流程與應徵紀錄
# 查詢指令，觸發詞位置比照求職模組設定流程，只放在 is_owner 分支。
# 2026-08-09（Step 4.3，見 robinson SPEC.md FR-39b、ADR-27）：應徵狀態更新語句，比照
# `_UPLOADED_FILE_PATTERN` 直接在這裡用 regex 一次解析，不走多輪對話狀態機。
# 2026-08-09（見 robinson SPEC.md FR-35e、FR-38e、ADR-24 後果、ADR-26）：帶動態檔名的觸發詞，
# 依副檔名/檔名關鍵字分流成兩條各自
# 獨立的回填流程——公司背景 CSV（檔名以「104職缺公司.csv」結尾）與職缺推薦 Excel（檔名以
# 「104職缺推薦.xlsx」結尾），不需要改動這個 regex 本身，只需要在下方 if/elif 各自擴充。
_UPLOADED_FILE_PATTERN = re.compile(r"^已上傳\s*(?P<filename>.+)$")
# 2026-08-02（FR-16a）：這幾個「最終執行確認」狀態是唯二不能被新語音訊息直接覆蓋清除的 flow，
# 見 handle_voice_message() 內的說明。
_FINAL_CONFIRM_FLOWS = {
    # 2026-08-17（Phase 6 第二批 2h）：體態摘要→二次確認關卡，語音只能貼出轉錄文字讓使用者
    # 確認，不能直接觸發這幾個「最終執行確認」狀態，見 handle_voice_message() 內的說明。
    "pending_body_height_confirm",
    "pending_body_waist_confirm",
    "pending_body_weight_confirm",
    "body_weight_delete_confirm",
    "pending_goal_confirm",
    "goal_delete_confirm",
    # 2026-08-17（批次3，FR-45a）：記帳／收藏清單目標摘要→二次確認關卡，理由同上。
    "pending_module_goal_confirm",
    "module_goal_delete_confirm",
    # 2026-08-18（批次5）：記帳摘要→二次確認關卡與預算月份覆蓋確認關卡，理由同上。
    "pending_transaction_confirm",
    "finance_transaction_delete_confirm",
    "pending_finance_budget_global_confirm",
    "pending_finance_budget_override_confirm",
}


def _entry_feature(data: str) -> str | None:
    if data.startswith("daily_log:"):
        return data.removeprefix("daily_log:")
    if data.startswith("menu:"):
        key = data.removeprefix("menu:")
        return None if key in {"main", "rule", "query", "schedule", "permission", "recovered"} else key
    return None


def _draft_resume_prompt(feature: str, summary: str) -> tuple[str, dict]:
    return (
        f"這個功能還有一份 30 分鐘內的草稿：\n{summary}\n\n要怎麼處理？",
        {"inline_keyboard": [
            [{"text": "✅ 繼續編輯", "callback_data": "draft:resume"}],
            [{"text": "🗑 放棄草稿", "callback_data": "draft:discard"}],
        ]},
    )


def _draft_switch_prompt(summary: str) -> tuple[str, dict]:
    return (
        f"目前功能還有未送出草稿：\n{summary}\n\n要怎麼處理？",
        {"inline_keyboard": [
            [{"text": "💾 保留草稿並切換", "callback_data": "draft:switch_keep"}],
            [{"text": "🗑 放棄草稿並切換", "callback_data": "draft:switch_discard"}],
            [{"text": "✏️ 繼續編輯", "callback_data": "draft:switch_continue"}],
        ]},
    )


def handle_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str | None,
    llm_client=None,
    text_llm_client=None,
    image_llm_clients: list | None = None,
    via_voice: bool = False,
    privacy_llm_client=None,
    telegram_client=None,
    calendar_client=None,
    gdrive_client=None,
) -> str:
    """處理一則來自 Telegram 的文字訊息，回傳要回覆的文字。

    `llm_client`（`GEMINI_API_BOT_KEY`）在訊息落入一般聊天核心時使用；`text_llm_client`
    保留供其他既有文字分析流程注入。`image_llm_clients`
    （`GEMINI_API_IMAGE_KEY1`/`KEY2`，見 robinson SPEC.md ADR-13）只有在使用者處於圖片辨識反問
    澄清流程（`pending_image_confirm`）時才會用到，其餘指令/對話流程分支都不需要；正式環境一律由
    webhook.py 注入，這裡預設 None 只是為了讓不涉及該流程的既有測試不用逐一補上假的 LLM Client。

    `via_voice`：這則文字是不是語音轉出來的——由
    `handle_voice_message()` 呼叫這裡時固定傳 `True`，webhook.py 處理一般文字訊息時維持預設的
    `False`。只有仍有效的 `pending_*_final_confirm` 高風險狀態會用到，見
    `_dispatch_active_flow()`；其餘分支不受影響。

    `privacy_llm_client`（2026-08-02，見 docs/specs/privacy-masking/SPEC.md）：個資遮蔽 LLM 語意層
    專用的獨立 Key，只會透傳到 `chat.handle_chat_message()`（見該函式 docstring）；`None` 時遮蔽
    只跑免費的 Regex 層，不影響其餘指令/對話流程分支。

    `telegram_client`：康復通知確認 callback 會用到，其餘分支不需要。

    `calendar_client`（2026-08-05，見 robinson SPEC.md FR-66a、ADR-17）：`pending_todo_calendar_sync`
    （建立事件）與 `pending_todo_action_confirm`（標記完成/取消時刪除對應事件）這兩個分支會用到；
    `None` 時優雅降級成「待辦事項照常記錄，但不會出現在 Google Calendar 上」，不影響其餘分支。

    `gdrive_client`（2026-08-09，見 robinson SPEC.md FR-35e）：`_UPLOADED_FILE_PATTERN`（「已上傳
    XXX」）這個分支會用到，至 Drive 資料夾下載 Robin 回填好的公司背景 CSV；`None` 時這個分支
    會因為呼叫端沒給 Client 而丟例外，屬於預期外狀況（正式環境一律由 webhook.py 注入），跟其餘
    分支預設 `None` 可優雅降級的情況不同。
    """
    text = (text or "").strip()
    is_owner = auth.is_owner(telegram_user_id)

    if text in _START_TRIGGERS:
        # 2026-08-15（FR-6a）：/start 是唯一保留的 Slash Command，Owner 直接顯示主選單；
        # 一般使用者若尚未綁定，進入「等待通關密碼」狀態，下一則文字才會被當成密碼驗證
        # （FR-3：只有按了 START 之後，下一則文字才進入通關密碼驗證）。
        state_store.clear(telegram_user_id)
        if is_owner:
            auth.get_or_create_owner(db, telegram_user_id)
            return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=True)

        user = auth.find_user_by_telegram_id(db, telegram_user_id)
        if user is None:
            state_store.set(telegram_user_id, {"flow": "awaiting_passcode"})
            return _AWAITING_PASSCODE_REPLY
        return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=False)

    if is_owner:
        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(
                db, state_store, telegram_user_id, text, state,
                llm_client, text_llm_client, image_llm_clients, via_voice, privacy_llm_client, telegram_client,
                calendar_client,
            )

        # Robin 免通關密碼視為管理者兼使用者，確保他一定有一筆 users 記錄（FR-5）
        owner_row = auth.get_or_create_owner(db, telegram_user_id)
        user_id = owner_row["id"]

        uploaded_match = _UPLOADED_FILE_PATTERN.match(text)
        if uploaded_match:
            filename = uploaded_match.group("filename").strip()
            if filename.endswith("104職缺公司.csv"):
                # 2026-08-09（FR-35e）：Robin 回填好公司背景 CSV 上傳 Drive 後的觸發詞。
                # `gdrive_client` 為選配（見 webhook.py `_build_gdrive_client_optional()`），
                # 環境變數還沒設定完整時優雅降級，不讓整個文字訊息處理流程失敗。
                if gdrive_client is None:
                    return "Drive 服務目前還沒設定好，沒辦法幫你回填公司背景，麻煩稍後再試一次！"
                return commands.handle_company_csv_uploaded(db, gdrive_client, filename)
            if filename.endswith("104職缺推薦.xlsx"):
                # 2026-08-09（Step 4.2，FR-38e）：Robin 回填好「是否喜歡」的職缺推薦 Excel 上傳
                # Drive 後的觸發詞，跟公司背景 CSV 是各自獨立的分流，設計完全對稱。
                if gdrive_client is None:
                    return "Drive 服務目前還沒設定好，沒辦法幫你回填職缺喜好，麻煩稍後再試一次！"
                return commands.handle_job_recommendation_excel_uploaded(db, gdrive_client, filename)
    else:
        user = auth.find_user_by_telegram_id(db, telegram_user_id)
        if user is None:
            state = state_store.get(telegram_user_id)
            if state is not None and state.get("flow") == "awaiting_passcode":
                if auth.try_bind_invite_code(db, telegram_user_id, text):
                    bound_user = auth.find_user_by_telegram_id(db, telegram_user_id)
                    toggles.ensure_default_toggles(db, bound_user["id"])
                    state_store.clear(telegram_user_id)
                    return templates.APPENDIX_A_TEXT
                return _PASSCODE_BIND_FAILED_REPLY
            return _NOT_BOUND_REPLY

        state = state_store.get(telegram_user_id)
        if state is not None:
            return _dispatch_active_flow(
                db, state_store, telegram_user_id, text, state,
                llm_client, text_llm_client, image_llm_clients, via_voice, privacy_llm_client, telegram_client,
                calendar_client,
            )

        user_id = user["id"]

    if text in _FRIEND_CHAT_TRIGGERS:
        # 2026-08-08（Step 3.5，見 robinson SPEC.md FR-51、FR-52、ADR-22）：好友模式陪伴聊天，
        # 單次生成完整回覆，不需要對話狀態機。
        return commands.start_friend_chat(db, llm_client, user_id)
    entry = feature_entry.detect(text, is_owner=is_owner)
    if entry is not None:
        return feature_entry.confirmation(entry)

    return chat.handle_chat_message(
        db, llm_client, text_llm_client, state_store, telegram_user_id, user_id, text,
        privacy_llm_client=privacy_llm_client,
    )


def handle_callback_query(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    data: str,
    calendar_client=None,
    llm_client=None,
    text_llm_client=None,
    image_llm_clients: list | None = None,
    privacy_llm_client=None,
    telegram_client=None,
    gdrive_client=None,
) -> tuple[str, dict | None]:
    """處理按下 Inline Keyboard 按鈕觸發的 callback_query（見 FR-6c：任何選單／callback 都要
    重新驗證權限，不能只靠「一開始選單沒顯示這顆按鈕」來擋，避免偽造 callback_data 繞過）。

    回傳 `(text, reply_markup)`，`reply_markup` 可能為 `None`（例如權限管理選單分派後的
    引導式文字提問，本來就不需要再帶按鈕）。

    `calendar_client`（2026-08-16，Phase 6 第二批 2f，見 robinson SPEC.md FR-66a、ADR-17）：
    待辦事項「✅ 確認送出」（`todo:confirm_save`）與清單「✅ 完成」「🚫 取消」（`todo:complete:<id>`
    ／`todo:cancel:<id>`）這三個 callback 會用到；`None` 時優雅降級成「待辦事項照常記錄/更新，
    但不會出現在 Google Calendar 上」，不影響其餘分支。

    `llm_client`／`text_llm_client`／`image_llm_clients`／`privacy_llm_client`／`telegram_client`／
    `gdrive_client`（2026-08-16，全站語音確認機制）：只有 `voice_confirm:accept` 這個 callback
    會用到——使用者確認語音轉錄內容正確後，要接回原本卡在的流程（可能是任何一個既有 pending
    flow，甚至是自由聊天），因此需要跟文字訊息分支一樣完整的一套 Client；其餘既有 callback
    分支都不需要，`None` 時不影響。呼叫端（webhook.py）比照文字訊息分支注入。
    """
    is_owner = auth.is_owner(telegram_user_id)

    if data.startswith("draft:"):
        pending = state_store.get(telegram_user_id) or {}
        flow = pending.get("flow")
        source_feature = pending.get("source_feature")
        target_feature = pending.get("target_feature")
        target_callback = pending.get("target_callback")
        if data == "draft:resume" and flow == "pending_draft_resume" and target_feature:
            draft = state_store.restore_draft(telegram_user_id, target_feature)
            if draft is not None:
                return "已恢復草稿，請繼續完成剛才的步驟。", None
        if data == "draft:discard" and flow == "pending_draft_resume" and target_feature and target_callback:
            state_store.discard_draft(telegram_user_id, target_feature)
            state_store.clear(telegram_user_id)
            return handle_callback_query(db, state_store, telegram_user_id, target_callback)
        if data == "draft:switch_continue" and flow == "pending_feature_switch" and source_feature:
            state_store.restore_draft(telegram_user_id, source_feature)
            return "已回到原本草稿，請繼續完成剛才的步驟。", None
        if data in {"draft:switch_keep", "draft:switch_discard"} and flow == "pending_feature_switch" and target_callback:
            if data == "draft:switch_discard" and source_feature:
                state_store.discard_draft(telegram_user_id, source_feature)
            state_store.clear(telegram_user_id)
            return handle_callback_query(db, state_store, telegram_user_id, target_callback)
        return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)

    if data == "feature_entry:cancel":
        return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)
    if data.startswith("feature_entry:open:"):
        key = data.removeprefix("feature_entry:open:")
        entry = feature_entry.by_key(key, is_owner=is_owner)
        if entry is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        return handle_callback_query(
            db,
            state_store,
            telegram_user_id,
            entry.callback_data,
            calendar_client=calendar_client,
            llm_client=llm_client,
            text_llm_client=text_llm_client,
            image_llm_clients=image_llm_clients,
            privacy_llm_client=privacy_llm_client,
            telegram_client=telegram_client,
            gdrive_client=gdrive_client,
        )

    target_feature = _entry_feature(data)
    if target_feature is not None:
        active_feature = state_store.active_feature(telegram_user_id)
        if active_feature and active_feature != target_feature:
            active_state = state_store.get(telegram_user_id) or {}
            draft = state_store.get_draft(telegram_user_id, active_feature)
            if draft is not None:
                state_store.clear(telegram_user_id, preserve_draft=True)
                state_store.set(telegram_user_id, {
                    "flow": "pending_feature_switch",
                    "source_feature": active_feature,
                    "target_feature": target_feature,
                    "target_callback": data,
                })
                return _draft_switch_prompt(state_store.summarize(active_state))
        if active_feature is None:
            draft = state_store.get_draft(telegram_user_id, target_feature)
            if draft is not None:
                state_store.set(telegram_user_id, {
                    "flow": "pending_draft_resume",
                    "target_feature": target_feature,
                    "target_callback": data,
                })
                return _draft_resume_prompt(target_feature, state_store.summarize(draft))

    if data == "voice_confirm:accept":
        # 2026-08-16（全站語音確認機制）：使用者按下「✅ 正確，繼續」，把轉錄前的
        # `resume_state` 還原回去，改用轉錄出來的文字接回原本流程（或自由聊天）。
        state = state_store.get(telegram_user_id)
        if state is None or state.get("flow") != "pending_voice_confirm":
            return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)
        resume_state = state.get("resume_state")
        transcribed_text = state.get("transcribed_text", "")
        if resume_state is None:
            state_store.clear(telegram_user_id)
        else:
            state_store.set(telegram_user_id, resume_state)
        result = handle_message(
            db, state_store, telegram_user_id, transcribed_text,
            llm_client=llm_client, text_llm_client=text_llm_client, image_llm_clients=image_llm_clients,
            via_voice=True, privacy_llm_client=privacy_llm_client, telegram_client=telegram_client,
            calendar_client=calendar_client, gdrive_client=gdrive_client,
        )
        if isinstance(result, tuple):
            return result
        return result, None

    # 一般對話只保留目前對話頁面的短期上下文；切換到任何選單即清除。
    chat.clear_short_context(telegram_user_id)

    if data == "menu:main":
        state_store.clear(telegram_user_id)
        return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)

    if data.startswith("menu:"):
        key = data[len("menu:") :]
        if not menu.is_valid_menu_key(key):
            return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)
        if menu.is_owner_only_key(key) and not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()

        if key == "rule":
            return commands.handle_rule(), menu.back_to_main_menu_keyboard()
        if key == "permission":
            return commands.start_permission_menu()
        if key == "todo":
            # 2026-08-16（Phase 6 第二批 2f，FR-6e）：待辦事項子選單首頁。
            state_store.clear(telegram_user_id)
            return commands.start_todo_menu()
        if key == "important_days":
            state_store.clear(telegram_user_id)
            return important_days.start_important_days_menu()
        if key == "collections":
            # 2026-08-16（Phase 6 第二批 2d，FR-6e）：收藏與旅遊子選單首頁。
            state_store.clear(telegram_user_id)
            return collections.start_collections_menu()
        if key == "achievements":
            # 2026-08-16（Phase 6 第二批 2e，FR-6e）：成果展示子選單首頁。
            state_store.clear(telegram_user_id)
            return achievements.start_achievements_menu()
        if key == "daily_log":
            state_store.clear(telegram_user_id)
            return menu.DAILY_LOG_MENU_TEXT, menu.build_daily_log_menu_keyboard()
        if key == "goal_tracking":
            # 2026-08-17（批次3，FR-45a）：🎯 目標追蹤主選單首頁。
            state_store.clear(telegram_user_id)
            return commands.start_goal_tracking_menu()
        if key == "query":
            # 2026-08-18（批次4，FR-9c／FR-9d）：🔍 資料查詢子選單首頁，直接進入日期選擇。
            return query.start_query_menu(state_store, telegram_user_id)
        if key == "schedule":
            state_store.clear(telegram_user_id)
            return schedule_settings.start_menu(is_owner=is_owner)
        if key == "tech_intel":
            # 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md、
            # docs/ADR/discuss/youtube-intel.md 對應日期條目）：YouTube 主題設定子選單首頁。
            state_store.clear(telegram_user_id)
            user = _get_identified_user(db, telegram_user_id)
            if user is None:
                return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
            if not toggles.is_feature_enabled(db, user["id"], key):
                return schedule_settings.feature_disabled_reply(key)
            return commands.start_youtube_settings_menu(db, user["id"])
        if key == "job_search":
            state_store.clear(telegram_user_id)
            user = _get_identified_user(db, telegram_user_id)
            if user is None:
                return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
            if not toggles.is_feature_enabled(db, user["id"], key):
                return schedule_settings.feature_disabled_reply(key)
            return job_settings.start_menu()
        if key == "certificate":
            state_store.clear(telegram_user_id)
            user = _get_identified_user(db, telegram_user_id)
            if user is None:
                return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
            if not toggles.is_feature_enabled(db, user["id"], key):
                return schedule_settings.feature_disabled_reply(key)
            return certificate_settings.start_menu()
        if key == "recovered":
            state_store.clear(telegram_user_id)
            return recovery_notifications.start_menu(db)
        if key == "system_errors":
            state_store.clear(telegram_user_id)
            return system_error_management.start_menu(db)
        return menu.not_yet_implemented_reply()

    if data.startswith("schedule:"):
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("schedule:") :]
        if action == "notifications":
            return schedule_settings.notification_menu(db, user["id"], is_owner=is_owner)
        if action.startswith("notification:"):
            return schedule_settings.toggle_notification(
                db, user["id"], action[len("notification:") :], is_owner=is_owner
            )
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        if action == "features":
            return schedule_settings.feature_menu(db, user["id"])
        if action.startswith("feature:"):
            return schedule_settings.toggle_feature(db, user["id"], action[len("feature:") :])
        if action == "system":
            return schedule_settings.system_jobs_menu()
        return schedule_settings.start_menu(is_owner=is_owner)

    if data.startswith("recovery:"):
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("recovery:") :]
        if action.startswith("incident:"):
            return recovery_notifications.select_incident(
                db, state_store, telegram_user_id, int(action.rsplit(":", 1)[1])
            )
        if action.startswith("toggle:"):
            return recovery_notifications.toggle(
                db, state_store, telegram_user_id, int(action.rsplit(":", 1)[1])
            )
        if action == "preview":
            return recovery_notifications.preview(db, state_store, telegram_user_id)
        if action == "confirm":
            return recovery_notifications.confirm(db, state_store, telegram_user_id, telegram_client)
        if action == "cancel":
            return recovery_notifications.cancel(state_store, telegram_user_id)
        return recovery_notifications.start_menu(db)

    if data.startswith("system_errors:"):
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("system_errors:") :]
        if action == "menu":
            state_store.clear(telegram_user_id)
            return system_error_management.start_menu(db)
        if action.startswith("list:"):
            _, status, page = action.split(":")
            return system_error_management.list_reports(db, status, int(page))
        if action.startswith("detail:"):
            return system_error_management.detail(db, int(action.rsplit(":", 1)[1]))
        if action.startswith("resolve:"):
            return system_error_management.start_resolution(
                db, state_store, telegram_user_id, int(action.rsplit(":", 1)[1])
            )
        if action == "confirm":
            return system_error_management.confirm(db, state_store, telegram_user_id, user["id"])
        if action == "edit":
            return system_error_management.edit(state_store, telegram_user_id)
        if action == "cancel":
            return system_error_management.cancel(state_store, telegram_user_id)
        return system_error_management.start_menu(db)

    if data.startswith("daily_log:"):
        # 2026-08-16（Phase 6 第二批 2c，FR-6e）：日常紀錄第二層子選單分派。
        key = data[len("daily_log:") :]
        if not menu.is_valid_daily_log_key(key):
            return menu.DAILY_LOG_MENU_TEXT, menu.build_daily_log_menu_keyboard()
        state_store.clear(telegram_user_id)
        if key == "mood":
            return commands.start_mood_menu()
        if key == "exercise":
            return commands.start_exercise_menu()
        if key == "diet":
            # 2026-08-16（Phase 6 第二批 2g）。
            return commands.start_diet_menu()
        if key == "body":
            # 2026-08-17（Phase 6 第二批 2h）。
            return commands.start_body_menu()
        if key == "finance":
            # 2026-08-18（批次5）。
            return commands.start_finance_menu()
        return menu.daily_log_not_yet_implemented_reply()

    if data.startswith("permission:"):
        action = data[len("permission:") :]
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        return commands.handle_permission_callback(db, state_store, telegram_user_id, action)

    if data.startswith("todo:"):
        # 2026-08-16（Phase 6 第二批 2f，FR-6e／FR-31／FR-31a／FR-32／FR-66a）：待辦事項選單、
        # 清單標記完成/取消、新增流程最後一輪的摘要確認。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("todo:") :]
        if action == "list":
            return commands.start_todo_list(db, user["id"])
        if action == "add":
            return commands.start_todo_new(state_store, telegram_user_id, user["id"]), None
        if action.startswith("complete:"):
            todo_id = int(action[len("complete:") :])
            return commands.handle_todo_status_action(db, user["id"], todo_id, "completed", calendar_client=calendar_client)
        if action.startswith("cancel:"):
            todo_id = int(action[len("cancel:") :])
            return commands.handle_todo_status_action(db, user["id"], todo_id, "cancelled", calendar_client=calendar_client)
        if action == "confirm_save":
            return commands.handle_todo_confirm_save(db, state_store, telegram_user_id, calendar_client=calendar_client)
        # 未知的待辦事項子動作，導回子選單而不是整個拋例外，比照其餘 callback 的保守做法。
        return commands.start_todo_menu()

    if data.startswith("important_days:"):
        # 2026-08-15（Phase 6 第二批 2b，FR-6e／FR-6h）：重要日子選單與清單操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("important_days:") :]
        if action == "list":
            return important_days.handle_list(db, user["id"])
        if action == "add":
            return important_days.start_add(state_store, telegram_user_id), None
        if action.startswith("edit:"):
            important_day_id = int(action[len("edit:") :])
            return important_days.start_edit(db, state_store, telegram_user_id, user["id"], important_day_id), None
        if action.startswith("delete:"):
            important_day_id = int(action[len("delete:") :])
            return important_days.start_delete_confirm(db, state_store, telegram_user_id, user["id"], important_day_id)
        if action.startswith("confirm_delete:"):
            important_day_id = int(action[len("confirm_delete:") :])
            return important_days.handle_delete(db, state_store, telegram_user_id, user["id"], important_day_id)
        if action == "confirm_save":
            return important_days.handle_confirm_save(db, state_store, telegram_user_id, user["id"])
        # 未知的重要日子子動作，導回子選單而不是整個拋例外，比照其餘 callback 的保守做法。
        return important_days.start_important_days_menu()

    if data.startswith("query:"):
        # 2026-08-18（批次4，FR-9c／FR-9d）：資料查詢日期選擇、模組複選與開始查詢。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("query:") :]
        if action in ("date:today", "date:yesterday"):
            choice = action[len("date:") :]
            return query.handle_date_quick(state_store, telegram_user_id, is_owner=is_owner, choice=choice)
        if action.startswith("module:"):
            module_key = action[len("module:") :]
            return query.handle_module_toggle(state_store, telegram_user_id, is_owner=is_owner, module_key=module_key)
        if action == "run":
            return query.handle_run(db, state_store, telegram_user_id, user, telegram_client=telegram_client)
        # 未知的資料查詢子動作，導回子選單而不是整個拋例外，比照其餘 callback 的保守做法。
        return query.start_query_menu(state_store, telegram_user_id)

    if data.startswith("goal_tracking:"):
        # 2026-08-17（批次3，FR-45a）：🎯 目標追蹤主選單，全程唯讀。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("goal_tracking:") :]
        if action.startswith("module:"):
            module_key = action[len("module:") :]
            return commands.start_goal_tracking_module(db, user["id"], module_key)
        if action.startswith("goal:"):
            _, goal_source, goal_id_text = action.split(":", 2)
            return commands.start_goal_tracking_detail(db, user["id"], goal_source, int(goal_id_text))
        if action.startswith("complete:"):
            _, goal_source, goal_id_text = action.split(":", 2)
            return commands.start_goal_complete_confirm(db, user["id"], goal_source, int(goal_id_text))
        if action.startswith("confirm_complete:"):
            _, goal_source, goal_id_text = action.split(":", 2)
            return commands.handle_goal_complete(db, user["id"], goal_source, int(goal_id_text), calendar_client), menu.back_to_main_menu_keyboard()
        return commands.start_goal_tracking_menu()

    if data.startswith("finance:"):
        # 2026-08-18（批次5，見 docs/ADR/discuss/robinson.md「批次5 開工前 SDD 計畫確認」）：
        # 記帳子選單（設定預算/新增/補記/我的記帳紀錄/我的記帳摘要）＋新增/補記流程的摘要→二次
        # 確認、按鈕式編輯/刪除、預算月份覆蓋確認按鈕；`finance:goal:*` 目標子流程沿用批次3既有的
        # `_dispatch_module_goal_callback()`，這批不動。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("finance:") :]

        if action.startswith("goal"):
            return _dispatch_module_goal_callback(
                db, state_store, telegram_user_id, user["id"], "finance", action, calendar_client=calendar_client
            )

        if action == "menu":
            state_store.clear(telegram_user_id)
            return commands.start_finance_menu()
        if action == "budget":
            return commands.start_finance_budget(state_store, telegram_user_id, user["id"]), None
        if action == "budget_confirm_save":
            return commands.handle_finance_budget_global_confirm_save(state_store, telegram_user_id), None
        if action == "budget_override_confirm_save":
            return commands.handle_finance_budget_override_confirm_save(state_store, telegram_user_id), None
        if action == "add":
            return commands.start_finance_add(state_store, telegram_user_id, user["id"]), None
        if action == "backfill":
            return commands.start_finance_backfill(state_store, telegram_user_id, user["id"]), None
        if action == "confirm_save":
            return commands.handle_transaction_confirm_save(db, state_store, telegram_user_id)
        if action == "list":
            return commands.handle_finance_list(db, user["id"])
        if action.startswith("edit:"):
            transaction_id = int(action[len("edit:") :])
            return commands.start_transaction_edit(db, state_store, telegram_user_id, user["id"], transaction_id), None
        if action.startswith("delete:"):
            transaction_id = int(action[len("delete:") :])
            return commands.start_transaction_delete_confirm(db, state_store, telegram_user_id, user["id"], transaction_id)
        if action.startswith("confirm_delete:"):
            transaction_id = int(action[len("confirm_delete:") :])
            return (
                commands.handle_transaction_delete(db, state_store, telegram_user_id, user["id"], transaction_id),
                menu.back_to_main_menu_keyboard(),
            )
        if action == "summary":
            return commands.handle_finance_summary(db, user["id"])
        return commands.start_finance_menu()

    if data.startswith("collections:"):
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-75）：收藏清單選單與 CRUD 操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("collections:") :]
        if action.startswith("goal"):
            # 2026-08-17（批次3，FR-45a）：收藏清單目標子流程，共用 module_goals。
            return _dispatch_module_goal_callback(
                db, state_store, telegram_user_id, user["id"], "collections", action, calendar_client=calendar_client
            )
        if action == "list":
            return collections.handle_list(db, user["id"])
        if action == "add":
            return collections.start_add(state_store, telegram_user_id)
        if action.startswith("edit:"):
            item_id = int(action[len("edit:") :])
            return collections.start_edit(db, state_store, telegram_user_id, user["id"], item_id), None
        if action.startswith("delete:"):
            item_id = int(action[len("delete:") :])
            return collections.start_delete_confirm(db, state_store, telegram_user_id, user["id"], item_id)
        if action.startswith("confirm_delete:"):
            item_id = int(action[len("confirm_delete:") :])
            return collections.handle_delete(db, state_store, telegram_user_id, user["id"], item_id)
        if action.startswith("visit:"):
            # 2026-08-16（Phase 6 第二批 2d 補修，見 docs/ADR/debug/robinson.md）：標記已造訪，
            # 不經行程直接把收藏加入探索地圖。
            item_id = int(action[len("visit:") :])
            return collections.start_visit(db, state_store, telegram_user_id, user["id"], item_id)
        if action == "geocode":
            return collections.handle_geocode_choice(db, state_store, telegram_user_id, True)
        if action == "skip_geocode":
            return collections.handle_geocode_choice(db, state_store, telegram_user_id, False)
        if action == "confirm_save":
            return collections.handle_confirm_save(db, state_store, telegram_user_id, user["id"])
        return collections.start_collections_menu()

    if data.startswith("trips:"):
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-74／FR-74a）：旅遊行程選單與 CRUD 操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("trips:") :]
        if action == "list":
            return trips.handle_list(db, user["id"])
        if action == "add":
            return trips.start_add(state_store, telegram_user_id), None
        if action.startswith("edit:"):
            trip_id = int(action[len("edit:") :])
            return trips.start_edit(db, state_store, telegram_user_id, user["id"], trip_id), None
        if action.startswith("delete:"):
            trip_id = int(action[len("delete:") :])
            return trips.start_delete_confirm(db, state_store, telegram_user_id, user["id"], trip_id)
        if action.startswith("confirm_delete:"):
            trip_id = int(action[len("confirm_delete:") :])
            return trips.handle_delete(db, state_store, telegram_user_id, user["id"], trip_id)
        if action.startswith("confirm:"):
            trip_id = int(action[len("confirm:") :])
            return trips.handle_set_status(db, user["id"], trip_id, "confirmed")
        if action.startswith("cancel:"):
            trip_id = int(action[len("cancel:") :])
            return trips.handle_set_status(db, user["id"], trip_id, "cancelled")
        if action.startswith("complete:"):
            trip_id = int(action[len("complete:") :])
            return trips.start_complete_select(db, state_store, telegram_user_id, user["id"], trip_id)
        if action.startswith("complete_toggle:"):
            collection_id = int(action[len("complete_toggle:") :])
            return trips.handle_complete_toggle(state_store, telegram_user_id, collection_id)
        if action.startswith("complete_confirm:"):
            trip_id = int(action[len("complete_confirm:") :])
            return trips.handle_complete_confirm(db, state_store, telegram_user_id, user["id"], trip_id)
        if action.startswith("toggle_item:"):
            collection_id = int(action[len("toggle_item:") :])
            return trips.handle_toggle_item(state_store, telegram_user_id, collection_id)
        if action == "items_done":
            return trips.handle_items_done(state_store, telegram_user_id)
        if action == "confirm_save":
            return trips.handle_confirm_save(db, state_store, telegram_user_id, user["id"])
        return trips.handle_list(db, user["id"])

    if data.startswith("achievements:"):
        # 2026-08-16（Phase 6 第二批 2e，FR-6e／FR-6h／FR-76／FR-76a）：成果展示選單與
        # 候選確認操作。候選機制維持被動，開啟清單（action == "list"）時才由
        # `AppLifeExplorationService.list_achievements()` 內建重新掃描；刪除直接執行，
        # 沒有二次確認流程（見 achievements.py 模組 docstring）。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("achievements:") :]
        if action == "list":
            return achievements.handle_list(db, user["id"])
        if action == "add":
            return achievements.start_add(state_store, telegram_user_id), None
        if action.startswith("delete:"):
            achievement_id = int(action[len("delete:") :])
            return achievements.handle_delete(db, user["id"], achievement_id)
        if action.startswith("pin:"):
            achievement_id = int(action[len("pin:") :])
            return achievements.handle_pin(db, user["id"], achievement_id, True)
        if action.startswith("unpin:"):
            achievement_id = int(action[len("unpin:") :])
            return achievements.handle_pin(db, user["id"], achievement_id, False)
        if action.startswith("candidate_accept:"):
            candidate_id = int(action[len("candidate_accept:") :])
            return achievements.handle_candidate_decision(db, user["id"], candidate_id, True)
        if action.startswith("candidate_reject:"):
            candidate_id = int(action[len("candidate_reject:") :])
            return achievements.handle_candidate_decision(db, user["id"], candidate_id, False)
        if action == "confirm_save":
            return achievements.handle_confirm_save(db, state_store, telegram_user_id, user["id"])
        return achievements.start_achievements_menu()

    if data.startswith("certificate_settings:"):
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("certificate_settings:") :]
        if action == "menu":
            state_store.clear(telegram_user_id)
            return certificate_settings.start_menu()
        if action == "profiles":
            return certificate_settings.start_profiles(db, user["id"])
        if action == "profile:add":
            return certificate_settings.start_profile_add(state_store, telegram_user_id, user["id"]), None
        if action == "profile:confirm_add":
            return certificate_settings.confirm_profile_add(db, state_store, telegram_user_id)
        if action.startswith("profile:confirm_toggle:"):
            return certificate_settings.confirm_profile_toggle(db, state_store, telegram_user_id, user["id"], int(action.rsplit(":", 1)[1]))
        if action.startswith("profile:toggle:"):
            return certificate_settings.start_profile_toggle(db, state_store, telegram_user_id, user["id"], int(action.rsplit(":", 1)[1]))
        if action.startswith("profile:"):
            return certificate_settings.start_profile_detail(db, user["id"], int(action.rsplit(":", 1)[1]))
        if action == "goals":
            return certificate_settings.start_goals(db, user["id"])
        if action == "goal:confirm":
            return certificate_settings.confirm_goal(db, state_store, telegram_user_id)
        if action.startswith("goal:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return (certificate_settings.start_goal_set(state_store, telegram_user_id, user["id"], profile), None) if profile else certificate_settings.start_goals(db, user["id"])
        if action == "daily":
            return certificate_settings.start_daily(db, user["id"])
        if action == "quiz:start":
            return commands.start_quiz_answer(db, state_store, telegram_user_id, user["id"]), None
        if action == "daily:confirm":
            return certificate_settings.confirm_daily(db, state_store, telegram_user_id)
        if action.startswith("daily:set:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return (certificate_settings.start_daily_set(state_store, telegram_user_id, user["id"], profile), None) if profile else certificate_settings.start_daily(db, user["id"])
        if action == "range:confirm":
            return certificate_settings.confirm_range(db, state_store, telegram_user_id)
        if action.startswith("range:confirm_delete:"):
            _, _, profile_id, override_id = action.split(":")
            profile = certificate_settings.profile_by_id(db, user["id"], int(profile_id))
            return certificate_settings.confirm_range_delete(db, state_store, telegram_user_id, user["id"], profile, int(override_id)) if profile else certificate_settings.start_daily(db, user["id"])
        if action.startswith("range:delete:"):
            _, _, profile_id, override_id = action.split(":")
            profile = certificate_settings.profile_by_id(db, user["id"], int(profile_id))
            return certificate_settings.start_range_delete(db, state_store, telegram_user_id, user["id"], profile, int(override_id)) if profile else certificate_settings.start_daily(db, user["id"])
        if action.startswith("range:edit:"):
            _, _, profile_id, override_id = action.split(":")
            profile = certificate_settings.profile_by_id(db, user["id"], int(profile_id))
            return (certificate_settings.start_range_edit(db, state_store, telegram_user_id, user["id"], profile, int(override_id)), None) if profile else certificate_settings.start_daily(db, user["id"])
        if action.startswith("range:add:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return (certificate_settings.start_range_edit(db, state_store, telegram_user_id, user["id"], profile), None) if profile else certificate_settings.start_daily(db, user["id"])
        if action.startswith("range:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return certificate_settings.start_range_list(db, user["id"], profile) if profile else certificate_settings.start_daily(db, user["id"])
        if action == "scores":
            return certificate_settings.start_scores(db, user["id"])
        if action == "score:confirm":
            return certificate_settings.confirm_score(db, state_store, telegram_user_id)
        if action.startswith("score:add:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return (certificate_settings.start_score_add(state_store, telegram_user_id, user["id"], profile), None) if profile else certificate_settings.start_scores(db, user["id"])
        if action.startswith("daily:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return certificate_settings.daily_summary(db, user["id"], profile) if profile else certificate_settings.start_daily(db, user["id"])
        if action.startswith("score:"):
            profile = certificate_settings.profile_by_id(db, user["id"], int(action.rsplit(":", 1)[1]))
            return certificate_settings.score_list(db, user["id"], profile) if profile else certificate_settings.start_scores(db, user["id"])
        return certificate_settings.start_menu()

    if data.startswith("youtube_settings:"):
        # 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md、
        # docs/ADR/discuss/youtube-intel.md 對應日期條目）：YouTube 主題設定選單與新增／移除操作，
        # 設計比照 collections.py／achievements.py 的單層子選單＋二次確認刪除模式。僅 Owner 可用
        # （`tech_intel` 主選單項目本身是 owner_only，這裡再檢查一次身分保守起見）。
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("youtube_settings:") :]
        if action == "menu":
            state_store.clear(telegram_user_id)
            return commands.start_youtube_settings_menu(db, user["id"])
        if action == "add":
            return commands.start_youtube_topic_add(db, state_store, telegram_user_id, user["id"])
        if action == "remove":
            return commands.start_youtube_topic_remove_menu(db, user["id"])
        if action.startswith("remove_select:"):
            topic_id = int(action[len("remove_select:") :])
            return commands.start_youtube_topic_remove_confirm(db, state_store, telegram_user_id, user["id"], topic_id)
        if action.startswith("confirm_remove:"):
            topic_id = int(action[len("confirm_remove:") :])
            return commands.handle_youtube_topic_remove_confirmed(db, state_store, telegram_user_id, user["id"], topic_id)
        return commands.start_youtube_settings_menu(db, user["id"])

    if data.startswith("job_search:"):
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("job_search:") :]
        if action == "menu":
            state_store.clear(telegram_user_id)
            return job_settings.start_menu()
        if action.startswith("profile:"):
            parts = action.split(":")
            if len(parts) == 2 and parts[1] in ("resume", "expectation"):
                return job_settings.start_profile_menu(db, user["id"], parts[1])
            if len(parts) == 3 and parts[1] == "edit" and parts[2] in ("resume", "expectation"):
                return job_settings.start_profile_edit(state_store, telegram_user_id, user["id"], parts[2]), None
            if len(parts) == 3 and parts[1] == "clear" and parts[2] in ("resume", "expectation"):
                field = {"resume": "job_resume", "expectation": "job_expectation"}[parts[2]]
                return job_settings.start_profile_clear_confirm(db, state_store, telegram_user_id, user["id"], field)
            if len(parts) == 3 and parts[1] == "confirm_clear" and parts[2] in ("resume", "expectation"):
                field = {"resume": "job_resume", "expectation": "job_expectation"}[parts[2]]
                return job_settings.handle_profile_clear_confirm(db, state_store, telegram_user_id, user["id"], field), menu.back_to_main_menu_keyboard()
        if action == "requirements":
            return job_settings.start_requirements(db, state_store, telegram_user_id, user["id"])
        if action == "requirements:edit":
            return job_settings.start_requirements_edit(state_store, telegram_user_id, user["id"]), None
        if action == "criteria":
            return job_settings.start_criteria_menu(db, user["id"])
        if action == "criteria:add":
            return job_settings.start_criteria_add(state_store, telegram_user_id, user["id"]), None
        if action.startswith("criteria:delete:"):
            return job_settings.start_criteria_delete_confirm(state_store, telegram_user_id, user["id"], int(action.rsplit(":", 1)[1]))
        if action.startswith("criteria:confirm_delete:"):
            return job_settings.handle_criteria_delete_confirm(db, state_store, telegram_user_id, user["id"], int(action.rsplit(":", 1)[1])), menu.back_to_main_menu_keyboard()
        if action.startswith("criteria:edit:"):
            return job_settings.start_criteria_edit(db, state_store, telegram_user_id, user["id"], int(action.rsplit(":", 1)[1]))
        if action == "jobs":
            return job_settings.start_jobs_list(db)
        if action.startswith("jobs:page:"):
            return job_settings.start_jobs_list(db, page=int(action.rsplit(":", 1)[1]))
        if action.startswith("status:"):
            parts = action.split(":")
            if len(parts) == 2 and parts[1] in {"applied", "interview", "offer"}:
                return job_settings.start_status_list(db, parts[1])
            if len(parts) == 3 and parts[1] == "select":
                return job_settings.start_status_update(parts[2])
            if len(parts) == 4 and parts[1] == "set" and parts[3] in {"applied", "interview", "offer", "rejected"}:
                if job_search.record_application_status(db, parts[2], parts[3]):
                    return f"已更新為「{job_search.application_status_label(parts[3])}」。", menu.back_to_main_menu_keyboard()
                return "找不到對應職缺。", menu.back_to_main_menu_keyboard()
        if action == "closed":
            return job_settings.start_closed_list(db)
        if action.startswith("closed:"):
            _, mode, job_id = action.split(":", 2)
            if mode in {"open", "close"} and job_search.set_job_closed_manually(db, job_id, mode == "close"):
                return ("已標記職缺關閉。" if mode == "close" else "已重新開啟職缺。"), menu.back_to_main_menu_keyboard()
        if action == "external:add":
            return commands.start_add_external_job(state_store, telegram_user_id, user["id"]), None
        return job_settings.start_menu()

    if data.startswith("mood:"):
        # 2026-08-16（Phase 6 第二批 2c，FR-6e）：心情選單與清單操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("mood:") :]
        if action == "list":
            return commands.handle_mood_list(db, user["id"])
        if action == "new":
            return commands.start_mood_journal(state_store, telegram_user_id, user["id"]), None
        if action == "backfill":
            return commands.start_mood_backfill(state_store, telegram_user_id, user["id"]), None
        if action.startswith("edit:"):
            journal_id = int(action[len("edit:") :])
            return commands.start_mood_edit(db, state_store, telegram_user_id, user["id"], journal_id), None
        if action.startswith("delete:"):
            journal_id = int(action[len("delete:") :])
            return commands.start_mood_delete_confirm(db, state_store, telegram_user_id, user["id"], journal_id)
        if action.startswith("confirm_delete:"):
            journal_id = int(action[len("confirm_delete:") :])
            return commands.handle_mood_delete(db, state_store, telegram_user_id, user["id"], journal_id), menu.back_to_main_menu_keyboard()
        if action == "confirm_save":
            return commands.handle_mood_confirm_save(db, state_store, telegram_user_id), None
        return commands.start_mood_menu()

    if data.startswith("exercise:"):
        # 2026-08-16（Phase 6 第二批 2c，FR-6e）：運動選單與清單操作。
        # 2026-08-17（FR-47a，批次2）：新增類別選擇（cat:<id>／cat:other）、選填欄位跳過
        # （skip:heart_rate／skip:note）與熱量來源二選一（calorie:ai／calorie:manual）三組
        # callback，見 commands.py「運動」區塊模組註解。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("exercise:") :]
        if action == "list":
            return commands.handle_exercise_list(db, user["id"])
        if action == "new":
            return commands.start_exercise_log(db, state_store, telegram_user_id, user["id"])
        if action == "backfill":
            return commands.start_exercise_backfill(state_store, telegram_user_id, user["id"]), None
        if action.startswith("edit:"):
            exercise_log_id = int(action[len("edit:") :])
            return commands.start_exercise_edit(db, state_store, telegram_user_id, user["id"], exercise_log_id)
        if action.startswith("delete:"):
            exercise_log_id = int(action[len("delete:") :])
            return commands.start_exercise_delete_confirm(db, state_store, telegram_user_id, user["id"], exercise_log_id)
        if action.startswith("confirm_delete:"):
            exercise_log_id = int(action[len("confirm_delete:") :])
            return commands.handle_exercise_delete(db, state_store, telegram_user_id, user["id"], exercise_log_id), menu.back_to_main_menu_keyboard()
        if action == "cat:other":
            return commands.start_exercise_category_custom(state_store, telegram_user_id), None
        if action.startswith("cat:"):
            category_id = int(action[len("cat:") :])
            return commands.handle_exercise_category_choice(db, state_store, telegram_user_id, category_id)
        if action == "skip:heart_rate":
            return commands.handle_exercise_skip_heart_rate(state_store, telegram_user_id)
        if action == "skip:note":
            return commands.handle_exercise_skip_note(state_store, telegram_user_id)
        if action == "calorie:ai":
            return commands.handle_exercise_calorie_ai_choice(llm_client, state_store, telegram_user_id)
        if action == "calorie:manual":
            return commands.handle_exercise_calorie_manual_choice(state_store, telegram_user_id)
        if action == "confirm_save":
            return commands.handle_exercise_confirm_save(db, state_store, telegram_user_id), None
        if action == "goal":
            # 2026-08-17（Phase 6 第二批 2h）：導到體態模組共用的目標子流程，`goal_type` 預設
            # 「運動」，跳過「請選類型」那題；返回鍵導回這個運動子選單。
            return commands.start_body_goal_menu("exercise", "exercise")
        return commands.start_exercise_menu()

    if data.startswith("diet:"):
        # 2026-08-16（Phase 6 第二批 2g，FR-6e／FR-48）：飲食/飲水選單與新增流程操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("diet:") :]
        if action == "list":
            return commands.start_diet_list(db, user["id"])
        if action == "new":
            return commands.start_diet_log(db, state_store, telegram_user_id, user["id"])
        if action == "backfill":
            return commands.start_diet_backfill(state_store, telegram_user_id, user["id"]), None
        if action in ("water_yes", "water_no"):
            return commands.handle_diet_water_choice_step(state_store, telegram_user_id, action)
        if action in ("food_yes", "food_no"):
            return commands.handle_diet_food_choice_step(state_store, telegram_user_id, action)
        if action in ("food_text", "food_photo"):
            return commands.handle_diet_food_input_mode_step(state_store, telegram_user_id, action)
        if action in ("nutrition_ai", "nutrition_manual"):
            return commands.handle_diet_nutrition_source_step(llm_client, state_store, telegram_user_id, action)
        if action.startswith("edit:"):
            diet_log_id = int(action[len("edit:") :])
            return commands.start_diet_edit(db, state_store, telegram_user_id, user["id"], diet_log_id)
        if action.startswith("delete:"):
            diet_log_id = int(action[len("delete:") :])
            return commands.start_diet_delete_confirm(db, state_store, telegram_user_id, user["id"], diet_log_id)
        if action.startswith("confirm_delete:"):
            diet_log_id = int(action[len("confirm_delete:") :])
            return commands.handle_diet_delete(db, state_store, telegram_user_id, user["id"], diet_log_id), menu.back_to_main_menu_keyboard()
        if action == "confirm_save":
            return commands.handle_diet_confirm_save(db, state_store, telegram_user_id), None
        if action == "goal":
            # 2026-08-17（Phase 6 第二批 2h）：導到體態模組共用的目標子流程，`goal_type` 預設
            # 「飲食」，跳過「請選類型」那題；返回鍵導回這個飲食子選單。
            return commands.start_body_goal_menu("diet", "diet")
        return commands.start_diet_menu()

    if data.startswith("body:"):
        # 2026-08-17（Phase 6 第二批 2h，FR-6e／FR-45／FR-46）：體態子選單（身高/腰圍/體重/
        # 我的體態紀錄）與三個子功能共用的 `body:goal:*` 目標子流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("body:") :]

        if action.startswith("goal"):
            return _dispatch_body_goal_callback(db, state_store, telegram_user_id, user["id"], action, calendar_client=calendar_client)

        if action == "height":
            return commands.start_body_height(state_store, telegram_user_id, user["id"]), None
        if action == "height_confirm_save":
            return commands.handle_body_height_confirm_save(db, state_store, telegram_user_id), None
        if action == "waist":
            return commands.start_body_waist(state_store, telegram_user_id, user["id"]), None
        if action == "waist_confirm_save":
            return commands.handle_body_waist_confirm_save(db, state_store, telegram_user_id), None
        if action == "weight_new":
            return commands.start_body_weight_new(state_store, telegram_user_id, user["id"]), None
        if action == "weight_backfill":
            return commands.start_body_weight_backfill(state_store, telegram_user_id, user["id"]), None
        if action == "weight_confirm_save":
            return commands.handle_body_weight_confirm_save(db, state_store, telegram_user_id, calendar_client=calendar_client)
        if action == "summary":
            return commands.start_body_summary(db, user["id"])
        if action == "weight_list":
            return commands.handle_body_weight_list(db, user["id"])
        if action.startswith("weight_edit:"):
            weight_log_id = int(action[len("weight_edit:") :])
            return commands.start_body_weight_edit(db, state_store, telegram_user_id, user["id"], weight_log_id), None
        if action.startswith("weight_delete:"):
            weight_log_id = int(action[len("weight_delete:") :])
            return commands.start_body_weight_delete_confirm(db, state_store, telegram_user_id, user["id"], weight_log_id)
        if action.startswith("weight_confirm_delete:"):
            weight_log_id = int(action[len("weight_confirm_delete:") :])
            return commands.handle_body_weight_delete(db, state_store, telegram_user_id, user["id"], weight_log_id), menu.back_to_main_menu_keyboard()
        return commands.start_body_menu()

    # 未知／格式不符的 callback_data（例如過期或偽造），保守導回主選單，不當例外處理。
    return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)


def _get_identified_user(db: CloudSQLClient, telegram_user_id: int) -> dict | None:
    """依身分找出對應的 users 記錄；Robin（Owner）一定有記錄，其餘家人未綁定通關密碼則回傳 None。"""
    if auth.is_owner(telegram_user_id):
        return auth.get_or_create_owner(db, telegram_user_id)
    return auth.find_user_by_telegram_id(db, telegram_user_id)


def _dispatch_body_goal_callback(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, action: str, calendar_client=None
):
    """`body:goal*` callback 分派（2026-08-17，Phase 6 第二批 2h）：體重/運動/飲食三個子功能
    共用的目標子流程，不管是從「⚖️ 體態」子選單，還是從「🏃 運動」／「🍚 飲食」子選單的
    「🎯 目標」按鈕點進來的，都走這裡；`goal_type`（`-` 代表不限定）與 `source`（決定各層
    「返回」按鈕要導回哪個子選單）都直接編碼在 `callback_data` 裡，不用額外查狀態。"""
    if action == "goal":
        return commands.start_body_goal_menu(None, "body")
    if action == "goal:confirm_save":
        return commands.handle_goal_confirm_save(db, state_store, telegram_user_id, calendar_client=calendar_client), None

    parts = action[len("goal:") :].split(":")
    sub_action = parts[0]

    if sub_action == "menu":
        goal_type = None if parts[1] == "-" else parts[1]
        return commands.start_body_goal_menu(goal_type, parts[2])
    if sub_action == "new":
        goal_type = None if parts[1] == "-" else parts[1]
        return commands.start_body_goal_new(state_store, telegram_user_id, user_id, goal_type, parts[2]), None
    if sub_action == "list":
        goal_type = None if parts[1] == "-" else parts[1]
        return commands.start_body_goal_list(db, user_id, goal_type, parts[2])
    if sub_action == "edit":
        goal_id = int(parts[1])
        return commands.start_body_goal_edit(db, state_store, telegram_user_id, user_id, goal_id, parts[2]), None
    if sub_action == "delete":
        goal_id = int(parts[1])
        return commands.start_body_goal_delete_confirm(db, state_store, telegram_user_id, user_id, goal_id, parts[2])
    if sub_action == "confirm_delete":
        goal_id = int(parts[1])
        return (
            commands.handle_goal_delete(db, state_store, telegram_user_id, user_id, goal_id, calendar_client=calendar_client),
            menu.back_to_main_menu_keyboard(),
        )
    return commands.start_body_goal_menu(None, "body")


def _dispatch_module_goal_callback(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    module_key: str,
    action: str,
    calendar_client=None,
):
    """`<module_key>:goal*` callback 分派（2026-08-17，批次3）：記帳／收藏清單共用的通用目標
    子流程，結構比照 `_dispatch_body_goal_callback()`，但 `module_key` 固定寫死在 callback_data
    前綴本身（不像 body 的 `goal_type`／`source` 需要額外編碼），所以不用像 body 版本額外拆
    `source` 參數。

    `calendar_client`（2026-08-17 補做，Robin 要求不得漏做）：只有 `goal:confirm_save` 這個
    callback 會用到，`None` 時優雅降級成「目標照常記錄，但不會同步到 Google Calendar」。"""
    if action == "goal":
        return commands.start_module_goal_menu(module_key, "main" if module_key == "finance" else module_key)
    if action == "goal:menu":
        return commands.start_module_goal_menu(module_key, "main" if module_key == "finance" else module_key)
    if action == "goal:new":
        return commands.start_module_goal_new(state_store, telegram_user_id, user_id, module_key), None
    if action == "goal:list":
        return commands.start_module_goal_list(db, user_id, module_key)
    if action == "goal:confirm_save":
        return commands.handle_module_goal_confirm_save(db, state_store, telegram_user_id, calendar_client=calendar_client), None
    if action.startswith("goal:edit:"):
        goal_id = int(action[len("goal:edit:") :])
        return commands.start_module_goal_edit(db, state_store, telegram_user_id, user_id, module_key, goal_id), None
    if action.startswith("goal:delete:"):
        goal_id = int(action[len("goal:delete:") :])
        return commands.start_module_goal_delete_confirm(db, state_store, telegram_user_id, user_id, module_key, goal_id)
    if action.startswith("goal:confirm_delete:"):
        goal_id = int(action[len("goal:confirm_delete:") :])
        return commands.handle_module_goal_delete(db, state_store, telegram_user_id, user_id, goal_id), menu.back_to_main_menu_keyboard()
    return commands.start_module_goal_menu(module_key, "main" if module_key == "finance" else module_key)


def handle_photo_message(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    file_id: str,
    caption: str | None,
    telegram_client,
    gdrive_client,
    image_llm_clients: list,
    privacy_llm_client=None,
) -> str:
    """處理使用者傳來的圖片訊息（對應 robinson SPEC.md FR-17、ADR-13）。

    未綁定通關密碼者一律先擋下，不消耗任何 Drive/Gemini 額度；已綁定者才下載圖片並交給
    `src/bot/image.py` 的商業邏輯處理。若使用者原本卡在某個未完成的對話流程（例如上一輪的
    圖片澄清問答還沒回答完就又傳了新圖片），直接以新圖片覆蓋、清除舊流程狀態，避免卡死。

    2026-08-16（Phase 6 第二批 2g）：**例外**——如果使用者正卡在 `pending_diet_photo`（飲食
    子選單「📷 照片」輸入方式，等待傳照片），這張照片要走 `commands.handle_diet_photo_message()`
    複用 `src/services/app_diet_photo.py` 的飲食辨識邏輯，而不是落入下面這套一般圖片分析
    （FR-17），這兩套是不同的商業邏輯，不能混用。

    `privacy_llm_client`（2026-08-02，見 docs/specs/privacy-masking/SPEC.md FR-5）：透傳給
    `image.handle_image_message()`，用來在 `caption` 送進 Gemini 前先做個資遮蔽。
    """
    user = _get_identified_user(db, telegram_user_id)
    if user is None:
        return _NOT_BOUND_REPLY

    current_state = state_store.get(telegram_user_id)
    if current_state is not None and current_state.get("flow") == "pending_diet_photo":
        image_bytes = telegram_client.get_file_bytes(file_id)
        llm_client = image_llm_clients[0] if image_llm_clients else None
        return commands.handle_diet_photo_message(db, llm_client, state_store, telegram_user_id, image_bytes, "image/jpeg")

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
        privacy_llm_client=privacy_llm_client,
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
    is_uploaded_audio: bool = False,
    voice_lockout_store: ConversationStateStore | None = None,
    privacy_llm_client=None,
    calendar_client=None,
) -> str | tuple[str, dict | None]:
    """處理使用者傳來的 Telegram 長按語音或上傳音檔。

    2026-08-16（全站語音確認機制）：轉錄成功時回傳 `(text, keyboard)` 二元組（貼出轉錄文字＋
    「✅ 正確，繼續」按鈕），比照 `handle_callback_query()` 的回傳慣例；其餘提早擋下的分支
    （未綁定、鎖定中、超過長度限制）維持回傳純 `str`，呼叫端（webhook.py）需要
    比照文字訊息分支用 `isinstance(x, tuple)` 拆解。

    涵蓋 Telegram 的 `voice`（錄音鍵語音訊息）與 `audio`（使用者上傳的音檔）兩種類型，
    FR-17 承諾「圖片與音檔」都支援，不限定只有錄音鍵那種；`mime_type` 由呼叫端
    （webhook.py）依實際訊息類型傳入，供 `voice.transcribe_and_upload()` 決定正確的
    Drive 副檔名與轉錄請求格式（見 src/bot/voice.py 模組 docstring）。

    FR-14 的 10 分鐘上限與 5 分鐘超時鎖定只套用 Telegram 長按語音，並刻意排在下載前檢查；
    上傳音檔不套用兩項限制。通過後才下載、上傳 Drive、記錄 media_uploads 並轉錄。

    2026-08-16（全站語音確認機制，見 docs/ADR/discuss/voice-safety.md）：轉出來的文字**不會**
    再直接當成使用者「打字輸入」丟進 `handle_message()`——語音辨識結果可能跟使用者實際講的
    內容有落差，這裡改成先把轉錄文字貼出來、附一顆「✅ 正確，繼續」按鈕請使用者確認；使用者
    按下按鈕（`handle_callback_query()` 的 `voice_confirm:accept`）或直接打字修正
    （`_dispatch_active_flow()` 的 `pending_voice_confirm` 分支）之後，才會用「使用者確認過的
    文字」接回原本卡在的流程（或自由聊天），下游 `handle_message()`／各 pending flow 完全不用
    改，這是 Step 1.4 沿用至今的核心架構選擇：語音只負責「變成文字」，「文字要怎麼處理」全部
    復用既有邏輯；2026-08-16 起多插了一輪「文字先給使用者確認過」的關卡。

    2026-08-02（FR-16a）：如果目前卡在 `_FINAL_CONFIRM_FLOWS` 這幾個「最終執行確認」狀態，
    語音一定會被拒絕（這一步只接受打字），所以**在下載/轉錄之前就直接短路回覆**，比照
    FR-14「先擋才不浪費額度」的一貫原則——沒必要為了一個註定被拒絕的結果，還是先花一次
    Drive 上傳＋Groq 轉錄的額度。這裡也刻意不清除該狀態，讓使用者可以直接補一則打字訊息完成
    最終確認，不用整個流程重來。

    `voice_lockout_store`（獨立於 `state_store`
    的另一個 `ConversationStateStore` 實例，正式環境由 webhook.py 建立並長期持有）記錄「這位
    使用者最近一次是否因單次語音超過 10 分鐘而被鎖定」——5 分鐘內長按語音功能關閉。
    呼叫端沒傳的話（例如既有測試不關心這個行為）就地
    建立一個新的、不會跨呼叫共用的 store，等於停用跨呼叫鎖定檢查，不影響其餘行為。
    """
    user = _get_identified_user(db, telegram_user_id)
    if user is None:
        return _NOT_BOUND_REPLY

    voice_lockout_store = voice_lockout_store or ConversationStateStore()

    current_state = state_store.get(telegram_user_id)
    if current_state is not None and current_state.get("flow") in _FINAL_CONFIRM_FLOWS:
        # 這幾個 flow 的 `handle_*_final_confirm_step()` 收到 `via_voice=True` 時完全不會用到
        # `text` 內容（見 commands.py），這裡帶空字串即可，不需要真的轉出語音內容。
        return handle_message(db, state_store, telegram_user_id, "", via_voice=True)

    if not is_uploaded_audio:
        if voice.is_locked_out_from_duration_violation(voice_lockout_store, telegram_user_id):
            return _VOICE_DURATION_LOCKOUT_REPLY
        if voice.exceeds_duration_limit(duration_seconds):
            voice.mark_duration_violation(voice_lockout_store, telegram_user_id)
            return _VOICE_DURATION_LIMIT_REPLY

    voice_bytes = telegram_client.get_file_bytes(file_id)
    transcribed_text = voice.transcribe_and_upload(
        db, gdrive_client, voice_client, user["id"], user["role"], voice_bytes, mime_type=mime_type
    )

    # 2026-08-16（全站語音確認機制，見 docs/ADR/discuss/voice-safety.md）：語音辨識結果可能跟
    # 使用者實際講的內容有落差，轉錄成功後不直接當成輸入內容送進 handle_message()，而是先
    # 貼出轉錄文字讓使用者確認。`resume_state` 保留「轉錄前」使用者原本卡在的狀態（可能是
    # 某個 pending flow，也可能是 None＝純自由聊天），使用者確認或改用文字修正後，
    # 才照這個狀態接回（見 `_dispatch_active_flow()` 的 `pending_voice_confirm` 分支與
    # `handle_callback_query()` 的 `voice_confirm:accept` 分支）。這裡刻意排在
    # `state_store.clear()` 之前才讀出 `current_state`（本函式最上方已讀出，尚未被覆蓋）。
    state_store.set(
        telegram_user_id,
        {"flow": "pending_voice_confirm", "resume_state": current_state, "transcribed_text": transcribed_text},
    )
    reply = (
        f"我聽到的內容是：\n\n「{transcribed_text}」\n\n"
        "請問這樣正確嗎？如果正確請按下面按鈕；如果不正確，可以直接重新傳送語音，"
        "或用文字打出正確內容。"
    )
    keyboard = {"inline_keyboard": [[{"text": "✅ 正確，繼續", "callback_data": "voice_confirm:accept"}]]}
    return reply, keyboard


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
    privacy_llm_client=None,
    telegram_client=None,
    calendar_client=None,
) -> str:
    """依進行中對話流程的 `flow` 標記分派到對應處理函式（見各 flow 對應 spec 的 ADR）。"""
    flow = state.get("flow")
    if flow == "pending_voice_confirm":
        # 2026-08-16（全站語音確認機制）：使用者對著「請問這樣正確嗎？」直接打字（而不是按
        # 「✅ 正確，繼續」），視為用打字修正剛剛聽錯的內容——把狀態還原成語音進來之前
        # 原本卡在的 `resume_state`（可能是某個 pending flow，也可能是 None＝自由聊天），
        # 再用這次打的文字重新呼叫 `handle_message()`，效果等同於使用者一開始就用打字回答；
        # `via_voice=False`：這是使用者親自打的字，不是語音轉出來的，`_FINAL_CONFIRM_FLOWS`
        # 這類只接受打字的關卡也應該正常放行。
        resume_state = state.get("resume_state")
        if resume_state is None:
            state_store.clear(telegram_user_id)
        else:
            state_store.set(telegram_user_id, resume_state)
        return handle_message(
            db, state_store, telegram_user_id, text,
            llm_client=llm_client, text_llm_client=text_llm_client, image_llm_clients=image_llm_clients,
            via_voice=False, privacy_llm_client=privacy_llm_client, telegram_client=telegram_client,
            calendar_client=calendar_client,
        )
    if flow in ("permission_create", "permission_disable", "permission_enable", "permission_resend"):
        # 2026-08-15（Phase 6 第二批 2a，FR-4）：Owner 權限管理選單引導式流程。
        return commands.handle_permission_step(db, state_store, telegram_user_id, text)
    if flow in {"system_error_resolution", "system_error_resolution_confirm"}:
        return system_error_management.handle_resolution_text(state_store, telegram_user_id, text)
    if flow == "important_days":
        # 2026-08-15（Phase 6 第二批 2b，FR-6e／FR-6h）：重要日子新增／編輯多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return important_days.handle_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "important_days_delete_confirm":
        return important_days.handle_delete_confirm_text(state_store, telegram_user_id)
    if flow == "pending_query_date":
        # 2026-08-18（批次4，FR-9c）：資料查詢打字輸入最終日期。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        is_owner = bool(user.get("is_owner"))
        return query.handle_date_text(state_store, telegram_user_id, text, is_owner=is_owner, llm_client=llm_client)
    if flow == "collection":
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-75）：收藏清單新增／編輯多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return collections.handle_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "collection_delete_confirm":
        return collections.handle_delete_confirm_text(state_store, telegram_user_id)
    if flow == "collection_visit":
        # 2026-08-16（Phase 6 第二批 2d 補修，見 docs/ADR/debug/robinson.md）：標記已造訪多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return collections.handle_visit_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "trip":
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-74／FR-74a）：旅遊行程新增／編輯多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return trips.handle_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "trip_delete_confirm":
        return trips.handle_delete_confirm_text(state_store, telegram_user_id)
    if flow == "trip_complete_select":
        return trips.handle_complete_select_text(state_store, telegram_user_id)
    if flow == "achievement":
        # 2026-08-16（Phase 6 第二批 2e，FR-6e／FR-6h／FR-76）：成果展示手動新增多步驟流程。
        return achievements.handle_step(state_store, telegram_user_id, text)
    if flow == "pending_image_confirm":
        return image.handle_image_confirm_step(image_llm_clients, state_store, telegram_user_id, text)
    # 2026-08-02（Step 1.7，見 robinson SPEC.md FR-31、FR-31a、FR-32）：待辦事項新增（時間→提醒→
    # 行事曆同步→摘要確認）與查詢清單後標記完成/取消，各自對應的 flow 分派，見 commands.py
    # 模組內「待辦事項」區塊說明；2026-08-16（Phase 6 第二批 2f）新增選單按鈕入口
    # （`pending_todo_new_content`）與摘要確認關卡（`pending_todo_confirm_save`），查詢清單改
    # 按鈕式標記完成/取消，移除 `pending_todo_list_action`／`pending_todo_action_confirm`。
    if flow == "pending_todo_new_content":
        return commands.handle_todo_new_content_step(state_store, telegram_user_id, text)
    if flow == "pending_todo_confirm":
        return commands.handle_todo_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_time":
        return commands.handle_todo_time_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_reminder":
        return commands.handle_todo_reminder_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_calendar_sync":
        # 2026-08-05（FR-66a、ADR-17）：新增待辦事項流程倒數第二輪，這一輪之後才進入摘要確認。
        return commands.handle_todo_calendar_sync_step(
            db, llm_client, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
    if flow == "pending_todo_confirm_save":
        return commands.handle_todo_confirm_save_text(state_store, telegram_user_id)
    # 2026-08-02（Step 1.8，見 robinson SPEC.md FR-49、FR-50）：心情小記三輪反問流程，全程不需要
    # LLM（固定分類選單＋自由文字直接記錄），只有內容/成就這兩輪需要 privacy_llm_client 做個資遮蔽。
    if flow == "pending_mood_backfill_date":
        # 2026-08-02 追加（FR-49 補記擴充）：解析「要補記哪一天」，講清楚後接到既有的分類選單。
        return commands.handle_mood_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_mood_category":
        return commands.handle_mood_category_step(state_store, telegram_user_id, text)
    if flow == "pending_mood_content":
        return commands.handle_mood_content_step(
            state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_mood_achievement":
        return commands.handle_mood_achievement_step(
            db, state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    # 2026-08-16（Phase 6 第二批 2c）：摘要確認、刪除確認這兩個狀態只接受按鈕操作，使用者
    # 打字時直接取消流程導回日常紀錄選單，不再走 LLM 分類（理由見 commands.py 對應函式註解）。
    if flow == "pending_mood_confirm":
        return commands.handle_mood_confirm_text(state_store, telegram_user_id)
    if flow == "mood_delete_confirm":
        return commands.handle_mood_confirm_text(state_store, telegram_user_id)
    # 2026-08-04（Step 2.1，見 robinson SPEC.md FR-41～FR-44）：記帳多輪對話流，結構比照心情小記
    # 的補記/更新/刪除擴充，見 commands.py「記帳」區塊開頭說明。
    # 2026-08-04 擴充（見 robinson SPEC.md FR-41a）：設定預算改成多輪，見 commands.py 該擴充說明。
    if flow == "pending_finance_budget_scope":
        return commands.handle_finance_budget_scope_step(db, state_store, telegram_user_id, text)
    if flow == "pending_finance_budget_months":
        return commands.handle_finance_budget_months_step(db, state_store, telegram_user_id, text)
    # 2026-08-18（批次5）：兩個預算覆蓋確認關卡改成按鈕（`finance:budget_confirm_save`／
    # `finance:budget_override_confirm_save`），使用者這裡若打字一律當作不接受，理由同
    # `handle_finance_confirm_text`。
    if flow in ("pending_finance_budget_global_confirm", "pending_finance_budget_override_confirm"):
        return commands.handle_finance_confirm_text(state_store, telegram_user_id)
    if flow == "pending_finance_budget_amount":
        return commands.handle_finance_budget_amount_step(db, state_store, telegram_user_id, text)
    if flow == "pending_transaction_backfill_date":
        return commands.handle_transaction_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_transaction_type":
        return commands.handle_transaction_type_step(state_store, telegram_user_id, text)
    if flow == "pending_transaction_category":
        return commands.handle_transaction_category_step(state_store, telegram_user_id, text)
    if flow == "pending_transaction_amount":
        return commands.handle_transaction_amount_step(state_store, telegram_user_id, text)
    if flow == "pending_transaction_note":
        return commands.handle_transaction_note_step(state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client)
    if flow in ("pending_transaction_confirm", "finance_transaction_delete_confirm"):
        return commands.handle_finance_confirm_text(state_store, telegram_user_id)
    # 2026-08-17（Phase 6 第二批 2h，見 robinson SPEC.md FR-45／FR-46）：體態管理全面改選單
    # 觸發＋摘要→二次確認，結構比照運動（2c）／飲食（2g）。
    if flow == "pending_body_height_value":
        return commands.handle_body_height_value_step(state_store, telegram_user_id, text)
    if flow == "pending_body_waist_value":
        return commands.handle_body_waist_value_step(state_store, telegram_user_id, text)
    if flow == "pending_body_waist_offer":
        # 記體重後「順便問要不要記腰圍」的回覆，見 commands.handle_body_weight_confirm_save()
        # 的觸發時機說明。
        return commands.handle_body_waist_offer_step(db, state_store, telegram_user_id, text)
    if flow == "pending_body_weight_backfill_date":
        return commands.handle_body_weight_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_body_weight_value":
        return commands.handle_body_weight_value_step(db, state_store, telegram_user_id, text)
    if flow in ("pending_body_height_confirm", "pending_body_waist_confirm", "pending_body_weight_confirm", "body_weight_delete_confirm"):
        return commands.handle_body_confirm_text(state_store, telegram_user_id)
    if flow == "pending_exercise_backfill_date":
        return commands.handle_exercise_backfill_date_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_exercise_category_custom":
        return commands.handle_exercise_category_custom_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_exercise_duration":
        return commands.handle_exercise_duration_step(state_store, telegram_user_id, text)
    if flow == "pending_exercise_heart_rate":
        return commands.handle_exercise_heart_rate_step(state_store, telegram_user_id, text)
    if flow == "pending_exercise_note":
        return commands.handle_exercise_note_step(state_store, telegram_user_id, text)
    if flow == "pending_exercise_calories_manual":
        return commands.handle_exercise_calories_manual_step(state_store, telegram_user_id, text)
    # 2026-08-16（Phase 6 第二批 2c）／2026-08-17（FR-47a，批次2）：這幾個關卡只接受按鈕操作，
    # 理由同心情小記的 pending_mood_confirm／mood_delete_confirm。
    if flow in (
        "pending_exercise_category",
        "pending_exercise_calorie_choice",
        "pending_exercise_confirm",
        "exercise_delete_confirm",
    ):
        return commands.handle_exercise_confirm_text(state_store, telegram_user_id)
    # 2026-08-16（Phase 6 第二批 2g）：飲食/飲水全面改選單觸發＋摘要→二次確認，見
    # commands.py「飲食（含飲水）」區塊模組註解。
    if flow == "pending_diet_backfill_date":
        return commands.handle_diet_backfill_date_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_diet_water_amount":
        return commands.handle_diet_water_amount_step(state_store, telegram_user_id, text)
    if flow == "pending_diet_description":
        return commands.handle_diet_description_step(state_store, telegram_user_id, text)
    if flow == "pending_diet_photo":
        # 這一步要傳照片，收到文字（含語音轉出來的文字）代表使用者這次沒有傳照片，提醒並
        # 提供改用文字輸入的退路，見 commands.handle_diet_photo_wait_step()。
        return commands.handle_diet_photo_wait_step(state_store, telegram_user_id)
    if flow == "pending_diet_photo_confirm":
        return commands.handle_diet_photo_confirm_step(state_store, telegram_user_id, text)
    if flow == "pending_diet_manual_macros":
        return commands.handle_diet_manual_macros_step(state_store, telegram_user_id, text)
    # 2026-08-16（Phase 6 第二批 2g）：這幾個按鈕關卡只接受按鈕操作，理由同
    # pending_exercise_confirm／exercise_delete_confirm。
    if flow in ("pending_diet_water_choice", "pending_diet_food_choice", "pending_diet_food_input_mode",
                "pending_diet_nutrition_source", "pending_diet_confirm", "diet_delete_confirm"):
        return commands.handle_diet_confirm_text(state_store, telegram_user_id)
    if flow == "pending_goal_type":
        return commands.handle_goal_type_step(state_store, telegram_user_id, text)
    if flow == "pending_goal_weight_value":
        return commands.handle_goal_weight_value_step(db, state_store, telegram_user_id, text)
    if flow == "pending_goal_exercise_minutes":
        return commands.handle_goal_exercise_minutes_step(state_store, telegram_user_id, text)
    if flow == "pending_goal_diet_description":
        return commands.handle_goal_diet_description_step(
            state_store, telegram_user_id, text, llm_client=llm_client, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_goal_deadline":
        return commands.handle_goal_deadline_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_goal_calendar_sync":
        # 只有新增流程、講清楚期限的目標才會走到這一題，見 handle_goal_deadline_step。
        return commands.handle_goal_calendar_sync_step(llm_client, state_store, telegram_user_id, text)
    if flow in ("pending_goal_confirm", "goal_delete_confirm"):
        return commands.handle_goal_confirm_text(state_store, telegram_user_id)
    # 2026-08-17（批次3，FR-45a）：記帳／收藏清單通用目標流程，見 commands.py 對應區塊。
    if flow == "pending_module_goal_description":
        return commands.handle_module_goal_description_step(
            db, llm_client, state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_module_goal_deadline":
        return commands.handle_module_goal_deadline_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_module_goal_calendar_sync":
        # 2026-08-17 補做（Robin 要求不得漏做）：只有新增流程、講清楚期限的模組目標才會走到
        # 這一題，見 handle_module_goal_deadline_step。
        return commands.handle_module_goal_calendar_sync_step(llm_client, state_store, telegram_user_id, text)
    if flow in ("pending_module_goal_confirm", "module_goal_delete_confirm"):
        return commands.handle_module_goal_confirm_text(state_store, telegram_user_id)
    # 2026-08-08（Step 3.3，見 robinson SPEC.md FR-27、FR-26 決策 5、6）：證照題庫作答（一次一題）
    # 與彈性排程調整（選 exam_type → 自由描述 → LLM 分類語意 → SPREAD 需額外確認提案）。
    if flow == "pending_quiz_answer":
        return commands.handle_quiz_answer_step(db, state_store, telegram_user_id, text)
    if flow == "pending_quiz_schedule_exam_type_choice":
        return commands.handle_quiz_schedule_exam_type_choice_step(state_store, telegram_user_id, text)
    if flow == "pending_quiz_schedule_intent":
        return commands.handle_quiz_schedule_intent_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_quiz_schedule_spread_confirm":
        return commands.handle_quiz_schedule_spread_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    # 2026-08-08 追加（Step 3.3 剩餘範圍，見 robinson SPEC.md FR-30、FR-24、FR-29、ADR-19）：
    # 正式成績記錄、證照目標設定、方向建議選 exam_type、成效彈性文字問答。
    if flow == "pending_exam_score_exam_type":
        return commands.handle_exam_score_exam_type_step(state_store, telegram_user_id, text)
    if flow == "pending_exam_score_date":
        return commands.handle_exam_score_date_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_exam_score_value":
        return commands.handle_exam_score_value_step(db, state_store, telegram_user_id, text)
    if flow == "pending_certificate_goal_exam_type":
        return commands.handle_certificate_goal_exam_type_step(state_store, telegram_user_id, text)
    if flow == "pending_certificate_goal_target_date":
        return commands.handle_certificate_goal_target_date_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_certificate_goal_target_score":
        return commands.handle_certificate_goal_target_score_step(db, state_store, telegram_user_id, text)
    if flow == "pending_certificate_advice_exam_type":
        return commands.handle_certificate_advice_exam_type_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_quiz_stats_query":
        return commands.handle_quiz_stats_query_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "certificate_profile_add":
        return certificate_settings.handle_profile_add_text(state_store, telegram_user_id, text)
    if flow in {"certificate_score_date", "certificate_score_value", "certificate_score_note"}:
        return certificate_settings.handle_score_text(state_store, telegram_user_id, text)
    if flow.startswith("certificate_daily_") and flow != "certificate_daily_confirm":
        return certificate_settings.handle_daily_text(state_store, telegram_user_id, text)
    if flow in {"certificate_goal_date", "certificate_goal_score"}:
        return certificate_settings.handle_goal_text(state_store, telegram_user_id, text)
    if flow.startswith("certificate_range_") and flow not in {
        "certificate_range_confirm", "certificate_range_delete_confirm",
    }:
        return certificate_settings.handle_range_text(db, state_store, telegram_user_id, text)
    # 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md、
    # docs/ADR/discuss/youtube-intel.md 對應日期條目）：YouTube 技術情報主題新增／移除確認。
    if flow == "youtube_topic_add":
        return commands.handle_youtube_topic_add_step(db, state_store, telegram_user_id, text)
    if flow == "youtube_topic_remove_confirm":
        return commands.handle_youtube_topic_remove_confirm_text(state_store, telegram_user_id)
    # 2026-08-09（Step 4.1，見 robinson SPEC.md FR-33、FR-36、ADR-24）：求職模組設定流程，
    # 結構比照記帳/證照目標等既有多輪對話流，見 commands.py「求職模組設定流程」區塊開頭說明。
    if flow == "pending_job_search_criteria":
        return commands.handle_job_search_criteria_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_job_search_ready_confirm":
        return commands.handle_job_search_ready_confirm_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_job_search_resume":
        return commands.handle_job_search_resume_step(
            state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_job_search_resume_confirm":
        return commands.handle_job_search_resume_confirm_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_job_search_expectation":
        return commands.handle_job_search_expectation_step(
            state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_job_search_expectation_confirm":
        return commands.handle_job_search_expectation_confirm_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_job_search_years_experience":
        return commands.handle_job_search_years_experience_step(state_store, telegram_user_id, text)
    if flow == "pending_job_search_salary_min":
        return commands.handle_job_search_salary_min_step(state_store, telegram_user_id, text)
    if flow == "pending_job_search_salary_max":
        return commands.handle_job_search_salary_max_step(db, state_store, telegram_user_id, text)
    if flow == "pending_job_settings_profile":
        return job_settings.handle_profile_edit(db, state_store, telegram_user_id, text)
    if flow == "pending_job_settings_requirements":
        return job_settings.handle_requirements_edit(db, state_store, telegram_user_id, text)
    if flow == "pending_job_settings_criteria":
        return job_settings.handle_criteria_add(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_job_settings_criteria_edit":
        return job_settings.handle_criteria_edit(db, llm_client, state_store, telegram_user_id, text)
    # 2026-08-09（Step 4.3，見 robinson SPEC.md FR-40、ADR-27）：外部管道職缺新增流程，六輪
    # 依序收集管道／職稱／公司名／連結／內容／公司背景，結構比照求職模組設定流程但不經 LLM
    # 解析（純自由文字直接記錄），只有內容/背景這兩輪需要 privacy_llm_client 做個資遮蔽。
    if flow == "pending_external_job_channel":
        return commands.handle_external_job_channel_step(state_store, telegram_user_id, text)
    if flow == "pending_external_job_title":
        return commands.handle_external_job_title_step(state_store, telegram_user_id, text)
    if flow == "pending_external_job_company":
        return commands.handle_external_job_company_step(state_store, telegram_user_id, text)
    if flow == "pending_external_job_url":
        return commands.handle_external_job_url_step(state_store, telegram_user_id, text)
    if flow == "pending_external_job_content":
        return commands.handle_external_job_content_step(
            state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_external_job_background":
        return commands.handle_external_job_background_step(
            db, state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    raise ValueError(f"未知的對話狀態：{state}")
