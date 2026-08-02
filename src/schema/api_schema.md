# Robinson API Schema

> 本文件記錄 Robinson 對外／內部使用的所有 API 路由，包含 Telegram webhook 入口與內建指令路由。依 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) 的 ADR-10，與 `db_schema.md` 同樣視為活文件，隨開發進度更新；狀態欄位標記 `計畫中` / `已實作`，實作完成後記得回來更新狀態。

## 使用方式

新增一個路由時，複製下方樣板填入實際內容。

```markdown
### `<METHOD> <path>`

**狀態**：計畫中 / 已實作
**觸發方式**：<Telegram 文字/指令 或 HTTP 呼叫方式>
**權限**：<任何人 / 已驗證使用者 / 僅 Owner>
**對應 FR**：<FR-xx>

**Request**：
​```json
{}
​```

**Response**：
​```json
{}
​```

**備註**：
```

---

## 路由清單

### `GET /healthz`

**狀態**：已實作，已部署上線（`https://life-assistant-bot-yhkm.onrender.com/healthz`）
**觸發方式**：cron-job.org 每 10 分鐘呼叫一次
**權限**：無需驗證（公開，僅回應健康狀態，不回傳任何使用者資料）
**對應 FR**：FR-3

**Response**：
```json
{"status": "ok"}
```

**備註**：純 keep-alive 用途，避免 Render 免費方案 15 分鐘無請求即休眠。**2026-08-02 新增（Step 1.6，見 robinson SPEC.md FR-21）**：順便觸發 `main._check_neon_capacity()`，借用 cron-job.org 既有的每 10 分鐘呼叫頻率檢查 Neon 資料庫容量，達 80% 門檻時私訊 Robin（`src/bot/monitoring.py` 的 `NeonCapacityMonitor`），不影響本端點回應內容與狀態碼；監控邏輯本身包一層 try/except，絕對不會讓健康檢查端點回傳失敗。**2026-08-02 補充（Step 1.7，見 FR-31a、FR-32）**：同一個 10 分鐘頻率也順便觸發 `main._check_todo_pushes()`——把逾期的待辦標記為 `expired`、推播前 30 分鐘提醒、台灣時間 08 點推播當天待辦摘要（`src/bot/todo.py`），同樣包一層 try/except 不影響本端點。

---

### `POST /telegram/webhook`

**狀態**：已實作（見 [platform-auth SPEC.md](../../docs/specs/platform-auth/SPEC.md)，`src/bot/webhook.py`）
**觸發方式**：Telegram Bot API 主動推送使用者訊息
**權限**：依訊息內容與使用者身分於內部再判斷（通關密碼驗證、功能開關等）
**對應 FR**：FR-1、FR-2、FR-5～FR-8、FR-17

**備註**：所有使用者文字/圖片訊息的統一入口，內部依訊息類型分三路：① `document`/`video`/`video_note`/`animation`/`sticker` 等不支援格式 → 直接回覆固定拒絕文案，不進入 DB/Gemini 流程；② 圖片訊息（`message.photo`）→ 呼叫 `router.handle_photo_message()`（見下方「圖片訊息」路由）；③ 其餘文字訊息 → 依內容路由到 `/rule`、`/function`、`/complaint` 或各功能模組的處理邏輯。`voice`/`audio` 依規格本來就該支援，Step 1.4 實作前暫沿用「忽略、不回覆」的既有行為。**2026-07-31 新增（platform-auth SPEC.md FR-7）**：`handle_message()`／`handle_photo_message()` 拋出未預期例外時（例如 Gemini API 額度超限），一律記錄 Traceback、回覆固定安全用語，並仍回傳 HTTP 200——避免 Telegram 因收不到 200 而重送同一則訊息，形成重試風暴加速燒 API 額度。**2026-08-02 補充（Step 1.6，見 FR-19a）**：記錄的 Traceback 附上「觸發功能」（photo/voice/text）與使用者輸入摘要，並額外私訊 Robin 完整原始內容（`webhook._notify_robin_of_error()`），讓他自己判斷原因；FR-19f／FR-19g 的「一般感冒級／重大疾病級」分級降級仍待 Phase 2 Step 2.6。

