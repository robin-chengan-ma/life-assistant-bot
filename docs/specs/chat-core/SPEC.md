---
title: Gemini 對話核心 — 知識庫問答、資安隔離、人格化語氣
slug: chat-core
status: implemented
created: 2026-07-30
updated: 2026-07-31
owner: Robin
---

# Gemini 對話核心

## 概要

對應 [robinson SPEC.md](../robinson/SPEC.md) Phase 1 Step 1.3（FR-9～FR-12、FR-56c、ADR-12）。取代 Step 1.1／1.2 目前的 `_PLACEHOLDER_REPLY` 佔位回覆，讓一般聊天訊息真正交給 Gemini 處理。

對話核心的「記憶」由四個部分組成（2026-07-31 Robin 確認）：
1. **短記憶**：最近 10 則 `conversation_logs`，逐字原文
2. **長記憶**：滾動式摘要（`conversation_summaries`），濃縮更久以前的對話重點，見 ADR-3
3. **知識庫**：`general_persona`／`general_family`／使用者自己的 `custom` 知識庫
4. **上網查資料**：知識庫與記憶都沒有答案時，用 Gemini 內建的 Google Search 工具查網路，查到後要先問使用者同不同意存回知識庫

回覆語氣需先參考 Robinson 人格背景，不能像照本宣科的模板。

這是 Step 1.3a（`/function` 改版）與 Step 1.3b（影像辨識）共同的前置依賴——兩者都需要能呼叫 LLM 的基礎能力。

## 需求

### 功能性需求

- [x] FR-1：路由層最終 fallback（不是任何已知指令、也沒有進行中的對話流程）改為呼叫對話核心，取代 `_PLACEHOLDER_REPLY`
- [x] FR-2：Context 組裝 —— 每次呼叫固定帶上：① `general_persona`、② `general_family`（全體共用，不分使用者）、③ 該使用者自己的 `custom` 知識庫（依 FR-10 資安隔離，只查自己的 `user_id`）、④ 該使用者最近 10 則 `conversation_logs`（依時間排序，避免 prompt 無上限成長）
- [x] FR-3：System Prompt 規則 —— 明確指示模型：(a) 用 Robinson 的人格語氣回答，不要照本宣科；(b) 優先根據提供的知識庫內容回答；(c) 知識庫沒有答案時才使用 Google Search 工具查詢
- [x] FR-4：查無答案時的處理（對應 FR-12）—— 單次 API 呼叫即開啟 Google Search grounding 工具，讓模型自行判斷需不需要查；回應的 `grounding_metadata.web_search_queries` 非空即代表這次真的查了網路，此時在回覆後面加上詢問「要不要記錄到你的知識庫」，並進入等待確認狀態（`flow: pending_kb_save`）；使用者下一則訊息若為同意詞（「要」／「好」／「記錄」／「儲存」）則寫入 `knowledge_base`（`category='custom'`，`user_id=`該使用者），其餘輸入一律視為不儲存並結束流程（不追問第二次，避免使用者被迫回應是非題以外的內容）
- [x] FR-5：對話紀錄 —— 只有真正進入一般聊天核心的訊息才記錄：使用者原始輸入寫一筆（`role='user'`），Robinson 的回覆寫一筆（`role='assistant'`）；指令觸發（`/rule`、`/my_toggles` 等）與確認存檔流程本身的輸入/輸出不計入對話紀錄
- [x] FR-6：長記憶查詢 —— Context 組裝時額外帶上該使用者的 `conversation_summaries.summary`（查無資料視為空字串），與短記憶/知識庫一起放進 prompt
- [x] FR-7：長記憶更新（滾動式摘要，對應 ADR-3）—— 每次聊天核心處理完一輪對話後，計算「比短記憶更早、且 `id` 大於 `summarized_up_to_log_id` 」的 backlog 對話則數；backlog ≥ 10 則時，把 backlog 內容連同既有摘要一起丟給 `GEMINI_API_TEXT_KEY`（長文生成用途，見 ADR-12），產出新摘要覆蓋回 `conversation_summaries.summary`，並把 `summarized_up_to_log_id` 推進到 backlog 最新一筆的 `id`；backlog 未達門檻則不觸發，維持原摘要不變
- [x] FR-8：新使用者第一次進入聊天核心時，若 `conversation_summaries` 尚無對應資料列，自動建立一筆空摘要（`summary=''`、`summarized_up_to_log_id=0`），不需要額外走 Owner 審核流程（資料本身沒有預設內容，純粹是佔位）

### 非功能性需求

