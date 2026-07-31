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
4. **不知道就誠實說**（2026-07-31 修正，見 ADR-5，supersede ADR-1）：知識庫與記憶都沒有答案時，不再上網查詢（Gemini 2.5 世代已對新專案關閉存取，grounding 整條路走不通），改為誠實回覆不知道，並建議使用者自行查詢後把答案提供給 Robinson 記錄

回覆語氣需先參考 Robinson 人格背景，不能像照本宣科的模板。

這是 Step 1.3a（`/function` 改版）與 Step 1.3b（影像辨識）共同的前置依賴——兩者都需要能呼叫 LLM 的基礎能力。

## 需求

### 功能性需求

- [x] FR-1：路由層最終 fallback（不是任何已知指令、也沒有進行中的對話流程）改為呼叫對話核心，取代 `_PLACEHOLDER_REPLY`
- [x] FR-2：Context 組裝 —— 每次呼叫固定帶上：① `general_persona`、② `general_family`（全體共用，不分使用者）、③ 該使用者自己的 `custom` 知識庫（依 FR-10 資安隔離，只查自己的 `user_id`）、④ 該使用者最近 10 則 `conversation_logs`（依時間排序，避免 prompt 無上限成長）
- [x] FR-3：System Prompt 規則 —— 明確指示模型：(a) 用 Robinson 的人格語氣回答，不要照本宣科；(b) 只根據提供的知識庫內容回答，明確告知模型自己沒有查詢網路的能力；(c) 知識庫沒有答案時必須誠實回報不知道（2026-07-31 修正，見 ADR-5）；(d)（2026-07-31 追加）真實日期由伺服器本地算出（`Asia/Taipei` 時區）直接塞進 prompt，日期／星期問題一律以此為準，不可自行推算或憑印象亂猜；除 prompt 內明確提供的資料外絕對不能捏造具體事實（例如生日、事件細節、數字）——起因是 Robin 回報問「今天幾月幾號」時模型瞎掰錯誤日期並編造「剛好是我生日」，LLM 本身沒有即時時鐘，移除 grounding 後更無管道查證，日期屬於伺服器本地就能算出的資訊，不需要任何外部 API
- [x] FR-4：查無答案時的處理（對應 FR-12，2026-07-31 修正，見 ADR-5，supersede 原本的 Google Search grounding 設計）—— 單次 API 呼叫（`generate_text`，不掛任何工具）；prompt 指示模型在資料不足以回答時，於回覆最後加上固定標記 `【NOT_FOUND】`；`chat.py` 偵測到標記後，去除標記並附加「你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！」，同時進入等待使用者提供答案的狀態（`flow: pending_user_knowledge`）；使用者下一則訊息直接視為要存入的內容，寫入 `knowledge_base`（`category='custom'`，`user_id=`該使用者），不需要額外的 yes/no 確認（使用者已被明確告知「下一則輸入會被記錄」）
- [x] FR-5：對話紀錄 —— 只有真正進入一般聊天核心的訊息才記錄：使用者原始輸入寫一筆（`role='user'`），Robinson 的回覆寫一筆（`role='assistant'`）；指令觸發（`/rule`、`/my_toggles` 等）與確認存檔流程本身的輸入/輸出不計入對話紀錄
- [x] FR-6：長記憶查詢 —— Context 組裝時額外帶上該使用者的 `conversation_summaries.summary`（查無資料視為空字串），與短記憶/知識庫一起放進 prompt
- [x] FR-7：長記憶更新（滾動式摘要，對應 ADR-3）—— 每次聊天核心處理完一輪對話後，計算「比短記憶更早、且 `id` 大於 `summarized_up_to_log_id` 」的 backlog 對話則數；backlog ≥ 10 則時，把 backlog 內容連同既有摘要一起丟給 `GEMINI_API_TEXT_KEY`（長文生成用途，見 ADR-12），產出新摘要覆蓋回 `conversation_summaries.summary`，並把 `summarized_up_to_log_id` 推進到 backlog 最新一筆的 `id`；backlog 未達門檻則不觸發，維持原摘要不變
- [x] FR-8：新使用者第一次進入聊天核心時，若 `conversation_summaries` 尚無對應資料列，自動建立一筆空摘要（`summary=''`、`summarized_up_to_log_id=0`），不需要額外走 Owner 審核流程（資料本身沒有預設內容，純粹是佔位）
- [x] FR-9：`/function` 改版（Step 1.3a，對應 robinson SPEC.md FR-56、FR-56a～FR-56c，見 ADR-4）—— 「總覽」與「細節追問」兩階段：
  - [x] FR-9a：總覽 —— 觸發 `/function` 或「我要看所有功能」時，`commands.handle_function(db, llm_client)` 組 prompt（Robinson 人格背景 + `templates.build_function_overview_raw_text()` 原始清單）呼叫一次 LLM，回傳人格化改寫過的功能總覽（僅名稱＋一句話簡述＋權限標記，不展開細節或範例）
  - [x] FR-9b：細節追問 —— 使用者用自然語言追問特定功能（例如「記帳功能可以做什麼？」）時，不走 `/function` 路由，直接落入一般聊天核心；`chat._build_prompt()` 固定附上 `templates.build_function_manual_text()`（完整功能手冊，含 FR-56d～FR-56h 情境範例），並指示 LLM 只有使用者明確詢問時才依此回答且需附範例，一般聊天不主動提起

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