---

### `/rule`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_rule`）
**觸發方式**：使用者於對話框輸入「我要看使用規則」或 `/rule`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-6d、FR-55

**Response**：固定文字，見 `docs/specs/robinson/SPEC.md` 附錄 A，不經過 LLM 生成。

---

### `/recovered`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_recovered`，2026-08-02，Step 1.6，見 robinson SPEC.md FR-20）
**觸發方式**：Robin 於對話框輸入 `/recovered`
**權限**：僅 Owner（Robin）
**對應 FR**：FR-20

**Response**：文字，回報實際成功通知的家人人數（例如「好的！已經通知 2 位家人我恢復正常運作了！」）

**備註**：Phase 1 沒有 Step 2.4 的 AI 自主修復／GitHub PR 機制，「有沒有修好」完全由 Robin 自己判斷，這個指令只負責「廣播」這個動作本身——查詢所有已綁定家人（`users.telegram_user_id IS NOT NULL AND is_owner = FALSE`），逐一發送固定的「我康復了」文案；刻意排除 Robin 自己（他就是下指令的人，不需要廣播給自己）；單一家人傳送失敗不影響其他人，記錄失敗但繼續廣播下一位。非 Owner 輸入 `/recovered` 不會觸發任何動作，會落入一般聊天核心當成普通文字處理。

---

### `/function`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_function`，Step 1.3a／ADR-4 改版，見 chat-core SPEC.md FR-9）
**觸發方式**：使用者於對話框輸入「我要看所有功能」或 `/function` → 回傳總覽；使用者針對特定功能追問細節時（例如「記帳功能可以做什麼？」）不走此路由，改落入一般聊天核心（見下方 Webhook 路由）
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-56、FR-56a～FR-56c、chat-core SPEC.md FR-9

**備註**：總覽階段組 prompt（Robinson 人格背景 + `templates.build_function_overview_raw_text()`）呼叫一次 LLM（`GEMINI_API_BOT_KEY`）改寫成口語，只列功能名稱＋一句話簡述＋權限標記，不展開細節或範例；細節與情境範例（`templates.build_function_manual_text()`）併入一般聊天核心的 context，由 LLM 依使用者提問自行判斷是否回答。實際文字模板排版待有產品原型後再美化（見 robinson SPEC.md 附錄 B）。

---

### `/my_todos`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_todo_list`，2026-08-02，Step 1.7，見 robinson SPEC.md FR-32；2026-08-02 追加支援 FR-31b 區間顯示）
**觸發方式**：使用者於對話框輸入「我的待辦事項」或 `/my_todos`
**權限**：任何已驗證使用者（Robin 或家人，各自只能看到自己的待辦）
**對應 FR**：FR-31b、FR-32

**Response**：文字，列出目前 `status='pending'` 的待辦事項清單（依預定時間由近到遠排序），沒有資料時回「目前沒有待辦事項喔！」；有資料時額外附上「輸入編號可標記完成/取消」的提示，並進入 `pending_todo_list_action` 狀態等待下一則訊息。單一時間點待辦顯示單一時間（例如「2026/08/02 15:00」），區間待辦（FR-31b，`start_at` 非 NULL）顯示「開始 ～ 結束」（例如「2026/08/02 08:00 ～ 2026/08/05 17:00」）。

**備註**：這是 FR-32「使用者主動查詢」的入口；選定編號後（`pending_todo_list_action`）會反問「標記為完成還是取消」，下一輪由 LLM 判斷使用者意思（`pending_todo_action_confirm`，比照全專案既有的 CONFIRM/CANCEL 單次呼叫慣例）寫入 `status='completed'`／`'cancelled'`（FR-31a）。新增待辦不是走這支路由觸發，而是使用者在一般聊天中自然語言描述「什麼時候要做什麼事」時，由 `chat.py` 的 `_REQUEST_TODO_MARKER` 偵測後進入 `pending_todo_confirm`→`pending_todo_time`→`pending_todo_reminder` 三輪反問流程（見 chat-core 一般聊天路由、`src/bot/commands.py` 的 `handle_todo_confirm_step`／`handle_todo_time_step`／`handle_todo_reminder_step`），確認提醒設定後才真正寫入 `todos`（FR-31）；`handle_todo_time_step` 若判斷使用者描述的是有明確開始與結束的時間區間（FR-31b，例如「8/2早上8點到8/5下午5點」），會多解析出一個 `start_at`，兩個時間點都要同時滿足「日期明確」「時段不歧義」兩個條件才算 CLEAR，缺一就反問，不會自己猜。

