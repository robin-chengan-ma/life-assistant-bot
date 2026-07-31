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

**備註**：純 keep-alive 用途，避免 Render 免費方案 15 分鐘無請求即休眠。

---

### `POST /telegram/webhook`

**狀態**：已實作（見 [platform-auth SPEC.md](../../docs/specs/platform-auth/SPEC.md)，`src/bot/webhook.py`）
**觸發方式**：Telegram Bot API 主動推送使用者訊息
**權限**：依訊息內容與使用者身分於內部再判斷（通關密碼驗證、功能開關等）
**對應 FR**：FR-1、FR-2、FR-5～FR-8、FR-17

**備註**：所有使用者文字/圖片訊息的統一入口，內部依訊息類型分三路：① `document`/`video`/`video_note`/`animation`/`sticker` 等不支援格式 → 直接回覆固定拒絕文案，不進入 DB/Gemini 流程；② 圖片訊息（`message.photo`）→ 呼叫 `router.handle_photo_message()`（見下方「圖片訊息」路由）；③ 其餘文字訊息 → 依內容路由到 `/rule`、`/function`、`/complaint` 或各功能模組的處理邏輯。`voice`/`audio` 依規格本來就該支援，Step 1.4 實作前暫沿用「忽略、不回覆」的既有行為。**2026-07-31 新增（platform-auth SPEC.md FR-7）**：`handle_message()`／`handle_photo_message()` 拋出未預期例外時（例如 Gemini API 額度超限），一律記錄 Traceback、回覆固定安全用語，並仍回傳 HTTP 200——避免 Telegram 因收不到 200 而重送同一則訊息，形成重試風暴加速燒 API 額度；完整錯誤分級處理仍待 robinson SPEC.md Step 1.6。

---

### `/rule`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_rule`）
**觸發方式**：使用者於對話框輸入「我要看使用規則」或 `/rule`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-6d、FR-55

**Response**：固定文字，見 `docs/specs/robinson/SPEC.md` 附錄 A，不經過 LLM 生成。

---

### `/function`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_function`，Step 1.3a／ADR-4 改版，見 chat-core SPEC.md FR-9）
**觸發方式**：使用者於對話框輸入「我要看所有功能」或 `/function` → 回傳總覽；使用者針對特定功能追問細節時（例如「記帳功能可以做什麼？」）不走此路由，改落入一般聊天核心（見下方 Webhook 路由）
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-56、FR-56a～FR-56c、chat-core SPEC.md FR-9

**備註**：總覽階段組 prompt（Robinson 人格背景 + `templates.build_function_overview_raw_text()`）呼叫一次 LLM（`GEMINI_API_BOT_KEY`）改寫成口語，只列功能名稱＋一句話簡述＋權限標記，不展開細節或範例；細節與情境範例（`templates.build_function_manual_text()`）併入一般聊天核心的 context，由 LLM 依使用者提問自行判斷是否回答。實際文字模板排版待有產品原型後再美化（見 robinson SPEC.md 附錄 B）。

---

### `/complaint`（內部路由，非對外 HTTP 端點）

**狀態**：計畫中
**觸發方式**：使用者於對話框輸入「我要客訴你」或 `/complaint`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-60～FR-63

**Response**：固定文字「請問你覺得哪個地方需要改進呢？」，接著進入等待客訴內容狀態；下一則訊息視為客訴內容並寫入資料庫。

**備註**：客訴內容會私訊給 Robin 並觸發 Gemini 分析（見 FR-62），此為刻意的隱私例外（見 FR-10/FR-11 的一般資料隔離原則）。

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

**備註**：組 context（人格背景＋家人背景＋自己的客製知識庫＋最近 10 則對話紀錄）→ 呼叫 `GEMINI_API_BOT_KEY` 並開啟 Google Search grounding → 若實際查了網路，回覆後附加詢問是否存入知識庫，進入 `pending_kb_save` 狀態。使用者訊息與 Robinson 回覆皆寫入 `conversation_logs`。這是取代 Step 1.1/1.2 `_PLACEHOLDER_REPLY` 的正式聊天入口。

---

### `pending_kb_save`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/chat.py::handle_pending_kb_save_step`）
**觸發方式**：一般聊天核心觸發 Google Search 後，下一則訊息自動進入此狀態
**權限**：任何已驗證使用者，僅能確認存入自己的客製知識庫
**對應 FR**：FR-4（見 chat-core SPEC.md）

**備註**：同意詞（「要」／「好」／「記錄」／「儲存」／「存」）才寫入 `knowledge_base`（`category='custom'`），其餘輸入一律視為不儲存，不追問第二次。

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