**後果**：`submodules/llm/client.py` 新增 `generate_with_search()` 方法，回傳 `(text, used_search)` tuple；`src/bot/chat.py` 依 `used_search` 決定要不要附加詢問存檔的文字並進入 `pending_kb_save` 流程。**2026-07-31 補充**：`generate_with_search()` 內部固定使用 `gemini-2.5-flash`，與其他呼叫用的模型不同——因為 Google Search grounding 免費額度依模型世代分桶，詳見 [submodules-core SPEC.md](../submodules-core/SPEC.md) ADR-7

**狀態**：superseded by ADR-5（2026-07-31，`gemini-2.5-flash` 對新產生的 Gemini API Key 直接 404「no longer available to new users」，Gemini 2.5 世代已對新專案關閉存取，grounding 整條路走不通，非額度或選型問題）

### ADR-2：存檔確認流程沿用 `ConversationStateStore`，用 `flow: "pending_kb_save"` 標記

**背景**：FR-4 需要在「查到網路答案」之後，等使用者下一則訊息確認要不要存檔，這是又一種新的多輪對話流程。

**決策**：比照 [feature-toggles SPEC.md](../feature-toggles/SPEC.md) ADR-1 的作法，用同一個 `ConversationStateStore`，新增 `flow: "pending_kb_save"`，狀態內容為 `{"flow": "pending_kb_save", "content": <查到的答案文字>, "user_id": <要存進哪個使用者的 custom 知識庫>}`

**理由**：與既有兩種 flow（`set_invite_codes`、`toggle`/`set_toggle`）一致的機制，路由層只需要多一個 `elif` 分支，不需要新增額外的狀態儲存機制

**狀態**：superseded by ADR-5（2026-07-31，flow 改名為 `pending_user_knowledge`，且不再需要 yes/no 確認）

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

### ADR-4：`/function` 改版（Step 1.3a）——總覽獨立小型 LLM 呼叫，細節追問併入既有聊天核心

**背景**：Step 1.1 的 `/function` 是一次性完整清單（`templates.build_function_list_text()`），不符合 FR-56 的「總覽＋按需深入＋情境範例＋人格化語氣」新規格。核心問題是「使用者追問某功能細節時」要怎麼接。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：併入既有聊天核心 —— `/function` 總覽走獨立小型 LLM 呼叫（不建對話狀態）；細節追問不做新指令，直接讓使用者用自然語言問，沿用 Step 1.3 聊天核心，把功能手冊（含範例）併入 `chat._build_prompt()` 的 context，LLM 自行判斷要不要回答與是否附範例 | 零新增狀態機、複用既有 context 組裝與人格化邏輯、複雜度最低，符合本專案「不過度工程」原則 | 「有沒有精準判斷出使用者在問功能細節」依賴模型自己的判斷，不是規則式 100% 可控 |
| B：獨立狀態機 —— 仿 `/my_toggles`／`/set_toggle` 的 flow 設計：`/function` 進總覽 → 使用者輸入功能名稱/編號進細節 → 固定指令退出 | 回覆內容更可控（不會被 LLM 誤判成一般聊天） | 多一套新流程與測試，工程量較大；且「功能細節說明」本質上就是問答，用固定選單反而不如自然語言直覺 |

**決策**：採方案 A（2026-07-31 Robin 確認）

**理由**：與 ADR-1／ADR-3 一致的判斷基準——本專案是個人/家用規模的 Bot，方案 B 的可控性提升有限（使用者選單操作本身也可能誤觸），卻要多付一整套新狀態機的實作與維護成本；方案 A 直接利用 Step 1.3 已經做好的「知識庫 context 組裝 + LLM 人格化改寫」機制，`/function` 總覽獨立呼叫是因為總覽在使用者還沒問任何問題時就要主動觸發，無法等一般聊天核心來處理，其餘（細節追問）完全復用既有能力