---

### `/mood_journal`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_mood_journal`，2026-08-02，Step 1.8，見 robinson SPEC.md FR-49）
**觸發方式**：使用者於對話框輸入「我想做心情筆記」或 `/mood_journal`
**權限**：任何已驗證使用者（Robin 或家人，各自只會記到自己的心情小記）
**對應 FR**：FR-49、FR-50、FR-56h

**Response**：文字，依序走三輪反問：先回傳心情分類清單（`mood.format_category_prompt()`，固定 6 選一，接受編號或直接輸入分類名稱）→ 分類選定後問「給我完整的日記內容」→ 日記內容寫入 `mood_journals` 後主動追問 FR-50 個人成就三選一提示，使用者可輸入既有的「結束」／「沒有了」跳過。

**備註**：全程不需要呼叫 LLM——心情分類固定 6 選一、個人成就「有填就存沒填就跳過」，純字串比對即可完成，跟 Step 1.7 待辦事項需要 LLM 解析模糊自然語言時間的架構不同。日記內容與個人成就回答都是自由文字，可能含個資，寫入 `mood_journals` 前一律先過 `privacy.mask_text()`（見 docs/specs/privacy-masking/SPEC.md FR-4），跟一般聊天／圖片說明文字／語音轉文字三個既有入口的防線一致，`detected=True` 時在回覆最後附加提醒文案。

---

### `/complaint`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_complaint`／`handle_complaint_content_step`，2026-08-02，Step 1.9，見 robinson SPEC.md FR-60～FR-63）
**觸發方式**：使用者於對話框輸入「我要客訴你」或 `/complaint`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-60～FR-63

**Response**：固定文字「請問你覺得哪個地方需要改進呢？」（不經過 LLM，FR-60），接著進入等待客訴內容狀態（`pending_complaint_content`）；下一則訊息視為客訴內容，寫入 `complaints` 後回覆「已經收到你的意見了，謝謝你的回饋，我會把這件事轉達給 Robin 知道！」（FR-61）。

**備註**：客訴內容寫入 `complaints` 前一律先過 `privacy.mask_text()`（見 docs/specs/privacy-masking/SPEC.md FR-4），跟一般聊天／圖片說明文字／語音轉文字／心情小記四個既有入口的防線一致——FR-62 的隱私例外只針對「Robin 平常看不到家人個別對話」（FR-10/FR-11）這條資料隔離規則，跟「個資不能明碼存檔/送外部 API」（FR-13）是不同層面的隱私考量，兩者不衝突。寫入成功後立即呼叫 Gemini（`complaint.build_analysis_prompt()`）分析出「可能問題點」與「修正/優化建議」，私訊給 Robin（查 `users` 表 `is_owner=TRUE` 那筆記錄的 `telegram_user_id`），分析報告**不會**回傳給提出客訴的使用者本人；分析／私訊這段包一層 try/except，Gemini 額度用盡、Telegram 傳送失敗、或 Robin 尚未有 `users` 記錄（理論上不該發生）都只記錄 log，不影響客訴內容已成功記錄這個結果。FR-63 的人工決策與後續討論純屬 Robin 自己的產品判斷，不涉及程式碼，沒有對應的實作。

---

### `/set_invite_codes`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_set_invite_codes`／`handle_set_invite_codes_step`）
**觸發方式**：Robin 輸入 `/set_invite_codes` 或「設定通關密碼」
**權限**：僅 Owner（Robin）
**對應 FR**：FR-6a～FR-6c

**備註**：進入引導式設定對話流（狀態機），詳見 ADR-8；狀態存於記憶體，不落地資料庫（見 platform-auth SPEC.md ADR-2）。

---

