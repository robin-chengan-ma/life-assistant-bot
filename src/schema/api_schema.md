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
**對應 FR**：FR-1、FR-2、FR-5～FR-8

**備註**：所有使用者文字/語音訊息的統一入口，內部再依內容路由到 `/rule`、`/function`、`/complaint` 或各功能模組的處理邏輯。目前僅處理純文字訊息，貼圖/照片等非文字更新一律忽略（Step 1.1 範圍外）。

---

### `/rule`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_rule`）
**觸發方式**：使用者於對話框輸入「我要看使用規則」或 `/rule`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-6d、FR-55

**Response**：固定文字，見 `docs/specs/robinson/SPEC.md` 附錄 A，不經過 LLM 生成。

---

### `/function`（內部路由，非對外 HTTP 端點）

**狀態**：已實作（`src/bot/commands.py::handle_function`），文案為 MVP 簡易版
**觸發方式**：使用者於對話框輸入「我要看所有功能」或 `/function`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-56

**備註**：回傳所有功能清單並註記 Owner 專屬 vs 一般使用者可用；實際文字模板待有產品原型後補上（見 SPEC.md 附錄 B）。

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