**後果**：
- `templates.py` 新增 `build_function_overview_raw_text()`（總覽用，不含範例）與 `build_function_manual_text()`（完整手冊，含 FR-56d～FR-56h 範例），取代原本的 `build_function_list_text()`；`FEATURE_LIST` 每筆功能新增 `examples` 欄位（尚無範例的功能留空清單）
- `knowledge.py` 新增 `get_persona_text(db)`，從 `build_context()` 拆出，供 `handle_function` 不需要 `user_id` 就能取得人格背景
- `commands.handle_function(db, llm_client)` 改為需要 `db`／`llm_client` 兩個參數，回傳值不再是純文字模板，而是 LLM 呼叫結果
- `chat._build_prompt()` 固定附上功能手冊區塊，並加入「僅使用者明確詢問才回答、需附範例、不主動提起」的規則說明

**狀態**：accepted

### ADR-5：移除 Google Search grounding，改為誠實回報不知道＋使用者自行提供答案（supersede ADR-1、ADR-2）

**背景**：2026-07-31 Robin 排查一把新產生的 `GEMINI_API_BOT_KEY`（新 Google Cloud 專案）時，發現 `generate_with_search()` 固定使用的 `gemini-2.5-flash` 直接回傳 404「This model ... is no longer available to new users」——用 curl 直接打 `generateContent`（不掛任何工具）也一樣 404，證實不是搜尋工具的問題，而是 Gemini 2.5 這整個世代已經對新專案關閉存取（見 [submodules-core SPEC.md](../submodules-core/SPEC.md) ADR-8）。Gemini 3 世代雖然可用，但免費層 grounding 額度是 0（見 submodules-core SPEC.md ADR-7 背景），要用就得開通計費。Robin 決定不追加成本，直接放棄 grounding 功能。

**決策**：完全移除 `generate_with_search()` 與相關 grounding 邏輯（2026-07-31 Robin「請把所有會用到上網查詢的部分移除」指示）。`chat.py` 改呼叫 `generate_text()`（不掛工具）；prompt 明確告知模型自己沒有查詢網路的能力，資料不足時必須誠實回報不知道，並在回覆最後加上系統標記 `【NOT_FOUND】`；`chat.py` 偵測到標記後，去除標記、附加「你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！」，並把 `pending_kb_save` 狀態改名為 `pending_user_knowledge`（不再有 `content` 欄位，因為答案還沒有——是下一則使用者輸入才會有）。使用者下一則輸入直接視為要存入的內容，不需要 yes/no 確認（原本 ADR-2 的確認詞機制拿掉，因為使用者已經被明確告知「下一則輸入會被記錄」，不會有誤觸風險）。

**替代方案**：
- 方案 A：换回舊專案的 Gemini API Key 專門處理 grounding——技術上可行、免費，但 Robin 判斷「再試下去只是在浪費時間」，且舊 Key 的存續狀態不確定，選擇直接放棄功能，已否決
- 方案 B：開通計費帳戶，讓 Gemini 3 世代也能用 grounding——涉及 Robin 個人帳務決定，Robin 明確表示不要繼續在這個問題上花時間，已否決

**理由**：Robin 直接指示移除，且盤點後這個功能只影響「一般聊天問到即時性資訊」這個情境，其餘主力功能（待辦/記帳/體態/心情小記等）都不依賴 grounding，功能倒退範圍可控；`robinson SPEC.md` 附錄 A 使用規範文案（「若需要即時上網查詢的資訊，請先自行搜尋」）原本就已經預告了這個使用限制，行為與既有文案一致。

**後果**：
- `submodules/llm/client.py` 刪除 `generate_with_search()`、`_SEARCH_MODEL`、`_used_search()`
- `src/bot/chat.py`：`handle_chat_message()` 改呼叫 `generate_text()`；新增 `handle_pending_user_knowledge_step()` 取代 `handle_pending_kb_save_step()`
- `src/bot/router.py`：`_dispatch_active_flow` 的 `pending_kb_save` 分支改為 `pending_user_knowledge`
- 相關測試全數更新（`test_client.py`／`test_chat.py`／`test_router.py`）

**狀態**：accepted

## 實作計畫

