"""統一路由：依身分、對話狀態、文字內容，分派到對應處理函式。"""
import re

from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, chat, collections, commands, image, important_days, job_search, menu, system_errors, templates, toggles, trips, voice
from src.bot.state import ConversationStateStore

_NOT_BOUND_REPLY = "請輸入通關密碼才能開始使用羅賓森喔！"
_AWAITING_PASSCODE_REPLY = "請輸入通關密碼："
_PASSCODE_BIND_FAILED_REPLY = "通關密碼不正確或已失效，請重新輸入，或輸入 /start 重新開始。"
_PERMISSION_DENIED_REPLY = "無法使用這個功能。"

# 2026-08-01（Step 1.4，robinson SPEC.md FR-14／FR-15）：語音訊息的擋下情境固定文案，
# 都在下載/上傳/轉文字之前就先擋下，避免浪費 Drive／Groq 額度，見 src/bot/voice.py 模組 docstring。
# 2026-08-02 起 FR-14 拆成兩條獨立規則：_VOICE_DURATION_LIMIT_REPLY 是「這一則太長」的當下拒絕，
# _VOICE_DURATION_LOCKOUT_REPLY 是「之前超時過，15 分鐘全面鎖定中」；_VOICE_CORRECTION_WINDOW_REPLY
# 則是 FR-15「只鎖修正情境」，三者觸發條件互不相同。
_VOICE_DURATION_LIMIT_REPLY = (
    "這則語音超過 10 分鐘囉，我沒辦法處理這麼長的語音，麻煩分段傳送或改用打字喔！"
    "接下來 15 分鐘語音功能會暫時鎖定，這段期間麻煩先用打字。"
)
_VOICE_DURATION_LOCKOUT_REPLY = (
    "剛剛語音超過 10 分鐘，語音功能鎖定中，這段期間麻煩先用打字，超過鎖定時間會自動恢復喔！"
)
_VOICE_CORRECTION_WINDOW_REPLY = "你剛剛才傳過語音，15 分鐘內麻煩先用打字修正或補充喔，超過 15 分鐘語音模式就會自動恢復！"

# 2026-08-02 追加：語音成功轉出文字後（代表 FR-15 修正窗口已經開始），主動附註提醒，不要讓使用者
# 只能靠「又傳一次語音被拒絕」才被動發現這 15 分鐘語音功能被鎖定；鎖定到期時目前沒有主動通知
# （機器人本身被動回應訊息，沒有排程推播機制），使用者下次互動時語音自然就能用了。
_VOICE_TRANSCRIBED_REMINDER = (
    "\n\n（提醒：接下來 15 分鐘內如果想修正或補充剛剛這則語音的內容，麻煩先用打字喔，"
    "超過 15 分鐘語音功能就會恢復正常！）"
)