### `/my_toggles`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_my_toggles`／`handle_toggle_step`）
**觸發方式**：使用者於對話框輸入「我的功能設定」或 `/my_toggles`
**權限**：任何已驗證使用者（Robin 或家人），僅能操作自己的開關
**對應 FR**：FR-2、FR-2a（見 [feature-toggles SPEC.md](../../docs/specs/feature-toggles/SPEC.md) FR-1）

**備註**：首次觸發會先補齊 8 個功能模組的預設開關資料（`is_enabled=TRUE`），列出附編號的清單；下一則訊息輸入有效編號即切換該項開關。狀態存於記憶體，共用 `src/bot/state.py` 的 `ConversationStateStore`。

---

### `/set_toggle`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::start_set_toggle`／`handle_toggle_step`）
**觸發方式**：Robin 輸入 `/set_toggle` 或「設定家人功能開關」
**權限**：僅 Owner（Robin）
**對應 FR**：FR-2a（見 feature-toggles SPEC.md FR-2）

**備註**：先列出所有已綁定的非 Owner 使用者供選擇，選定後進入與 `/my_toggles` 相同的編號切換畫面，但改的是該使用者的開關；目前沒有任何家人綁定時回覆提示訊息，不進入設定模式。

---

### 一般聊天核心（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/chat.py::handle_chat_message`）
**觸發方式**：路由層最終 fallback —— 訊息不是任何已知指令、也沒有進行中的對話流程時觸發
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-9～FR-12、FR-56c（見 [chat-core SPEC.md](../../docs/specs/chat-core/SPEC.md)）

**備註**：組 context（人格背景＋家人背景＋自己的客製知識庫＋最近 10 則對話紀錄）→ 呼叫 `GEMINI_API_BOT_KEY`（純文字，不查網路）→ 若回覆含系統標記 `【NOT_FOUND】`（代表模型誠實回報不知道），去除標記並附加自行查詢建議，進入 `pending_user_knowledge` 狀態。使用者訊息與 Robinson 回覆皆寫入 `conversation_logs`。這是取代 Step 1.1/1.2 `_PLACEHOLDER_REPLY` 的正式聊天入口。**2026-07-31 修正**：原本開啟 Google Search grounding，因這把 Key 所屬的新專案對 Gemini 2.5 世代關閉存取已移除，見 [chat-core SPEC.md](../../docs/specs/chat-core/SPEC.md) ADR-5。**2026-08-01 新增（FR-11／ADR-8）**：若使用者主動要求「記住」「新增到知識庫」，回覆含系統標記 `【REQUEST_SAVE】`（代表模型判斷這是主動記知識請求，先反問確認內容與分類），去除標記後進入 `pending_save_knowledge_confirm` 狀態，見下方對應路由；`_build_prompt()` 依 `auth.is_owner()` 判斷結果給不同的存放範圍規則（Owner 可選共用或個人範圍，非 Owner 僅個人範圍）。

---

### `pending_user_knowledge`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/chat.py::handle_chat_message`，帶 `pending_question` 參數；2026-07-31 取代 `pending_kb_save`／`handle_pending_kb_save_step`，見 chat-core SPEC.md ADR-5；**2026-07-31 再修正見 ADR-6**：不再有獨立的 `handle_pending_user_knowledge_step()`，功能整併進 `handle_chat_message()`）
**觸發方式**：一般聊天核心回覆「不知道」後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能存入自己的客製知識庫
**對應 FR**：FR-4（見 chat-core SPEC.md）

**備註**：不再無條件把下一則訊息當成答案。同一次 LLM 呼叫會先判斷這則新訊息是「提供答案」（回覆含 `【SAVE_ANSWER】`，才寫入 `knowledge_base`，`category='custom'`）、「拒絕記錄」（回覆含 `【DECLINE_SAVE】`，不寫入）、還是「其實問了個無關的新問題」（不含任何標記，照一般聊天規則正常回答，並清除 pending 狀態，不殘留卡住下一輪）。狀態內容為 `{"flow": "pending_user_knowledge", "target_user_id": <int>, "original_question": <str>}`，`original_question` 供下一輪判斷 prompt 使用。

---