- [x] Step 1（2026-07-31 由 ADR-5 取代）：`submodules/llm/client.py` 曾新增 `generate_with_search(prompt) -> tuple[str, bool]`，現已刪除
- [x] Step 2：`src/bot/knowledge.py` —— `build_context(db, user_id)` 組出四類知識庫內容；`save_custom_knowledge(db, user_id, content)` 寫入 `custom` 知識庫
- [x] Step 3（2026-07-31 依 ADR-5 修正）：`src/bot/chat.py` —— `handle_chat_message(db, llm_client, state_store, telegram_user_id, user_id, text)`：組 prompt、呼叫 `generate_text()`、寫對話紀錄、判斷回覆是否含 `【NOT_FOUND】` 標記以決定是否進入 `pending_user_knowledge`
- [x] Step 4（2026-07-31 依 ADR-5 修正）：`chat.py` 新增 `handle_pending_user_knowledge_step()`（取代 `handle_pending_kb_save_step()`）處理使用者主動提供答案的下一則訊息，直接存入知識庫
- [x] Step 5（2026-07-31 依 ADR-5 修正）：`router.py` 整合：`flow == "pending_user_knowledge"` 的分派、一般訊息 fallback 改呼叫 `chat.handle_chat_message`
- [x] Step 6：更新 `src/schema/api_schema.md` 標記對話核心路由狀態
- [x] Step 7：`conversation_summaries` migration（Robin 已核准，見 ADR-3），`0007_create_conversation_summaries_table.sql`
- [x] Step 8：`src/bot/memory.py` —— `get_or_create_summary_row()`／`get_summary()`／`maybe_update_summary()`（backlog 計算、門檻觸發、吞例外）
- [x] Step 9：`chat.py` 新增 `text_llm_client` 參數，改為分別呼叫 `knowledge.build_context()` 取得知識庫/短記憶、`memory.get_summary()` 取得長記憶，`_build_prompt()` 加入長記憶區塊；回覆算完並寫入對話紀錄後才呼叫 `memory.maybe_update_summary()`（實際採用「chat.py 各自呼叫兩個模組」而非「揉進 knowledge.build_context() 的回傳值」，讓 `knowledge.py`／`memory.py` 職責分離，`knowledge.py` 本體與既有測試不受影響）
- [x] Step 10：`router.py` 新增 `text_llm_client` 參數並透傳；`webhook.py` 額外注入 `LLMClient(GEMINI_API_TEXT_KEY)`
- [x] Step 11（Step 1.3a／ADR-4）：`templates.py` 新增 `build_function_overview_raw_text()`／`build_function_manual_text()`，`FEATURE_LIST` 補上 `examples` 欄位
- [x] Step 12：`knowledge.py` 新增 `get_persona_text(db)`；`commands.handle_function(db, llm_client)` 改為 LLM 人格化總覽
- [x] Step 13：`chat._build_prompt()` 加入功能手冊區塊與「按需回答＋附範例＋不主動提起」規則
- [x] Step 14：`router.py` 的 `_FUNCTION_TRIGGERS` 分支改呼叫 `commands.handle_function(db, llm_client)`

## 測試策略

### Unit Tests
- [x]（2026-07-31 移除，見 ADR-5）~~`llm.client.LLMClient.generate_with_search()`~~
- [x] `knowledge.build_context()`：組出正確的四類內容；只查自己的 `custom`／`conversation_logs`（資安隔離）；對話紀錄只取最近 10 則
- [x] `knowledge.save_custom_knowledge()`：正確寫入 `category='custom'`、`user_id`
- [x] `chat.handle_chat_message()`（2026-07-31 依 ADR-5 修正）：一般問答（不觸發存檔流程）／回覆含 `【NOT_FOUND】` 標記時去除標記、附加自行查詢建議並設定 `pending_user_knowledge` 狀態／每次呼叫後對話紀錄各寫入使用者訊息與回覆各一筆
- [x] `pending_user_knowledge` 流程（2026-07-31 依 ADR-5 修正）：使用者下一則輸入直接存入知識庫，不需要 yes/no 確認
- [x] `memory.maybe_update_summary()`：backlog 未達門檻不觸發／達門檻時呼叫 `GEMINI_API_TEXT_KEY` 並正確覆蓋摘要、推進 `summarized_up_to_log_id`／新使用者自動建立空白摘要列（FR-8）／只考慮自己的對話、排除軟刪除、不重複處理已摘要過的部分／呼叫失敗吞例外不往外拋
- [x] `chat.handle_chat_message()` 整合長記憶：prompt 包含摘要內容；backlog 達門檻時觸發摘要更新