- [x] NFR-1：範圍界線 —— 本階段不做外部 API 重試/降級機制（NFR-9／FR-19f～i），呼叫失敗直接讓例外往上拋，留到 Step 1.6 統一處理
- [x] NFR-2：安全 —— `custom` 知識庫與 `conversation_logs` 查詢一律帶 `user_id` 條件，不會查到其他使用者的資料（對應 FR-10）
- [x] NFR-3：成本 —— Context 的對話紀錄視窗固定 10 則，避免單次呼叫的 token 用量隨對話變長無上限成長
- [x] NFR-4：成本 —— 長記憶摘要更新採「backlog 累積到門檻才觸發」，不是每則訊息都呼叫，平均每 10 則對話才多一次 `GEMINI_API_TEXT_KEY` 呼叫（對應 ADR-3）

## 設計決策

### ADR-1：查無答案時採「單次 API 呼叫＋Google Search grounding」，而非「先問後查」的兩次呼叫

**背景**：FR-12 要求「查不到答案才上網查」，需要一個機制判斷「知識庫是否足夠回答」。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：單次呼叫，開啟 `google_search` 工具，讓模型自行判斷要不要查，事後看 `grounding_metadata.web_search_queries` 是否非空來判斷有沒有查 | 呼叫次數少、成本低、實作單純 | 判斷「有沒有查網路」的準確度依賴 Gemini 自己的工具呼叫決策，不是我們自己寫規則精準控制 |
| B：先只給知識庫呼叫一次，要求模型在不知道時回傳明確的固定字串（例如 `[NEED_SEARCH]`），偵測到才觸發第二次帶 `google_search` 工具的呼叫 | 「要不要查」的判斷邏輯掌握在我們手上，較可控 | 兩倍 API 呼叫成本；且仍然依賴模型「有沒有老實回傳約定字串」，一樣不是 100% 可控 |

**決策**：採方案 A（2026-07-31 Robin 確認）

**理由**：兩個方案都無法完全避免依賴模型自我判斷，方案 B 只是把「判斷該不該查」換成「判斷該不該回傳約定字串」，可控性沒有實質提升，卻要付兩倍呼叫成本；方案 A 更符合 NFR-1（免費額度優先）與本專案一貫的「不過度工程」原則

**後果**：`submodules/llm/client.py` 新增 `generate_with_search()` 方法，回傳 `(text, used_search)` tuple；`src/bot/chat.py` 依 `used_search` 決定要不要附加詢問存檔的文字並進入 `pending_kb_save` 流程

**狀態**：accepted

### ADR-2：存檔確認流程沿用 `ConversationStateStore`，用 `flow: "pending_kb_save"` 標記

**背景**：FR-4 需要在「查到網路答案」之後，等使用者下一則訊息確認要不要存檔，這是又一種新的多輪對話流程。

**決策**：比照 [feature-toggles SPEC.md](../feature-toggles/SPEC.md) ADR-1 的作法，用同一個 `ConversationStateStore`，新增 `flow: "pending_kb_save"`，狀態內容為 `{"flow": "pending_kb_save", "content": <查到的答案文字>, "user_id": <要存進哪個使用者的 custom 知識庫>}`

**理由**：與既有兩種 flow（`set_invite_codes`、`toggle`/`set_toggle`）一致的機制，路由層只需要多一個 `elif` 分支，不需要新增額外的狀態儲存機制

**狀態**：accepted

### ADR-3：長記憶採「滾動式摘要」，而非全量塞入或向量搜尋

**背景**：Robin 指出短記憶只抓最近 10 則會忘記很久以前的對話，Robinson 作為貼心助理必須也記得久遠的內容。需要一個機制在「記得住重點」與「成本/複雜度可控」之間取捨。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：滾動式摘要 —— 維護一份 `conversation_summaries.summary`，backlog（比短記憶更早、尚未摘要過的對話）累積到門檻就跟既有摘要一起送給 Gemini 濃縮成新摘要 | 成本有上限（不隨對話量無限增長）、不需要額外資料庫技術、實作單純 | 記的是「濃縮過的重點」，不是逐字原文，細節可能模糊 |
| B：全部對話原文塞進 prompt | 完全不會忘記細節 | 對話越多、每次呼叫的 token 用量與費用就越高，最終會超出免費額度或模型 context 上限，不可行 |
| C：語意向量搜尋（RAG）—— 每則訊息存成向量，聊天時搜尋最相關的舊對話 | 能精準挖出久遠對話的細節 | 需要 pgvector 擴充與額外的向量化 API 呼叫，複雜度與成本明顯較高，對個人家用機器人規模而言過度工程 |

**決策**：採方案 A（2026-07-31 Robin 確認）

**理由**：方案 B 在對話量成長後必然不可行，違反 NFR-1（免費額度）與 NFR-3（成本控制）；方案 C 技術上最強，但需要的基礎設施（pgvector、embedding pipeline）對這個規模的個人專案是過度工程，不符合本專案一貫的「不過度工程」原則；方案 A 用最小的新增複雜度（一張表、一個門檻觸發的摘要呼叫）換取「記得住重點」的核心需求