### `pending_name_confirm`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/chat.py::handle_chat_message`，帶 `confirming_question` 參數；見 chat-core SPEC.md ADR-7，部分 supersede ADR-6 的「直接假設打字誤植並回答」機制）
**觸發方式**：一般聊天核心偵測到使用者問的人名疑似打字誤植（同音字/形似字），回覆帶 `【CONFIRM_NAME】` 標記反問確認後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能針對自己上一輪的提問確認
**對應 FR**：FR-3(e)、chat-core SPEC.md ADR-7

**備註**：同一次 LLM 呼叫判斷使用者這則回覆是「確認／講出更明確的名字」（針對原問題完整回答，不再輸出任何標記，也不再反問一次）還是「否認／問了別的事」（當成全新一般訊息正常回答，不假設在回答上一題）。狀態內容為 `{"flow": "pending_name_confirm", "target_user_id": <int>, "original_question": <str>}`，`original_question` 供下一輪判斷 prompt 使用。

---

### `/clean-all-dialog`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（觸發即進入確認流程，`src/bot/commands.py::start_clean_all_dialog_confirm`；**2026-08-01 起不再直接刪除**，見下方 `pending_clean_all_dialog_confirm`）
**觸發方式**：使用者於對話框輸入「我想要刪除所有對話紀錄」或 `/clean-all-dialog`
**權限**：任何已驗證使用者（Robin 或家人），僅能清除自己的對話紀錄
**對應 FR**：chat-core SPEC.md FR-10

**Response**：固定文字「你目前有 {N} 筆對話紀錄，確定要清除嗎？（不會影響你的知識庫內容）」，不經過 LLM 生成；設定 `pending_clean_all_dialog_confirm` 狀態，等使用者下一則回覆確認後才真正執行。

**備註**：實際刪除邏輯在 `commands.handle_clean_all_dialog(db, user_id)`：只清「對話」——`conversation_logs` 軟刪除（`deleted_at` 設為現在時間）＋ `conversation_summaries` 重置為空白摘要（`summary=''`、`summarized_up_to_log_id=0`），刻意不動 `knowledge_base`。與 FR-12 的 `/clean-target-dialog`（使用者說「我想刪除有關...的紀錄」時觸發，會連同該主題的知識庫內容一起清除）明確區隔。**2026-08-01 追加修正**：原本觸發詞一送出就直接刪除，Robin 回報沒有給反悔機會，違反「操作前先確認」原則，改為先反問確認。

---

### `pending_clean_all_dialog_confirm`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_clean_all_dialog_confirm_step`，2026-08-01 新增，見 chat-core SPEC.md FR-10 追加修正）
**觸發方式**：`/clean-all-dialog` 觸發反問確認後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能確認/取消自己的清除請求
**對應 FR**：chat-core SPEC.md FR-10

**備註**：用單次 `GEMINI_API_BOT_KEY` 呼叫判斷使用者這則回覆是「確定」（回覆固定字 `CONFIRM`，才呼叫 `handle_clean_all_dialog()` 真正執行刪除）還是「取消」（回覆固定字 `CANCEL`）；任何非 `CONFIRM` 的判定結果一律視為取消，寧可保守也不誤刪。狀態內容為 `{"flow": "pending_clean_all_dialog_confirm", "target_user_id": <int>}`。

---

### `pending_save_knowledge_confirm`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_save_knowledge_confirm_step`，2026-08-01 新增，見 chat-core SPEC.md FR-11／ADR-8）
**觸發方式**：一般聊天核心偵測到使用者主動要求記住/新增知識，回覆帶 `【REQUEST_SAVE】` 標記反問確認後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者；共用知識庫（`general_family`／`general_persona`）僅 Owner 能實際寫入，非 Owner 一律強制寫進自己的 `custom`（伺服器端依 `auth.is_owner()` 現場判斷，不信任模型判斷結果）
**對應 FR**：chat-core SPEC.md FR-11、ADR-8