# 2026-08-15（Phase 6 第二批 2a，見 docs/specs/SPEC.md FR-6a）：`/start` 是 FR-6a 定案下
# 唯一保留的 Slash Command，用於 START 首次驗證及重新顯示主選單；取代舊版 `/set_invite_codes`
# 的 Owner 建立使用者流程已改為選單驅動，見 commands.start_permission_menu()。
_START_TRIGGERS = {"/start"}
# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-20）：Owner 專屬，廣播「我康復了」給所有家人。
_RECOVERED_TRIGGERS = {"/recovered"}
_RULE_TRIGGERS = {"/rule", "我要看使用規則"}
_FUNCTION_TRIGGERS = {"/function", "我要看所有功能"}
_MY_TOGGLES_TRIGGERS = {"/my_toggles", "我的功能設定"}
_SET_TOGGLE_TRIGGERS = {"/set_toggle", "設定家人功能開關"}
# 2026-08-04（Step 2.3，見 robinson SPEC.md FR-53）：Owner 專屬，補齊家人生日資料，設計比照 /set_toggle。
_SET_FAMILY_BIRTHDAY_TRIGGERS = {"/set_family_birthday", "設定家人生日"}
# 2026-08-02（Step 1.7，見 robinson SPEC.md FR-32）：查詢待辦事項清單，所有使用者皆可用
# （不像 /set_toggle 是 Owner 專屬），放在 is_owner/非 is_owner 分支都會落到的共用觸發詞區塊。
_MY_TODOS_TRIGGERS = {"/my_todos", "我的待辦事項"}
# 2026-08-16（Phase 6 第二批 2c）：心情小記全面改選單觸發，舊文字觸發詞
# （/mood_journal、/backfill_mood、/my_mood_journals 等）已移除，入口改為
# 「📝 日常紀錄」→「😊 心情」子選單，見 menu.py `DAILY_LOG_MENU_ITEMS`。
# 2026-08-08（Step 3.5，見 robinson SPEC.md FR-51、FR-52、ADR-22）：好友模式陪伴聊天，`friend_mode`
# 開關 owner_only=False，所有使用者皆可用，放在共用觸發詞區塊；單輪生成完整回覆，不需要對話狀態機。
_FRIEND_CHAT_TRIGGERS = {"/friend_chat", "陪我聊聊"}
# 2026-08-04（Step 2.1，見 robinson SPEC.md FR-41～FR-44）：記帳模組觸發詞，設計比照心情小記。
_FINANCE_SET_BUDGET_TRIGGERS = {"/set_budget", "設定記帳預算"}
_FINANCE_ADD_TRIGGERS = {"/add_transaction", "我要記帳"}
_FINANCE_BACKFILL_TRIGGERS = {"/backfill_transaction", "我要補記帳"}
_MY_TRANSACTIONS_TRIGGERS = {"/my_transactions", "我的記帳紀錄"}
_FINANCE_SUMMARY_TRIGGERS = {"/my_finance_summary", "我的記帳摘要"}
# 2026-08-04（Step 2.2，見 robinson SPEC.md FR-45～FR-48）：體態管理模組觸發詞，設計比照記帳/心情小記。
_SET_HEIGHT_TRIGGERS = {"/set_height", "設定身高"}
# 2026-08-08 追加（FR-46 擴充）：腰圍為參考指標，觸發詞設計與身高完全對稱。
_SET_WAIST_TRIGGERS = {"/set_waist", "設定腰圍"}
_LOG_WEIGHT_TRIGGERS = {"/log_weight", "我要記錄體重"}
_BACKFILL_WEIGHT_TRIGGERS = {"/backfill_weight", "我要補記體重"}
_MY_WEIGHT_LOGS_TRIGGERS = {"/my_weight_logs", "我的體重紀錄"}
# 2026-08-16（Phase 6 第二批 2c）：運動全面改選單觸發，舊文字觸發詞
# （/log_exercise、/backfill_exercise、/my_exercise_logs 等）已移除，入口改為
# 「📝 日常紀錄」→「🏃 運動」子選單。
_LOG_DIET_TRIGGERS = {"/log_diet", "我要記錄飲食"}
_BACKFILL_DIET_TRIGGERS = {"/backfill_diet", "我要補記飲食"}
_MY_DIET_LOGS_TRIGGERS = {"/my_diet_logs", "我的飲食紀錄"}
_SET_BODY_GOAL_TRIGGERS = {"/set_body_goal", "我要設定體態管理目標"}
_MY_BODY_GOALS_TRIGGERS = {"/my_body_goals", "我的體態目標"}
# 2026-08-08（Step 3.3，見 robinson SPEC.md FR-27、FR-26 決策 5）：證照題庫作答與彈性排程調整，
# `certificate` 功能開關本身是 owner_only（見 templates.py FEATURE_LIST），這兩個觸發詞只放在
# is_owner 分支，比照 _SET_TOGGLE_TRIGGERS 等既有 Owner 專屬觸發詞的位置。
_START_QUIZ_TRIGGERS = {"/start_quiz", "開始作答"}
_ADJUST_QUIZ_SCHEDULE_TRIGGERS = {"/adjust_quiz_schedule", "調整出題排程"}
# 2026-08-08 追加（Step 3.3 剩餘範圍，見 robinson SPEC.md FR-30、FR-24、FR-29、ADR-19）：正式成績
# 記錄／查詢、證照目標設定／查詢／方向建議、成效彈性文字問答，同樣皆為 Owner 專屬。
_LOG_EXAM_SCORE_TRIGGERS = {"/log_exam_score", "我要記錄正式成績"}
_MY_EXAM_SCORES_TRIGGERS = {"/my_exam_scores", "我的正式成績"}
_SET_CERTIFICATE_GOAL_TRIGGERS = {"/set_certificate_goal", "設定證照目標"}
_MY_CERTIFICATE_GOALS_TRIGGERS = {"/my_certificate_goals", "我的證照目標"}
_CERTIFICATE_ADVICE_TRIGGERS = {"/certificate_advice", "給我讀書建議"}
_MY_QUIZ_STATS_TRIGGERS = {"/my_quiz_stats", "查詢我的成效"}
# 2026-08-08 追加（Step 3.4，見 robinson SPEC.md FR-57a、ADR-21）：YouTube 技術情報主題管理，
# `tech_intel` 功能開關本身是 owner_only，這三個觸發詞同樣只放在 is_owner 分支。
_MY_YOUTUBE_TOPICS_TRIGGERS = {"/my_youtube_topics", "我的YouTube主題"}
_ADD_YOUTUBE_TOPIC_TRIGGERS = {"/add_youtube_topic", "新增YouTube主題"}
_REMOVE_YOUTUBE_TOPIC_TRIGGERS = {"/remove_youtube_topic", "移除YouTube主題"}
# 2026-08-09（Step 4.1，見 robinson SPEC.md FR-33、FR-36、ADR-24 決策 2）：求職模組設定流程，
# `job_search` 開關同步改為 owner_only=True，觸發詞只放在 is_owner 分支，家人完全看不到這個功能。
_JOB_SEARCH_SETUP_TRIGGERS = {"/set_job_search", "我要找工作", "我最近想要找工作了"}
# 2026-08-09（Step 4.3，見 robinson SPEC.md FR-40、ADR-27）：外部管道職缺新增流程與應徵紀錄
# 查詢指令，觸發詞位置比照求職模組設定流程，只放在 is_owner 分支。
_ADD_EXTERNAL_JOB_TRIGGERS = {"/add_external_job", "新增外部職缺"}
_MY_APPLICATIONS_TRIGGERS = {"/my_applications", "我的應徵紀錄"}
# 2026-08-09（Step 4.3，見 robinson SPEC.md FR-39b、ADR-27）：應徵狀態更新語句，比照
# `_UPLOADED_FILE_PATTERN` 直接在這裡用 regex 一次解析，不走多輪對話狀態機。
_APPLICATION_STATUS_PATTERN = re.compile(
    r"^ID=(?P<job_id>[\w-]+)\s*職缺(?P<status_text>已應徵|已獲得面試|已拿到\s*Offer|已婉拒|未錄取)$"
)
# 2026-08-09（見 robinson SPEC.md FR-19j）：系統錯誤解法記錄，Owner 專屬單行指令，比照
# `_APPLICATION_STATUS_PATTERN` 直接 regex 解析、不走多輪對話狀態機。刻意用「錯誤ID=」
# 而非單純「ID=」開頭，避免跟 `_APPLICATION_STATUS_PATTERN` 的 `ID=<job_id>` 撞在一起。
_ERROR_RESOLUTION_PATTERN = re.compile(r"^錯誤ID=(?P<report_id>\d+)\s*已處理[:：]\s*(?P<resolution>.+)$")
# 2026-08-09（見 robinson SPEC.md FR-35e、FR-38e、ADR-24 後果、ADR-26）：帶動態檔名的觸發詞，
# 設計比照 _CLEAN_TARGET_DIALOG_PATTERN 用 regex 擷取參數；依副檔名/檔名關鍵字分流成兩條各自
# 獨立的回填流程——公司背景 CSV（檔名以「104職缺公司.csv」結尾）與職缺推薦 Excel（檔名以
# 「104職缺推薦.xlsx」結尾），不需要改動這個 regex 本身，只需要在下方 if/elif 各自擴充。
_UPLOADED_FILE_PATTERN = re.compile(r"^已上傳\s*(?P<filename>.+)$")
# 2026-08-02（Step 1.9，見 robinson SPEC.md FR-60）：任何身分皆可觸發客訴收集流程。
_COMPLAINT_TRIGGERS = {"/complaint", "我要客訴你"}
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
    privacy_llm_client=None,
    telegram_client=None,
    calendar_client=None,
    gdrive_client=None,
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

    `privacy_llm_client`（2026-08-02，見 docs/specs/privacy-masking/SPEC.md）：個資遮蔽 LLM 語意層
    專用的獨立 Key，只會透傳到 `chat.handle_chat_message()`（見該函式 docstring）；`None` 時遮蔽
    只跑免費的 Regex 層，不影響其餘指令/對話流程分支。

    `telegram_client`（2026-08-02，Step 1.6，見 robinson SPEC.md FR-20）：`/recovered`（廣播
    「我康復了」給所有已綁定家人）與 `pending_complaint_content`（Step 1.9，FR-62，私訊 Robin
    客訴分析報告）這兩個分支會用到，其餘分支不需要。

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

        if text in _SET_TOGGLE_TRIGGERS:
            return commands.start_set_toggle(db, state_store, telegram_user_id)
        if text in _SET_FAMILY_BIRTHDAY_TRIGGERS:
            return commands.start_set_family_birthday(db, state_store, telegram_user_id)
        if text in _MY_TOGGLES_TRIGGERS:
            return commands.start_my_toggles(db, state_store, telegram_user_id, user_id)
        if text in _RECOVERED_TRIGGERS:
            return commands.handle_recovered(db, telegram_client)
        if text in _START_QUIZ_TRIGGERS:
            # 2026-08-08（FR-27）：開始依序作答目前所有待作答的證照題庫題目。
            return commands.start_quiz_answer(db, state_store, telegram_user_id, user_id)
        if text in _ADJUST_QUIZ_SCHEDULE_TRIGGERS:
            # 2026-08-08（FR-26 決策 5、6）：開始彈性排程調整流程（MOVE/CANCEL/RANGE/SPREAD）。
            return commands.start_quiz_schedule_adjust(db, state_store, telegram_user_id, user_id)
        if text in _LOG_EXAM_SCORE_TRIGGERS:
            # 2026-08-08（FR-30）：開始記錄正式應考成績流程。
            return commands.start_log_exam_score(db, state_store, telegram_user_id, user_id)
        if text in _MY_EXAM_SCORES_TRIGGERS:
            # 2026-08-08（FR-30）：查詢正式成績（單次列表，不經對話狀態機）。
            return commands.handle_my_exam_scores(db, user_id)
        if text in _SET_CERTIFICATE_GOAL_TRIGGERS:
            # 2026-08-08（FR-24）：開始設定證照準備目標流程。
            return commands.start_set_certificate_goal(db, state_store, telegram_user_id, user_id)
        if text in _MY_CERTIFICATE_GOALS_TRIGGERS:
            # 2026-08-08（FR-24）：查詢證照準備目標（單次列表，不經對話狀態機）。
            return commands.handle_my_certificate_goals(db, user_id)
        if text in _CERTIFICATE_ADVICE_TRIGGERS:
            # 2026-08-08（FR-24）：依近 30 天成效與目標，用 LLM 生成方向建議。
            return commands.start_certificate_advice(db, llm_client, state_store, telegram_user_id, user_id)
        if text in _MY_QUIZ_STATS_TRIGGERS:
            # 2026-08-08（FR-29）：開始成效彈性文字問答流程。
            return commands.start_quiz_stats_query(db, state_store, telegram_user_id, user_id)
        if text in _MY_YOUTUBE_TOPICS_TRIGGERS:
            # 2026-08-08（Step 3.4，FR-57a）：查詢目前設定的 YouTube 技術情報主題（單次列表）。
            return commands.handle_my_youtube_topics(db, user_id)
        if text in _ADD_YOUTUBE_TOPIC_TRIGGERS:
            # 2026-08-08（Step 3.4，FR-57a）：開始新增一組 YouTube 技術情報主題流程。
            return commands.start_add_youtube_topic(state_store, telegram_user_id, user_id)
        if text in _REMOVE_YOUTUBE_TOPIC_TRIGGERS:
            # 2026-08-08（Step 3.4，FR-57a）：列出目前主題並進入可輸入編號刪除的模式。
            return commands.start_remove_youtube_topic(db, state_store, telegram_user_id, user_id)
        if text in _JOB_SEARCH_SETUP_TRIGGERS:
            # 2026-08-09（Step 4.1，FR-33、FR-36）：開始求職模組設定流程，先問搜尋條件。
            return commands.start_job_search_setup(state_store, telegram_user_id, user_id)
        if text in _ADD_EXTERNAL_JOB_TRIGGERS:
            # 2026-08-09（Step 4.3，FR-40）：開始記錄 LinkedIn／Cake 等外部管道職缺，先問管道。
            return commands.start_add_external_job(state_store, telegram_user_id, user_id)
        if text in _MY_APPLICATIONS_TRIGGERS:
            # 2026-08-09（Step 4.3，FR-39 追加）：查詢目前各職缺的最新應徵狀態（單次列表）。
            return commands.handle_my_applications(db)
        application_status_match = _APPLICATION_STATUS_PATTERN.match(text)
        if application_status_match:
            # 2026-08-09（Step 4.3，FR-39b）：應徵狀態更新語句，不走多輪對話，直接解析並寫入。
            job_id = application_status_match.group("job_id")
            status_text = application_status_match.group("status_text").replace(" ", "")
            status = job_search.APPLICATION_STATUS_TEXT_TO_STATUS[status_text]
            if job_search.record_application_status(db, job_id, status):
                label = job_search.application_status_label(status)
                return f"已經幫你把「{job_id}」的應徵狀態更新為「{label}」了！"
            return f"找不到 ID={job_id} 對應的職缺，麻煩確認一下 ID 有沒有打對！"
        error_resolution_match = _ERROR_RESOLUTION_PATTERN.match(text)
        if error_resolution_match:
            # 2026-08-09（見 robinson SPEC.md FR-19j）：系統錯誤解法記錄語句，不走多輪對話，
            # 直接解析並寫入 system_error_reports.resolution。
            report_id = int(error_resolution_match.group("report_id"))
            resolution = error_resolution_match.group("resolution").strip()
            if system_errors.update_resolution(db, report_id, resolution):
                return f"已經幫你把「錯誤ID={report_id}」的解法記錄好了！"
            return f"找不到 錯誤ID={report_id} 對應的紀錄，麻煩確認一下 ID 有沒有打對！"
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

        if text in _MY_TOGGLES_TRIGGERS:
            return commands.start_my_toggles(db, state_store, telegram_user_id, user_id)

    if text in _RULE_TRIGGERS:
        return commands.handle_rule()
    if text in _FUNCTION_TRIGGERS:
        return commands.handle_function(db, llm_client)
    if text in _MY_TODOS_TRIGGERS:
        # 2026-08-02（Step 1.7，見 robinson SPEC.md FR-32）：查詢待處理清單並進入可標記完成/取消的模式。
        return commands.start_todo_list(db, state_store, telegram_user_id, user_id)
    if text in _FRIEND_CHAT_TRIGGERS:
        # 2026-08-08（Step 3.5，見 robinson SPEC.md FR-51、FR-52、ADR-22）：好友模式陪伴聊天，
        # 單次生成完整回覆，不需要對話狀態機。
        return commands.start_friend_chat(db, llm_client, user_id)
    if text in _FINANCE_SET_BUDGET_TRIGGERS:
        # 2026-08-04（Step 2.1，見 robinson SPEC.md FR-41）：設定每月支出預算上限。
        return commands.start_finance_budget(state_store, telegram_user_id, user_id)
    if text in _FINANCE_ADD_TRIGGERS:
        # 2026-08-04（FR-42）：開始記帳流程，先問交易類型。
        return commands.start_finance_add(state_store, telegram_user_id, user_id)
    if text in _FINANCE_BACKFILL_TRIGGERS:
        # 2026-08-04（FR-42）：補記過去日期的記帳，先問是哪一天。
        return commands.start_finance_backfill(state_store, telegram_user_id, user_id)
    if text in _MY_TRANSACTIONS_TRIGGERS:
        # 2026-08-04（FR-42）：查詢記帳清單並進入可更新/刪除的模式。
        return commands.start_finance_list(db, state_store, telegram_user_id, user_id)
    if text in _FINANCE_SUMMARY_TRIGGERS:
        # 2026-08-04（FR-44）：單次查詢當月記帳文字摘要，不需要對話狀態機。
        return commands.handle_finance_summary(db, user_id)
    if text in _SET_HEIGHT_TRIGGERS:
        # 2026-08-04（Step 2.2，見 robinson SPEC.md FR-46）：設定身高，單輪。
        return commands.start_set_height(state_store, telegram_user_id, user_id)
    if text in _SET_WAIST_TRIGGERS:
        # 2026-08-08 追加（FR-46 擴充）：設定腰圍，單輪，設計與身高完全對稱。
        return commands.start_set_waist(state_store, telegram_user_id, user_id)
    if text in _LOG_WEIGHT_TRIGGERS:
        return commands.start_weight_log(state_store, telegram_user_id, user_id)
    if text in _BACKFILL_WEIGHT_TRIGGERS:
        return commands.start_weight_backfill(state_store, telegram_user_id, user_id)
    if text in _MY_WEIGHT_LOGS_TRIGGERS:
        return commands.start_weight_list(db, state_store, telegram_user_id, user_id)
    if text in _LOG_DIET_TRIGGERS:
        # 2026-08-04（FR-48）：開始記錄飲食/飲水流程，先問類型。
        return commands.start_diet_log(state_store, telegram_user_id, user_id)
    if text in _BACKFILL_DIET_TRIGGERS:
        return commands.start_diet_backfill(state_store, telegram_user_id, user_id)
    if text in _MY_DIET_LOGS_TRIGGERS:
        return commands.start_diet_list(db, state_store, telegram_user_id, user_id)
    if text in _SET_BODY_GOAL_TRIGGERS:
        # 2026-08-04（FR-46～FR-48）：設定體態管理目標，先問類型。
        return commands.start_body_goal(state_store, telegram_user_id, user_id)
    if text in _MY_BODY_GOALS_TRIGGERS:
        return commands.start_body_goal_list(db, state_store, telegram_user_id, user_id)
    if text in _COMPLAINT_TRIGGERS:
        # 2026-08-02（Step 1.9，見 robinson SPEC.md FR-60）：固定提問，不經過 LLM。
        return commands.start_complaint(state_store, telegram_user_id, user_id)
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
        db, llm_client, text_llm_client, state_store, telegram_user_id, user_id, text,
        privacy_llm_client=privacy_llm_client,
    )