**後果**：
- 新增 `conversation_summaries` 表（`user_id` UNIQUE、`summary`、`summarized_up_to_log_id`、`updated_at`），2026-07-31 Robin 核准建表 SQL（`src/migrations/0007_create_conversation_summaries_table.sql`）
- 新增 `src/bot/memory.py`：`get_or_create_summary_row()`、`maybe_update_summary()`（backlog ≥ 10 才觸發，呼叫 `GEMINI_API_TEXT_KEY`）
- `chat.handle_chat_message()` 新增 `text_llm_client` 參數；`webhook.py` 需額外注入第二把 Gemini Key 的 Client
- 摘要更新失敗（例如 API 錯誤）的處理方式：比照 NFR-1，本階段不特別做重試，讓例外往上拋——但為了不讓「摘要更新失敗」拖垮「這次的聊天回覆」，摘要更新必須放在**已經算出回覆內容之後**執行，且用 `try/except` 包住、失敗僅記錄不影響本次回覆正常送出（摘要頂多晚一輪再更新，不是關鍵路徑）

**狀態**：accepted

## 實作計畫

- [x] Step 1：`submodules/llm/client.py` 新增 `generate_with_search(prompt) -> tuple[str, bool]`，回傳文字與是否使用了 Google Search
- [x] Step 2：`src/bot/knowledge.py` —— `build_context(db, user_id)` 組出四類知識庫內容；`save_custom_knowledge(db, user_id, content)` 寫入 `custom` 知識庫
- [x] Step 3：`src/bot/chat.py` —— `handle_chat_message(db, llm_client, state_store, telegram_user_id, user_id, text)`：組 prompt、呼叫 LLM、寫對話紀錄、判斷是否進入 `pending_kb_save`
- [x] Step 4：`src/bot/commands.py` 或 `chat.py` 新增 `handle_pending_kb_save_step()` 處理確認存檔的下一則訊息
- [x] Step 5：`router.py` 整合：`flow == "pending_kb_save"` 的分派、一般訊息 fallback 改呼叫 `chat.handle_chat_message`
- [x] Step 6：更新 `src/schema/api_schema.md` 標記對話核心路由狀態
- [x] Step 7：`conversation_summaries` migration（Robin 已核准，見 ADR-3），`0007_create_conversation_summaries_table.sql`
- [x] Step 8：`src/bot/memory.py` —— `get_or_create_summary_row()`／`get_summary()`／`maybe_update_summary()`（backlog 計算、門檻觸發、吞例外）
- [x] Step 9：`chat.py` 新增 `text_llm_client` 參數，改為分別呼叫 `knowledge.build_context()` 取得知識庫/短記憶、`memory.get_summary()` 取得長記憶，`_build_prompt()` 加入長記憶區塊；回覆算完並寫入對話紀錄後才呼叫 `memory.maybe_update_summary()`（實際採用「chat.py 各自呼叫兩個模組」而非「揉進 knowledge.build_context() 的回傳值」，讓 `knowledge.py`／`memory.py` 職責分離，`knowledge.py` 本體與既有測試不受影響）
- [x] Step 10：`router.py` 新增 `text_llm_client` 參數並透傳；`webhook.py` 額外注入 `LLMClient(GEMINI_API_TEXT_KEY)`

## 測試策略

### Unit Tests
- [x] `llm.client.LLMClient.generate_with_search()`：mock `genai.Client`，驗證有 `grounding_metadata.web_search_queries` 時回傳 `used_search=True`，沒有或為空時回傳 `False`
- [x] `knowledge.build_context()`：組出正確的四類內容；只查自己的 `custom`／`conversation_logs`（資安隔離）；對話紀錄只取最近 10 則
- [x] `knowledge.save_custom_knowledge()`：正確寫入 `category='custom'`、`user_id`
- [x] `chat.handle_chat_message()`：一般問答（不觸發存檔流程）／觸發 Google Search 後附加詢問文字並設定 `pending_kb_save` 狀態／每次呼叫後對話紀錄各寫入使用者訊息與回覆各一筆
- [x] `pending_kb_save` 確認流程：同意詞寫入知識庫 / 非同意詞不寫入且結束流程
- [x] `memory.maybe_update_summary()`：backlog 未達門檻不觸發／達門檻時呼叫 `GEMINI_API_TEXT_KEY` 並正確覆蓋摘要、推進 `summarized_up_to_log_id`／新使用者自動建立空白摘要列（FR-8）／只考慮自己的對話、排除軟刪除、不重複處理已摘要過的部分／呼叫失敗吞例外不往外拋
- [x] `chat.handle_chat_message()` 整合長記憶：prompt 包含摘要內容；backlog 達門檻時觸發摘要更新