**備註**：用單次內部 `GEMINI_API_BOT_KEY` 呼叫（`DECISION`/`CATEGORY`/`LABEL`/`CONTENT` 固定格式，非使用者可見）判斷確定與否並整理出分類標籤與內容；`DECISION=CONFIRM` 才呼叫 `knowledge.save_knowledge()` 真正寫入（`CATEGORY` 依伺服器端權限判斷可能被強制改為 `custom`），`CANCEL`（或任何非 `CONFIRM`）不寫入。狀態內容為 `{"flow": "pending_save_knowledge_confirm", "target_user_id": <int>, "original_request": <str>}`。

---

### `/clean-target-dialog`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（觸發即進入確認流程，`src/bot/commands.py::start_clean_target_dialog_confirm`，2026-08-01 新增，見 chat-core SPEC.md FR-12／ADR-8）
**觸發方式**：使用者於對話框輸入 `/clean-target-dialog <主題>` 或「我想刪除有關 OOO 的紀錄」（`router.py` 用 regex `_CLEAN_TARGET_DIALOG_PATTERN` 擷取主題）
**權限**：任何已驗證使用者；共用知識庫（`general_family`／`general_persona`）只有 Owner 觸發時才會納入候選並可被刪除，非 Owner 只能清自己的 `conversation_logs` 與自己的 `custom` 知識庫
**對應 FR**：chat-core SPEC.md FR-12、ADR-8

**Response**：候選中沒有任何資料、或候選裡沒有跟主題相關的項目時，直接回覆固定文案且不進入確認流程；有匹配時回覆「找到 N 則對話紀錄、M 筆知識庫資料跟「主題」有關，確定要清除嗎？」，設定 `pending_clean_target_dialog_confirm` 狀態。

**備註**：候選清單（自己的 `conversation_logs`＋自己的 `custom`，Owner 觸發再加上全部 `general_family`／`general_persona`）交給單次內部 LLM 呼叫判斷「哪些跟這個主題相關」（回傳編號清單或 `NONE`），不是規則式比對。

---

### `pending_clean_target_dialog_confirm`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_clean_target_dialog_confirm_step`，2026-08-01 新增，見 chat-core SPEC.md FR-12／ADR-8）
**觸發方式**：`/clean-target-dialog` 觸發反問確認後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能確認/取消自己觸發的這次清除請求
**對應 FR**：chat-core SPEC.md FR-12、ADR-8

**備註**：用單次內部 `GEMINI_API_BOT_KEY` 呼叫判斷使用者這則回覆是「確定」（`CONFIRM`，才真正執行：`conversation_logs` 軟刪除、`knowledge_base` **硬刪除**——`knowledge_base` 沒有 `deleted_at` 欄位）還是「取消」（`CANCEL`，任何非 `CONFIRM` 一律視為取消，保守優先）。狀態內容為 `{"flow": "pending_clean_target_dialog_confirm", "target_user_id": <int>, "topic": <str>, "log_ids": [...], "kb_ids": [...]}`。

---

### 圖片訊息（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/router.py::handle_photo_message`、`src/bot/image.py::handle_image_message`，Step 1.3b，見 robinson SPEC.md FR-17、ADR-13）
**觸發方式**：使用者傳送圖片訊息（`message.photo`），`webhook.py::_extract_photo` 取出最高解析度的 `file_id` 與 `caption`
**權限**：任何已驗證使用者（Robin 或家人）；未綁定通關密碼者直接回覆提示訊息，不消耗任何 Drive/Gemini 額度
**對應 FR**：FR-17、FR-17a～FR-17c

**備註**：先透過 `TelegramClient.get_file_bytes()` 下載原始圖片 → 上傳原始檔到 Google Drive（`submodules/gdrive/`）並寫入 `media_uploads`（`media_type='image'`）→ `Pillow` 壓縮至 1024×1024 內／JPEG 80%（僅記憶體內處理，不落地存回 Drive）→ 從 `GEMINI_API_IMAGE_KEY1`／`KEY2` 隨機挑一把呼叫 `generate_with_image()`。若 LLM 回覆帶有 `[NEED_CONFIRM]` 標記（表示有看不清楚的地方），進入 `pending_image_confirm` 狀態並把反問文字回給使用者；使用者傳來原有對話流程未完成、又傳新圖片時，會直接清除舊流程狀態、以新圖片為準。