def handle_callback_query(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    data: str,
) -> tuple[str, dict | None]:
    """處理按下 Inline Keyboard 按鈕觸發的 callback_query（見 FR-6c：任何選單／callback 都要
    重新驗證權限，不能只靠「一開始選單沒顯示這顆按鈕」來擋，避免偽造 callback_data 繞過）。

    回傳 `(text, reply_markup)`，`reply_markup` 可能為 `None`（例如權限管理選單分派後的
    引導式文字提問，本來就不需要再帶按鈕）。
    """
    is_owner = auth.is_owner(telegram_user_id)

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
        if key == "important_days":
            state_store.clear(telegram_user_id)
            return important_days.start_important_days_menu()
        if key == "collections":
            # 2026-08-16（Phase 6 第二批 2d，FR-6e）：收藏與旅遊子選單首頁。
            state_store.clear(telegram_user_id)
            return collections.start_collections_menu()
        if key == "daily_log":
            state_store.clear(telegram_user_id)
            return menu.DAILY_LOG_MENU_TEXT, menu.build_daily_log_menu_keyboard()
        return menu.not_yet_implemented_reply()

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
        return menu.daily_log_not_yet_implemented_reply()

    if data.startswith("permission:"):
        action = data[len("permission:") :]
        if not is_owner:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        return commands.handle_permission_callback(db, state_store, telegram_user_id, action)

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

    if data.startswith("collections:"):
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-75）：收藏清單選單與 CRUD 操作。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("collections:") :]
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
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY, menu.back_to_main_menu_keyboard()
        action = data[len("exercise:") :]
        if action == "list":
            return commands.handle_exercise_list(db, user["id"])
        if action == "new":
            return commands.start_exercise_log(state_store, telegram_user_id, user["id"]), None
        if action == "backfill":
            return commands.start_exercise_backfill(state_store, telegram_user_id, user["id"]), None
        if action.startswith("edit:"):
            exercise_log_id = int(action[len("edit:") :])
            return commands.start_exercise_edit(db, state_store, telegram_user_id, user["id"], exercise_log_id), None
        if action.startswith("delete:"):
            exercise_log_id = int(action[len("delete:") :])
            return commands.start_exercise_delete_confirm(db, state_store, telegram_user_id, user["id"], exercise_log_id)
        if action.startswith("confirm_delete:"):
            exercise_log_id = int(action[len("confirm_delete:") :])
            return commands.handle_exercise_delete(db, state_store, telegram_user_id, user["id"], exercise_log_id), menu.back_to_main_menu_keyboard()
        if action == "confirm_save":
            return commands.handle_exercise_confirm_save(db, state_store, telegram_user_id), None
        return commands.start_exercise_menu()

    # 未知／格式不符的 callback_data（例如過期或偽造），保守導回主選單，不當例外處理。
    return menu.MAIN_MENU_TEXT, menu.build_main_menu_keyboard(is_owner=is_owner)


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
    privacy_llm_client=None,
) -> str:
    """處理使用者傳來的圖片訊息（對應 robinson SPEC.md FR-17、ADR-13）。

    未綁定通關密碼者一律先擋下，不消耗任何 Drive/Gemini 額度；已綁定者才下載圖片並交給
    `src/bot/image.py` 的商業邏輯處理。若使用者原本卡在某個未完成的對話流程（例如上一輪的
    圖片澄清問答還沒回答完就又傳了新圖片），直接以新圖片覆蓋、清除舊流程狀態，避免卡死。

    `privacy_llm_client`（2026-08-02，見 docs/specs/privacy-masking/SPEC.md FR-5）：透傳給
    `image.handle_image_message()`，用來在 `caption` 送進 Gemini 前先做個資遮蔽。
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
    voice_lockout_store: ConversationStateStore | None = None,
    privacy_llm_client=None,
    calendar_client=None,
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

    2026-08-02（FR-16a）：如果目前卡在 `_FINAL_CONFIRM_FLOWS` 這幾個「最終執行確認」狀態，
    語音一定會被拒絕（這一步只接受打字），所以**在下載/轉錄之前就直接短路回覆**，比照
    FR-14/FR-15「先擋才不浪費額度」的一貫原則——沒必要為了一個註定被拒絕的結果，還是先花一次
    Drive 上傳＋Groq 轉錄的額度。這裡也刻意不清除該狀態，讓使用者可以直接補一則打字訊息完成
    最終確認，不用整個流程重來。

    2026-08-02（Robin 釐清 FR-14 其實有兩條規則）：`voice_lockout_store`（獨立於 `state_store`
    的另一個 `ConversationStateStore` 實例，正式環境由 webhook.py 建立並長期持有）記錄「這位
    使用者最近一次是否因單次語音超過 10 分鐘而被鎖定」——這 15 分鐘內語音功能整體關閉，跟
    FR-15 只鎖「修正情境」是兩條獨立規則。呼叫端沒傳的話（例如既有測試不關心這個行為）就地
    建立一個新的、不會跨呼叫共用的 store，等於停用這個檢查，不影響其餘行為。

    2026-08-02（Robin 問鎖定/解除有沒有提醒使用者）：轉錄成功時代表 FR-15 修正窗口正式開始，
    在 `handle_message()` 的回覆後面主動附註一句提醒（見 `_VOICE_TRANSCRIBED_REMINDER`），
    不讓使用者只能靠「又傳一次語音被拒絕」才被動發現被鎖定；鎖定解除本身沒有主動通知
    （機器人是被動回應訊息的架構，沒有排程推播機制，下次互動語音自然就恢復可用）。
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

    if voice.is_locked_out_from_duration_violation(voice_lockout_store, telegram_user_id):
        return _VOICE_DURATION_LOCKOUT_REPLY

    if voice.exceeds_duration_limit(duration_seconds):
        voice.mark_duration_violation(voice_lockout_store, telegram_user_id)
        return _VOICE_DURATION_LIMIT_REPLY
    if voice.is_within_correction_window(db, user["id"]):
        return _VOICE_CORRECTION_WINDOW_REPLY

    # 比照 handle_photo_message：新語音訊息直接覆蓋任何未完成的舊流程狀態，避免卡死。
    state_store.clear(telegram_user_id)

    voice_bytes = telegram_client.get_file_bytes(file_id)
    transcribed_text = voice.transcribe_and_upload(
        db, gdrive_client, voice_client, user["id"], user["role"], voice_bytes, mime_type=mime_type
    )

    # via_voice=True（FR-16a）：讓其餘一般聊天/指令分派也能識別這則訊息是語音轉出來的（目前只有
    # pending_*_final_confirm 這幾個 flow 會用到，其餘分支不受影響）。
    reply = handle_message(
        db, state_store, telegram_user_id, transcribed_text,
        llm_client=llm_client, text_llm_client=text_llm_client, via_voice=True,
        privacy_llm_client=privacy_llm_client, calendar_client=calendar_client,
    )
    # 2026-08-02：主動附註 FR-15 修正窗口提醒，見上方 _VOICE_TRANSCRIBED_REMINDER 說明。
    return reply + _VOICE_TRANSCRIBED_REMINDER


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
    if flow in ("permission_create", "permission_disable", "permission_enable", "permission_resend"):
        # 2026-08-15（Phase 6 第二批 2a，FR-4）：Owner 權限管理選單引導式流程。
        return commands.handle_permission_step(db, state_store, telegram_user_id, text)
    if flow == "important_days":
        # 2026-08-15（Phase 6 第二批 2b，FR-6e／FR-6h）：重要日子新增／編輯多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return important_days.handle_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "important_days_delete_confirm":
        return important_days.handle_delete_confirm_text(state_store, telegram_user_id)
    if flow == "collection":
        # 2026-08-16（Phase 6 第二批 2d，FR-6e／FR-6h／FR-75）：收藏清單新增／編輯多步驟流程。
        user = _get_identified_user(db, telegram_user_id)
        if user is None:
            return _PERMISSION_DENIED_REPLY
        return collections.handle_step(db, state_store, telegram_user_id, user["id"], text)
    if flow == "collection_delete_confirm":
        return collections.handle_delete_confirm_text(state_store, telegram_user_id)
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
    if flow == "pending_user_knowledge":
        # 2026-07-31（ADR-6）：不再無條件把這則訊息當成答案存檔，改由同一次 LLM 呼叫判斷
        # 這是在提供答案、拒絕記錄、還是問了個無關的新問題，見 chat.handle_chat_message。
        return chat.handle_chat_message(
            db, llm_client, text_llm_client, state_store, telegram_user_id,
            state["target_user_id"], text, pending_question=state.get("original_question"),
            privacy_llm_client=privacy_llm_client,
        )
    if flow == "pending_name_confirm":
        # 2026-08-01（ADR-7）：打字誤植改為先反問確認，等使用者這則回覆才真正回答原本的問題。
        return chat.handle_chat_message(
            db, llm_client, text_llm_client, state_store, telegram_user_id,
            state["target_user_id"], text, confirming_question=state.get("original_question"),
            privacy_llm_client=privacy_llm_client,
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
    # 2026-08-02（Step 1.7，見 robinson SPEC.md FR-31、FR-31a、FR-32）：待辦事項新增（三輪反問）
    # 與查詢清單後標記完成/取消，各自對應的 flow 分派，見 commands.py 模組內「待辦事項」區塊說明。
    if flow == "pending_todo_confirm":
        return commands.handle_todo_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_time":
        return commands.handle_todo_time_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_reminder":
        return commands.handle_todo_reminder_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_todo_calendar_sync":
        # 2026-08-05（FR-66a、ADR-17）：新增待辦事項流程的最後一輪，確定後才真正寫入 todos。
        return commands.handle_todo_calendar_sync_step(
            db, llm_client, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
    if flow == "pending_todo_list_action":
        return commands.handle_todo_list_action_step(db, state_store, telegram_user_id, text)
    if flow == "pending_todo_action_confirm":
        return commands.handle_todo_action_confirm_step(
            db, llm_client, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
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
    if flow == "pending_finance_budget_global_confirm":
        return commands.handle_finance_budget_global_confirm_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_finance_budget_override_confirm":
        return commands.handle_finance_budget_override_confirm_step(llm_client, state_store, telegram_user_id, text)
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
        return commands.handle_transaction_note_step(
            db, state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_transaction_list_action":
        return commands.handle_transaction_list_action_step(state_store, telegram_user_id, text)
    if flow == "pending_transaction_action_choice":
        return commands.handle_transaction_action_choice_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_transaction_delete_confirm":
        return commands.handle_transaction_delete_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    # 2026-08-04（Step 2.2，見 robinson SPEC.md FR-45～FR-48）：體態管理多輪對話流，結構比照記帳。
    if flow == "pending_height_value":
        return commands.handle_height_value_step(db, state_store, telegram_user_id, text)
    if flow == "pending_waist_value":
        # 2026-08-08 追加（FR-46 擴充）：設定腰圍，單輪，設計與身高完全對稱。
        return commands.handle_waist_value_step(db, state_store, telegram_user_id, text)
    if flow == "pending_waist_offer":
        # 2026-08-08 追加（FR-46 擴充）：記體重後「順便問要不要記腰圍」的回覆，見
        # commands.handle_weight_value_step() 的觸發時機說明。
        return commands.handle_waist_offer_step(db, state_store, telegram_user_id, text)
    if flow == "pending_weight_backfill_date":
        return commands.handle_weight_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_weight_value":
        return commands.handle_weight_value_step(
            db, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
    if flow == "pending_weight_list_action":
        return commands.handle_weight_list_action_step(state_store, telegram_user_id, text)
    if flow == "pending_weight_action_choice":
        return commands.handle_weight_action_choice_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_weight_delete_confirm":
        return commands.handle_weight_delete_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_exercise_backfill_date":
        return commands.handle_exercise_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_exercise_activity":
        return commands.handle_exercise_activity_step(state_store, telegram_user_id, text)
    if flow == "pending_exercise_duration":
        return commands.handle_exercise_duration_step(state_store, telegram_user_id, text)
    if flow == "pending_exercise_heart_rate":
        return commands.handle_exercise_heart_rate_step(llm_client, state_store, telegram_user_id, text)
    # 2026-08-16（Phase 6 第二批 2c）：理由同心情小記的 pending_mood_confirm／mood_delete_confirm。
    if flow == "pending_exercise_confirm":
        return commands.handle_exercise_confirm_text(state_store, telegram_user_id)
    if flow == "exercise_delete_confirm":
        return commands.handle_exercise_confirm_text(state_store, telegram_user_id)
    if flow == "pending_diet_backfill_date":
        return commands.handle_diet_backfill_date_step(llm_client, state_store, telegram_user_id, text)
    if flow == "pending_diet_entry_type":
        return commands.handle_diet_entry_type_step(state_store, telegram_user_id, text)
    if flow == "pending_diet_description":
        return commands.handle_diet_description_step(
            db, llm_client, state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_diet_water_amount":
        return commands.handle_diet_water_amount_step(db, state_store, telegram_user_id, text)
    if flow == "pending_diet_list_action":
        return commands.handle_diet_list_action_step(state_store, telegram_user_id, text)
    if flow == "pending_diet_action_choice":
        return commands.handle_diet_action_choice_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_diet_delete_confirm":
        return commands.handle_diet_delete_confirm_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_goal_type":
        return commands.handle_goal_type_step(state_store, telegram_user_id, text)
    if flow == "pending_goal_weight_value":
        return commands.handle_goal_weight_value_step(db, state_store, telegram_user_id, text)
    if flow == "pending_goal_exercise_minutes":
        return commands.handle_goal_exercise_minutes_step(state_store, telegram_user_id, text)
    if flow == "pending_goal_diet_description":
        return commands.handle_goal_diet_description_step(
            state_store, telegram_user_id, text, privacy_llm_client=privacy_llm_client
        )
    if flow == "pending_goal_deadline":
        return commands.handle_goal_deadline_step(db, llm_client, state_store, telegram_user_id, text)
    if flow == "pending_goal_calendar_sync":
        # 2026-08-05（FR-66c、ADR-17）：只有講清楚期限的目標才會走到這一題，見 handle_goal_deadline_step。
        return commands.handle_goal_calendar_sync_step(
            db, llm_client, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
    if flow == "pending_goal_list_action":
        return commands.handle_goal_list_action_step(db, state_store, telegram_user_id, text)
    if flow == "pending_goal_cancel_confirm":
        return commands.handle_goal_cancel_confirm_step(
            db, llm_client, state_store, telegram_user_id, text, calendar_client=calendar_client
        )
    # 2026-08-04（Step 2.3，見 robinson SPEC.md FR-53）：設定家人生日，結構比照 /set_toggle。
    if flow == "pending_family_birthday_select":
        return commands.handle_family_birthday_select_step(db, state_store, telegram_user_id, text)
    if flow == "pending_family_birthday_date":
        return commands.handle_family_birthday_date_step(db, state_store, telegram_user_id, text)
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
    # 2026-08-08 追加（Step 3.4，見 robinson SPEC.md FR-57a、ADR-21）：YouTube 技術情報主題管理。
    if flow == "pending_youtube_topic_add":
        return commands.handle_youtube_topic_add_step(db, state_store, telegram_user_id, text)
    if flow == "pending_youtube_topic_remove":
        return commands.handle_youtube_topic_remove_step(db, state_store, telegram_user_id, text)
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
    if flow == "pending_complaint_content":
        # 2026-08-02（Step 1.9，見 robinson SPEC.md FR-61、FR-62）：寫入客訴＋Gemini 分析私訊 Robin。
        return commands.handle_complaint_content_step(
            db, llm_client, telegram_client, state_store, telegram_user_id, text,
            privacy_llm_client=privacy_llm_client,
        )
    return commands.handle_toggle_step(db, state_store, telegram_user_id, text)