### Integration Tests
- [x] `router.py`：一般聊天訊息完整跑過 `chat.handle_chat_message` 並取得回覆；`pending_kb_save` 狀態下一則訊息正確分派
- [x] 連續對話累積超過門檻則數後，自動觸發一次摘要更新（`test_handle_chat_message_triggers_memory_update_after_reply`）

### E2E Tests
- [x] 完整流程：使用者問一個知識庫沒有的問題 → 觸發 Google Search → 附加詢問 → 回覆「要」→ 確認寫入 `custom` 知識庫

**測試結果**：一般聊天核心（ADR-1/ADR-2）新增 26 個測試，長記憶（ADR-3）再新增 13 個（`test_memory.py` 11 個、`test_chat.py`／`test_webhook.py` 長記憶整合部分共 2 個），全專案總計 117 個測試全過、`src/bot/` 與 `submodules/llm/` 覆蓋率皆維持 100%（`pytest tests/ --cov=src/bot --cov=submodules/llm`）。

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
|------|--------|------|----------|
| 模型判斷「要不要查網路」不夠精準（ADR-1 已知取捨） | 低 | 中 | 這是刻意接受的簡化取捨，且 System Prompt 已明確要求優先用知識庫；後續若發現誤判頻繁，再評估升級為方案 B |
| 對話紀錄視窗固定 10 則，可能漏掉更早的重要上下文 | 低 | 低 | 對應 NFR-3 的成本考量，屬於刻意取捨；若之後發現使用者常提到更早的內容，可再評估加大視窗或摘要機制 |
| Gemini 呼叫失敗（額度用盡、網路錯誤等）目前直接拋例外，使用者會看到不友善的錯誤 | 中 | 中 | 已在 NFR-1 明確排除在本階段範圍外，Step 1.6 會補上統一的錯誤處理與「生病了」友善提示 |
| 長記憶摘要多次滾動濃縮後可能失真或遺漏細節（ADR-3 已知取捨） | 低 | 中 | 短記憶（最近 10 則原文）與知識庫仍保有精確資訊，摘要只補「更早以前」的粗略脈絡，不是唯一資訊來源；若之後發現失真嚴重，可再評估升級為向量搜尋（ADR-3 方案 C） |
| 摘要更新呼叫（`GEMINI_API_TEXT_KEY`）失敗，可能拖慢或影響本次聊天回覆 | 低 | 低 | ADR-3 明訂摘要更新在回覆算完之後才執行，且用 `try/except` 包住，失敗只跳過本次摘要更新，不影響聊天回覆本身送出 |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
|------|----------|--------|
| 2026-07-31 | 初版建立，展開 robinson SPEC.md Phase 1 Step 1.3 為獨立 spec，記錄 ADR-1（單次呼叫+Google Search grounding，Robin 確認）、ADR-2（pending_kb_save 狀態流程設計） | Claude（依 Robin「繼續開發 Step 1.3 吧」指示） |
| 2026-07-31 | ADR-1／ADR-2 完成 TDD 實作：`submodules/llm/client.py` 新增 `generate_with_search()`；新增 `src/bot/knowledge.py`（知識庫查詢/寫入）、`src/bot/chat.py`（對話核心＋存檔確認流程）；`router.py` 最終 fallback 改呼叫聊天核心（移除 `_PLACEHOLDER_REPLY`），`webhook.py` 注入 `LLMClient`（`GEMINI_API_BOT_KEY`）；全專案 104 個測試全過、覆蓋率 100% | Claude |
| 2026-07-31 | Robin 指出對話記憶只有短記憶會忘記久遠對話，確認記憶架構改為「長記憶＋短記憶＋知識庫＋上網查資料」四部分；新增 ADR-3：長記憶採滾動式摘要（而非全量塞入或向量搜尋），待 Robin 核准 `conversation_summaries` 建表 SQL 後展開實作 | Robin |
| 2026-07-31 | Robin 核准 `conversation_summaries` 建表 SQL（含中文 comment），完成 ADR-3 TDD 實作：新增 `src/bot/memory.py`（`get_or_create_summary_row`／`get_summary`／`maybe_update_summary`，backlog ≥10 才觸發、呼叫 `GEMINI_API_TEXT_KEY`、吞例外不影響本次回覆）；`chat.py` 整合長記憶到 prompt 並在回覆後觸發摘要更新；`router.py`／`webhook.py` 注入第二把 `GEMINI_API_TEXT_KEY` 的 `LLMClient`；全專案 117 個測試全過、覆蓋率 100% | Claude |