---

### `pending_image_confirm`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/image.py::handle_image_confirm_step`）
**觸發方式**：圖片辨識回覆帶 `[NEED_CONFIRM]` 標記後，下一則文字訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能針對自己剛上傳的圖片澄清
**對應 FR**：FR-17b

**備註**：帶著使用者的澄清文字，重新呼叫同一把 LLM Key、用同一份已壓縮的圖片 bytes（記憶體內狀態，不重新下載）分析一次，這次 prompt 明確要求不能再要求澄清、必須給出最終答案。

---

### 語音訊息（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/router.py::handle_voice_message`、`src/bot/voice.py`，Step 1.4，見 robinson SPEC.md FR-14、FR-15、FR-17、ADR-12、ADR-13）
**觸發方式**：使用者傳送語音訊息（`message.voice`，錄音鍵）或上傳音檔（`message.audio`，例如 MP3/M4A/WAV），`webhook.py::_extract_voice` 同時偵測兩者，取出 `file_id`、`duration`（秒）與 `mime_type`
**權限**：任何已驗證使用者（Robin 或家人）；未綁定通關密碼者直接回覆提示訊息，不消耗任何 Drive/Groq 額度
**對應 FR**：FR-14、FR-15、FR-16a、FR-17

**備註**：FR-14（10 分鐘上限）／FR-15（15 分鐘修正窗口）刻意排在下載語音檔之前檢查（不需要下載/呼叫任何外部服務），避免浪費額度：FR-14 直接用 Telegram 訊息本身帶的 `duration` 秒數判斷；FR-15 查該使用者 `media_uploads` 最近一筆 `audio` 記錄的時間判斷，被擋下的嘗試不會產生新記錄、不會延長窗口。**2026-08-02 補充**：FR-14 其實有兩條規則——規則 1 是「單次語音本身超過 10 分鐘」時語音功能整體鎖定 15 分鐘（`voice.mark_duration_violation()`／`is_locked_out_from_duration_violation()`，用獨立的 `voice_lockout_store`（`ConversationStateStore`，webhook.py 長期持有）記憶體儲存，因為超時的語音不會寫入 `media_uploads`，無法沿用 FR-15 查 DB 的作法）；FR-15 則是「成功轉出文字後 15 分鐘內若想再用語音修正」才鎖，兩者觸發條件不同，鎖定檢查順序為：最終執行確認短路（FR-16a）→ FR-14 規則 1 鎖定中 → FR-14 本則超時（觸發規則 1 的鎖定）→ FR-15 修正窗口。通過檢查後才透過 `TelegramClient.get_file_bytes()` 下載原始語音檔 → 上傳到 Google Drive（`submodules/gdrive/`）並寫入 `media_uploads`（`media_type='audio'`，不落地存壓縮版，語音本身不需要壓縮）→ 呼叫 `submodules/voice/` 的 `VoiceClient`（Groq Whisper）轉出文字。**架構決策**：轉出來的文字不會另外走一套獨立流程，而是直接當成使用者「打字輸入」，呼叫既有的 `handle_message()` 走完整的指令/pending flow/一般聊天分派——語音只負責「變成文字」，「文字要怎麼處理」全部復用既有邏輯。使用者傳來語音時，若原本卡在其他未完成的對話流程，會直接清除舊流程狀態、以這次語音轉出的文字為準（比照圖片訊息的既有慣例），**但 `pending_*_final_confirm` 這三個最終執行確認狀態例外，見下方 FR-16a 說明**。**2026-08-01 修正**：`message.voice` 固定是 OGG/OPUS，但 `message.audio`（使用者上傳的音檔）可能是任意格式，`mime_type` 會一路透傳到 Drive 上傳、檔名副檔名、Groq 轉錄請求三處（見 `voice._infer_extension()`），避免把非 OGG 檔案誤標成 `.ogg`。**2026-08-02 新增（FR-16a，見 chat-core SPEC.md ADR-9）**：`handle_voice_message()` 呼叫 `handle_message()` 時固定帶 `via_voice=True`；若使用者當下卡在 `/clean-all-dialog`／`/clean-target-dialog`／主動記知識的最終執行確認狀態（`pending_*_final_confirm`），這則語音訊息不會清除該狀態，也一律無法通過最終確認，只會提示改用打字——避免語音聽錯直接誤觸不可逆操作。**2026-08-02 追加優化**：這個檢查排在下載/轉錄之前（也排在 FR-14／FR-15 檢查之前），完全不下載語音檔、不呼叫 Groq，比照 FR-14/FR-15「先擋才不浪費額度」的原則，不會為了一個註定被拒絕的結果還先花一次 Drive/Groq 額度。**2026-08-02 新增（FR-15 主動提醒）**：語音成功轉出文字、`handle_message()` 回覆組好之後，會在回覆末尾附加 `router._VOICE_TRANSCRIBED_REMINDER` 固定文案，主動告知使用者 FR-15 的 15 分鐘修正窗口已經開始、想修正請改用打字；鎖定「到期」本身沒有主動通知（機器人是被動回應訊息的架構，沒有排程/推播機制去主動私訊），使用者下次互動時語音自然就恢復可用。