### Integration Tests
- [x] `router.py`：一般聊天訊息完整跑過 `chat.handle_chat_message` 並取得回覆；`pending_user_knowledge` 狀態下一則訊息正確分派（2026-07-31 依 ADR-5 更名自 `pending_kb_save`）
- [x] 連續對話累積超過門檻則數後，自動觸發一次摘要更新（`test_handle_chat_message_triggers_memory_update_after_reply`）

### E2E Tests
- [x]（2026-07-31 依 ADR-5 修正）完整流程：使用者問一個知識庫沒有的問題 → 模型誠實回報不知道（`【NOT_FOUND】`標記）→ 附加自行查詢建議 → 使用者提供答案 → 直接寫入 `custom` 知識庫
- [x] Step 1.3a：`/function` 觸發後回傳 LLM 人格化總覽；使用者用自然語言追問特定功能時，落入一般聊天核心且 prompt 內含該功能的情境範例

**測試結果**：一般聊天核心（ADR-1/ADR-2，2026-07-31 由 ADR-5 取代）新增 26 個測試，長記憶（ADR-3）再新增 13 個（`test_memory.py` 11 個、`test_chat.py`／`test_webhook.py` 長記憶整合部分共 2 個），Step 1.3a（ADR-4）再新增 9 個測試（分散在 `test_templates.py`／`test_commands.py`／`test_knowledge.py`／`test_chat.py`／`test_router.py`），ADR-5（移除 grounding）調整既有測試、全專案總計 174 個測試全過、`src/bot/` 與 `submodules/llm/` 覆蓋率皆維持 100%（`pytest tests/ --cov=src/bot --cov=submodules/llm`）。

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
|------|--------|------|----------|
| （2026-07-31 已移除 grounding，此風險隨 ADR-1 一併 superseded）~~模型判斷「要不要查網路」不夠精準~~ | — | — | 見 ADR-5：直接移除 grounding，不再需要判斷是否查網路 |
| 移除 grounding 後，使用者問即時性資訊會被回覆不知道，可能感覺功能倒退（ADR-5 已知取捨） | 低 | 中 | Robin 明確指示移除且盤點過影響範圍可控；`robinson SPEC.md` 附錄 A 使用規範已預告此限制，且提供「自行查詢後提供答案存檔」的替代路徑 |
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
| 2026-07-31 | **Phase 1 Step 1.3a 完成**：`/function` 改版為「總覽 + 按需深入」（FR-9／FR-9a／FR-9b），新增 ADR-4（總覽用獨立小型 LLM 呼叫，細節追問併入既有聊天核心，Robin 確認）；`templates.py` 新增 `build_function_overview_raw_text()`／`build_function_manual_text()`（`FEATURE_LIST` 補 `examples` 欄位，收錄 FR-56d～FR-56h 情境範例）；`knowledge.py` 新增 `get_persona_text()`；`commands.handle_function()` 改為需要 `db`／`llm_client`；`chat._build_prompt()` 固定附上功能手冊；全專案 126 個測試全過、覆蓋率 100% | Claude（依 Robin「繼續開發吧」指示） |
| 2026-07-31 | **移除 Google Search grounding**：Robin 排查一把新產生的 `GEMINI_API_BOT_KEY` 時發現 `gemini-2.5-flash` 對新專案回傳 404「no longer available to new users」，Gemini 2.5 世代已對新專案關閉存取（見 submodules-core SPEC.md ADR-8），Robin 指示「把所有會用到上網查詢的部分移除，若真的不知道答案就回不知道，並建議使用者自行查詢後提供答案存檔」；新增 ADR-5（supersede ADR-1／ADR-2）：`client.py` 刪除 `generate_with_search()`；`chat.py` 改呼叫 `generate_text()`，prompt 加入 `【NOT_FOUND】` 標記機制，新增 `handle_pending_user_knowledge_step()` 取代 `handle_pending_kb_save_step()`；`router.py` flow 更名為 `pending_user_knowledge`；全專案 174 個測試全過、覆蓋率 100% | Claude（依 Robin 指示） |
| 2026-07-31 | Robin 回報問「今天幾月幾號」時模型瞎掰了錯誤日期，還編造「剛好是我生日」這種知識庫沒有的內容；補充 FR-3(d)：`chat.py` 新增 `_now()`／`_current_date_text()`（`Asia/Taipei` 時區，伺服器本地算出，不需外部 API），prompt 加入真實日期區塊並加強「不可捏造具體事實」規則；全專案 176 個測試全過、覆蓋率 100% | Claude（依 Robin 回報指示） |