### 個資偵測與遮蔽（跨路由的橫切關注點，非獨立端點）

**狀態**：已實作（`src/bot/privacy.py`，Step 1.5，見 robinson SPEC.md FR-13、FR-13a～FR-13d、[docs/specs/privacy-masking/SPEC.md](../../docs/specs/privacy-masking/SPEC.md)）
**觸發方式**：不是使用者主動觸發的路由，而是掛在既有訊息處理路徑上的前置處理——`chat.handle_chat_message()`（一般聊天、`pending_user_knowledge`／`pending_name_confirm`／`pending_save_knowledge_confirm` 這幾個會呼叫聊天核心的流程）與 `image.handle_image_message()`（圖片說明文字）在組 Prompt、寫入 DB 之前都會先呼叫 `privacy.mask_text()`
**對應 FR**：FR-13、FR-13a～FR-13d

**備註**：雙層防線——第一層 `mask_regex()` 是免費、確定性的 Regex 硬規則，涵蓋身分證字號／手機／市話／銀行帳戶／信用卡號／健保卡號／地址／車牌 8 類台灣常見格式，命中就整段換成固定文字 `[已遮蔽個資]`；第二層 `mask_with_llm()` 是 LLM 語意辨識，補 Regex 抓不到的變形寫法（全形數字、中文數字、額外符號等），用**獨立申請**的 `GEMINI_API_PRIVACY_KEY`（見 privacy-masking SPEC.md ADR-1），不佔用既有聊天/長記憶/圖片辨識用的 Key 配額——因為這一層等於對每一則訊息都多花一次 Gemini 呼叫，考量到本專案先前多次撞到 429，刻意用獨立 Key 隔離額度。這把 Key 是選配的：`webhook.py::_build_privacy_llm_client()` 讀不到 `GEMINI_API_PRIVACY_KEY` 環境變數時回傳 `None`，`mask_text()` 會優雅降級成只跑免費的 Regex 層，不會讓整個訊息處理流程失敗（見 ADR-2）。生日與 LINE ID 明確排除、不遮蔽（FR-13c）。偵測到個資時，除了遮蔽本身，也會在回覆最後附加固定提醒文案，請使用者盡快到 Telegram 對話中自行刪除原始訊息（機器人沒有權限代刪使用者自己傳送的訊息）。**語音**因為轉出文字後統一走既有 `handle_message()` → `chat.handle_chat_message()`，天然涵蓋這道防線，不需要額外處理。**刻意排除範圍**：`commands.start_clean_target_dialog_confirm()`（`/clean-target-dialog`）的搜尋主題 `topic` 不套用遮蔽，因為使用者很可能就是要用個資內容當關鍵字搜尋要刪除的紀錄（例如「我想刪除有關 0912345678 的紀錄」），遮蔽會讓比對用的關鍵字直接消失、刪除功能整支失效；通關密碼、`/set_toggle`／`/my_toggles` 編號選擇、FR-16a 最終確認關鍵字等純控制流程文字同樣不套用，因為這些不是「使用者傳送的個資內容」，是比對用的固定格式輸入。
