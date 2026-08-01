---
title: Gemini 對話核心 — 知識庫問答、資安隔離、人格化語氣
slug: chat-core
status: implemented
created: 2026-07-30
updated: 2026-08-01
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
- [x] FR-3：System Prompt 規則 —— 明確指示模型：(a) 用 Robinson 的人格語氣回答，不要照本宣科；(b) 只根據提供的知識庫內容回答，明確告知模型自己沒有查詢網路的能力；(c) 知識庫沒有答案時必須誠實回報不知道（2026-07-31 修正，見 ADR-5）；(d)（2026-07-31 追加）真實日期由伺服器本地算出（`Asia/Taipei` 時區）直接塞進 prompt，日期／星期問題一律以此為準，不可自行推算或憑印象亂猜；除 prompt 內明確提供的資料外絕對不能捏造具體事實（例如生日、事件細節、數字）——起因是 Robin 回報問「今天幾月幾號」時模型瞎掰錯誤日期並編造「剛好是我生日」，LLM 本身沒有即時時鐘，移除 grounding 後更無管道查證，日期屬於伺服器本地就能算出的資訊，不需要任何外部 API；(e)（2026-07-31 追加，2026-08-01 追加修正）代名詞（他／她／牠／它）追問一律理解成使用者「最近一次」明確點名問過的那個人，即使中間插入了其他不相關的問題也要以那之後最新一次明確點名的對象為準，不可跳回更早之前提過的人；不能因為上一輪回答內容裡順便提到其他人名就誤判指涉對象；使用者明確糾正時要針對正確對象重新回答原本的問題，不能只重複貼舊答案；只要沒有百分之百把握指涉對象就必須先反問使用者，不能用可能錯誤的假設硬答；年齡等數值計算一律用「現在的日期」與知識庫裡的正確生日相減——起因是 Robin 回報問「小布丁是誰」後追問「他大概幾歲」，Robinson 誤把「他」理解成上一輪回答裡順便提到的照顧者（爺爺）並算出爺爺的年齡，使用者糾正「我說小布丁啦」後又只是重複貼一模一樣的舊答案，沒有真的回答年齡；**2026-08-01 追加修正起因**：Robin 回報連續問「小雯有養動物嗎」→（中間插入一則不相關問題）→「范麗芳是誰」→「她老公是誰」，Robinson 誤把「她」理解成更早之前提過的小雯，而不是最近一次才明確點名問過的范麗芳，原規則未明確規範「該用哪一輪的主體」也未強制「沒把握就要反問」，故補強上述兩點；(f)（2026-08-01 追加，見 ADR-7）回答務必精簡直接——單純的事實性問題（幾歲、什麼顏色、是誰等）只需給出核心答案本身，不要主動附加推算過程、查到的來源或不必要的背景說明／形容詞堆疊；只有使用者明確要求解釋原因、過程，或問題本身就需要完整說明時才展開細講——起因是 Robin 回報問「Robin 今年幾歲」時 Robinson 複述了整段生日與計算過程，問「牛牛是什麼顏色」時附加了一整段外觀描述，其實只需要回「快要滿 29 歲」「黑色」就好；(g)（2026-08-01 追加，誠實性規則）除了 FR-4 的 `pending_user_knowledge` `【SAVE_ANSWER】` 流程以外，模型沒有任何其他管道能真的把新資訊寫進 `knowledge_base`；即使使用者直接要求「記住」「新增到知識庫」「幫我存起來」，也絕對不能宣稱已經記錄、已經新增、已經儲存，必須誠實告知目前無法主動寫入、請轉告 Robin 手動新增——起因是 Robin 回報請 Robinson 把家庭成員背景新增到知識庫，Robinson 回覆已經新增，但實際上完全沒有對應的寫入路徑，屬於謊報成功；也順帶修正打字誤植反問機制（ADR-7）的一個副作用：反問句必須帶出【Robinson 人格背景】／【Robin 與家人背景】／【客製知識庫】裡「真實存在」的相似人名，不可以套用其他不相關的人名，資料裡根本沒有相似人名時要直接走 FR-4 的「不知道」規則——起因是 Robin 回報問「阿牛是誰」（知識庫當時沒有這筆資料）卻被反問「你是說『吳凱吉』嗎？」，兩者毫無相似之處，原因是舊版 prompt 範例把一個真實家人姓名寫死在指示文字裡，模型會照抄範例而非真的比對知識庫內容
- [x] FR-4：查無答案時的處理（對應 FR-12，2026-07-31 修正，見 ADR-5，supersede 原本的 Google Search grounding 設計）—— 單次 API 呼叫（`generate_text`，不掛任何工具）；prompt 指示模型在資料不足以回答時，於回覆最後加上固定標記 `【NOT_FOUND】`；`chat.py` 偵測到標記後，去除標記並附加「你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！」，同時進入等待使用者提供答案的狀態（`flow: pending_user_knowledge`，含 `original_question` 欄位）。**2026-07-31 再修正，見 ADR-6**：下一則訊息不再無條件視為答案存檔——同一次 LLM 呼叫會先判斷這則新訊息是「提供答案」（輸出 `【SAVE_ANSWER】`，才寫入 `knowledge_base`，`category='custom'`，`user_id=`該使用者）、「拒絕記錄」（輸出 `【DECLINE_SAVE】`，不寫入）、還是「其實是問了個無關的新問題」（不輸出任何標記，照一般規則正常回答，並清除 pending 狀態）
- [x] FR-5：對話紀錄 —— 只有真正進入一般聊天核心的訊息才記錄：使用者原始輸入寫一筆（`role='user'`），Robinson 的回覆寫一筆（`role='assistant'`）；指令觸發（`/rule`、`/my_toggles` 等）與確認存檔流程本身的輸入/輸出不計入對話紀錄
- [x] FR-6：長記憶查詢 —— Context 組裝時額外帶上該使用者的 `conversation_summaries.summary`（查無資料視為空字串），與短記憶/知識庫一起放進 prompt
- [x] FR-7：長記憶更新（滾動式摘要，對應 ADR-3）—— 每次聊天核心處理完一輪對話後，計算「比短記憶更早、且 `id` 大於 `summarized_up_to_log_id` 」的 backlog 對話則數；backlog ≥ 10 則時，把 backlog 內容連同既有摘要一起丟給 `GEMINI_API_TEXT_KEY`（長文生成用途，見 ADR-12），產出新摘要覆蓋回 `conversation_summaries.summary`，並把 `summarized_up_to_log_id` 推進到 backlog 最新一筆的 `id`；backlog 未達門檻則不觸發，維持原摘要不變
- [x] FR-8：新使用者第一次進入聊天核心時，若 `conversation_summaries` 尚無對應資料列，自動建立一筆空摘要（`summary=''`、`summarized_up_to_log_id=0`），不需要額外走 Owner 審核流程（資料本身沒有預設內容，純粹是佔位）
- [x] FR-9：`/function` 改版（Step 1.3a，對應 robinson SPEC.md FR-56、FR-56a～FR-56c，見 ADR-4）—— 「總覽」與「細節追問」兩階段：
  - [x] FR-9a：總覽 —— 觸發 `/function` 或「我要看所有功能」時，`commands.handle_function(db, llm_client)` 組 prompt（Robinson 人格背景 + `templates.build_function_overview_raw_text()` 原始清單）呼叫一次 LLM，回傳人格化改寫過的功能總覽（僅名稱＋一句話簡述＋權限標記，不展開細節或範例）
  - [x] FR-9b：細節追問 —— 使用者用自然語言追問特定功能（例如「記帳功能可以做什麼？」）時，不走 `/function` 路由，直接落入一般聊天核心；`chat._build_prompt()` 固定附上 `templates.build_function_manual_text()`（完整功能手冊，含 FR-56d～FR-56h 情境範例），並指示 LLM 只有使用者明確詢問時才依此回答且需附範例，一般聊天不主動提起
- [x] FR-10（2026-08-01 新增，2026-08-01 追加修正改為先確認）：`/clean-all-dialog` —— 使用者輸入「我想要刪除所有對話紀錄」或 `/clean-all-dialog` 時，`commands.handle_clean_all_dialog(db, user_id)` 只清除該使用者自己的「對話」：`conversation_logs` 軟刪除（`deleted_at` 設為現在時間，比照既有慣例）＋ `conversation_summaries` 重置為空白摘要（`summary=''`、`summarized_up_to_log_id=0`）；**刻意不動 `knowledge_base`**——這是與規劃中、尚未實作的「刪除特定主題相關紀錄」（`/clean-target-dialog`，使用者說「我想刪除有關...的紀錄」時觸發，會連同該主題的知識庫內容一起清除）明確區隔開的不同指令，`/clean-all-dialog` 只處理對話記憶，不處理知識庫。**追加修正起因**：Robin 回報原本觸發詞一送出就直接執行刪除，沒有給使用者反悔機會，違反 FR-16「任何涉及寫入/修改資料庫的操作前一律先與使用者確認」；改為 `commands.start_clean_all_dialog_confirm()` 先查出目前 `conversation_logs` 未刪除筆數告知使用者並反問「確定要清除嗎？」，進入 `pending_clean_all_dialog_confirm` 狀態，下一則訊息由 `commands.handle_clean_all_dialog_confirm_step()` 以單次 LLM 呼叫判斷使用者是「確定」（`CONFIRM`，才呼叫 `handle_clean_all_dialog()` 真正執行）還是「取消」（`CANCEL`，任何無法判斷為確定的回覆一律視為取消，保守優先，不誤刪）

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

**狀態**：`pending_user_knowledge` 的「下一則輸入無條件視為答案」機制部分 superseded by ADR-6（2026-07-31，同一天 Robin 實測就回報這個假設太天真：換問題、拒絕記錄都會被誤存），其餘（移除 grounding、誠實回報不知道）維持 accepted

### ADR-6：`pending_user_knowledge` 改由同一次 LLM 呼叫判斷「答案／拒絕／新問題」，不再無條件存檔（部分 supersede ADR-5）

**背景**：ADR-5 上線當天 Robin 實測回報三個問題，全部源自同一個天真假設——「使用者下一則輸入＝要存的答案」：
1. 問「陳東東是誰」被回不知道後，換問一個完全無關的新問題「吳凱吉是誰」，結果被當成「陳東東」的答案存進知識庫，新問題本身也沒被回答，直接被吞掉
2. 問「吳鎧吉是誰」（同音字打錯，知識庫其實有「吳凱吉」）被誤判不知道；換句話說 prompt 對「使用者打字可能有誤植」這件事完全沒有容錯
3. 使用者明確回「不用紀錄啦」表示拒絕，還是被存進知識庫；另外還發現模型會把之前已經回覆過、寫進 `conversation_logs` 的建議句從對話紀錄裡複誦出來，跟程式碼另外補的同一句建議疊在一起變成重複兩次

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：關鍵字比對——維護一組「拒絕詞」（不用／算了／不需要）比對使用者輸入，符合就不存，其餘一律當答案存 | 零額外 API 呼叫、實作單純 | 只解決拒絕詞問題（問題3），完全沒解決「換了新問題」（問題1）這種無法用關鍵字窮舉的情況；本質上只是把天真假設的破口從「全部」縮小到「大部分」，治標不治本 |
| B：同一次 LLM 呼叫裡讓模型先判斷這則新訊息是「提供答案」「拒絕記錄」還是「問了個無關的新問題」，三種情況分別輸出對應標記（`【SAVE_ANSWER】`／`【DECLINE_SAVE】`／無標記=正常回答），Python 依標記決定要不要存檔 | 不额外多打一次 API（跟原本判斷「知不知道」共用同一次呼叫）、能處理關鍵字窮舉不了的「換問題」情境，泛化能力最好 | 判斷準確度依賴模型的語言理解能力，不是規則式 100% 可控（但這跟 ADR-1 一貫的取捨邏輯一致） |

**決策**：採方案 B。同時，順手把 ADR-5 的 prompt 再補兩條規則：(a) 遇到跟知識庫人名高度相似（同音字/形似字，例如「鎧」vs「凱」）的名字，先假設是打字誤植、用最相近的知識庫人名回答，不要直接判定不知道；(b) 附加建議句之前，先把回覆文字裡「可能已經存在」的同一句建議去掉，再統一補一份，避免重複兩次。

**理由**：方案 A 治標不治本——本次三個問題裡最嚴重的「換問題被吞掉」根本不是關鍵字能解的，因為使用者換的新問題內容無法窮舉；方案 B 沒有增加 API 呼叫次數（原本這一步就是要呼叫一次 LLM 判斷「知不知道」，現在只是多帶一段情境、多判斷一件事），符合 ADR-1 一貫「單次呼叫換取簡單實作」的原則，且泛化能力明顯更好。

**後果**：
- `src/bot/chat.py`：`handle_chat_message()` 新增 `pending_question: str | None = None` 參數；不是 None 時 `_build_prompt()` 會多帶一段「特別狀況」情境，並依回覆是否含 `【SAVE_ANSWER】`／`【DECLINE_SAVE】`／`【NOT_FOUND】` 三種標記分流；三種都沒有的話代表模型判斷是無關新問題，照一般規則回答並清除舊的 pending 狀態，不再殘留卡住下一輪
- 刪除 `handle_pending_user_knowledge_step()`——其功能完全併入 `handle_chat_message()`，不再是獨立的「無條件存檔」函式
- `pending_user_knowledge` 狀態新增 `original_question` 欄位（記錄使用者原本問的問題，供下一輪的判斷 prompt 使用）
- `src/bot/router.py`：`_dispatch_active_flow` 簽章改吃整包 `state` dict（取代原本只吃 `flow` 字串），並新增 `llm_client`／`text_llm_client` 參數，`pending_user_knowledge` 分支改呼叫 `chat.handle_chat_message()` 而非已刪除的舊函式
- 相關測試全數更新（`test_chat.py`／`test_router.py`）

**狀態**：accepted

### ADR-7：打字誤植改為「先反問確認，等使用者回覆才回答」，不再直接假設是同一人（部分 supersede ADR-6 的容錯規則）

**背景**：ADR-6 為同音字/形似字打字誤植（如「鎧」vs「凱」）加了容錯規則，但當時的作法是「假設是打字誤植、直接用最相近的知識庫人名回答」。2026-08-01 Robin 實測後認為這樣太冒進——萬一猜錯人，會在使用者沒發現的情況下把錯誤資訊講得煞有其事，不如先反問一句更保險。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：維持 ADR-6 做法，直接假設並回答，回覆末尾可選擇性附上「你是說『吳凱吉』嗎？」的確認句 | 少一輪來回，使用者體驗較快 | 假設錯了會直接輸出錯誤資訊，且使用者可能沒注意到附帶的確認句，誤以為是在講別人 |
| B：先反問確認，等使用者這一則回覆確認或否認後，才真正回答原本的問題 | 不會在猜錯的情況下講出錯誤資訊，符合 Robin 傾向保守的態度 | 多一輪來回；需要新增一個 pending 狀態與對應的 router／chat 分支，複雜度略增 |

**決策**：採方案 B（2026-08-01 Robin「先確認再回答比較好喔」指示）

**理由**：與 ADR-6 一貫的「不確定就不要自作主張」精神一致（例如代名詞指涉不確定時要反問，FR-3e）；打錯字猜錯人的代價（講錯資訊給使用者）比多問一句的代價（多一輪對話）更高，值得用一輪來回換取正確性。

**後果**：
- `src/bot/chat.py`：新增 `_CONFIRM_NAME_MARKER = "【CONFIRM_NAME】"`；`handle_chat_message()` 新增 `confirming_question: str | None = None` 參數；prompt 規則從「假設打字誤植直接回答」改為「先反問確認是不是知識庫裡最相近的那個人，並在回覆最後加上 `【CONFIRM_NAME】` 標記」；偵測到標記時，去除標記後回覆反問句，並把狀態設為 `{"flow": "pending_name_confirm", "target_user_id": <int>, "original_question": <str>}`
- `_build_prompt()` 新增 `confirming_question` 對應的「特別狀況」情境區塊，交由同一次 LLM 呼叫判斷使用者這則回覆是「確認／講出更明確的名字」（針對原問題完整回答，不再輸出任何標記）還是「否認／問了別的事」（當成全新一般訊息正常回答，不假設在回答上一題）——沿用 ADR-6 已建立的「單次呼叫＋標記分流」架構，不另外多打一次 API
- `src/bot/router.py`：`_dispatch_active_flow()` 新增 `flow == "pending_name_confirm"` 分支，呼叫 `chat.handle_chat_message()` 並帶入 `confirming_question=state.get("original_question")`
- 相關測試更新（`test_chat.py`／`test_router.py`）

**狀態**：accepted（ADR-6 的「直接假設並回答」機制部分 superseded；ADR-6 其餘部分——同一次呼叫判斷答案/拒絕/新問題、建議句去重——維持 accepted）

**2026-08-01 追加修正**：Robin 回報問「阿牛是誰」（知識庫當時沒有這筆資料）卻被反問「你是說『吳凱吉』嗎？」，兩者毫無相似之處。原因是上方「後果」提到的 prompt 規則裡，反問範例寫死了一個真實家人姓名「吳凱吉」，模型會照抄這個範例而不是真的去比對知識庫內容判斷相似度。修正 `chat._build_prompt()`：反問句必須帶出資料中「真實存在且真的高度相似」的人名，不可以套用其他不相關、不相似的名字；且明確規定知識庫裡根本沒有相似人名時要直接依照 FR-4 的「不知道」規則回答，不可以誤觸發這個反問機制。同時補上 FR-3(g) 誠實性規則（見上方 FR-3）。

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
- [x] Step 15（2026-08-01，ADR-7）：`chat.py` 新增 `_CONFIRM_NAME_MARKER`／`confirming_question` 參數，prompt 打字誤植規則改為先反問；`router.py` 新增 `pending_name_confirm` 分支
- [x] Step 16（2026-08-01，FR-3f）：`chat._build_prompt()` 加入精簡回答規則
- [x] Step 17（2026-08-01，FR-10）：新增 `commands.handle_clean_all_dialog(db, user_id)`；`router.py` 新增 `_CLEAN_ALL_DIALOG_TRIGGERS` 分派；`templates.APPENDIX_A_TEXT` 補上第 4 點使用須知
- [x] Step 18（2026-08-01，FR-10 追加修正＋FR-3g）：`commands.py` 新增 `start_clean_all_dialog_confirm()`／`handle_clean_all_dialog_confirm_step()`，`/clean-all-dialog` 改為先反問確認再刪除；`router.py` 新增 `pending_clean_all_dialog_confirm` 分派；`chat._build_prompt()` 修正 CONFIRM_NAME 反問範例（不可套用不相關人名）並加入誠實性規則（不可謊報已寫入知識庫）；`src/migrations/0011_add_family_pets_to_family_knowledge.sql` 新增阿牛（牛牛）、龜龜兩筆家庭寵物背景

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
- [x]（2026-08-01，ADR-7）打字誤植觸發 `【CONFIRM_NAME】` 標記時設定 `pending_name_confirm` 狀態並去除標記；`router.py` 正確分派該 flow 並帶入 `confirming_question`；使用者確認／否認兩種情況分別正確處理
- [x]（2026-08-01，FR-10）`commands.handle_clean_all_dialog()`：軟刪除 `conversation_logs`、重置 `conversation_summaries`、不影響 `knowledge_base`；`router.py` 的 `/clean-all-dialog` 與「我想要刪除所有對話紀錄」皆能正確觸發
- [x]（2026-08-01，FR-10 追加修正）`commands.start_clean_all_dialog_confirm()`：正確回報目前未刪除的對話紀錄筆數並設定 `pending_clean_all_dialog_confirm` 狀態、不會真的刪除；`commands.handle_clean_all_dialog_confirm_step()`：LLM 判定 `CONFIRM` 才真的執行刪除、`CANCEL`（或任何非 `CONFIRM` 回覆）保留原資料；`router.py` 正確分派該 flow
- [x]（2026-08-01，FR-3g／CONFIRM_NAME 修正）prompt 誠實性規則存在（不可謊報已寫入知識庫）；CONFIRM_NAME 反問規則要求帶出資料中真實存在的相似人名、且知識庫沒有相似人名時要走「不知道」規則，不誤觸發反問

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
| `pending_name_confirm` 判斷「使用者是否確認」依賴模型語言理解，不是規則式 100% 可控（ADR-7 已知取捨） | 低 | 低 | 與 ADR-6 一貫的取捨邏輯一致；猜錯的代價（誤判成否認、退回一般聊天重新回答一次）遠低於「假設打字誤植答錯人」的代價 |
| `/clean-all-dialog` 是不可逆操作（軟刪除，但一般聊天流程不提供復原入口） | 低 | 低 | 觸發詞明確（需使用者主動輸入完整句子或指令），不會被模糊語句誤觸；`deleted_at` 軟刪除保留了資料庫層級復原的可能性，只是目前沒有對外的復原指令；**2026-08-01 追加緩解**：已改為先反問確認、告知目前筆數，才真正執行，進一步降低誤觸風險 |
| 目前沒有任何「使用者主動要求，就把資訊寫進知識庫」的機制（唯一寫入路徑是 `pending_user_knowledge` 的被動流程），使用者可能誤以為講一聲「記住」就會生效 | 中 | 中 | 已修正 prompt 誠實性規則，Robinson 不會再謊稱已經記錄；但功能本身仍缺，屬於已知缺口，待 Robin 決定是否要開發「主動寫入知識庫」功能（新 Step，範圍待定：寫入 `custom` 還是 `general_family`、是否需要確認流程） |

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
| 2026-07-31 | Robin 回報問「小布丁是誰」後追問「他大概幾歲」，Robinson 誤把「他」理解成上一輪回答裡順便提到的照顧者（爺爺）並算出爺爺的年齡，糾正「我說小布丁啦」後又只是重複貼舊答案；補充 FR-3(e)：prompt 加入代名詞指涉規則（不要因為上一輪回答順便提到其他人名就誤判、使用者糾正要重新回答原問題、不確定就反問）與年齡計算規則；全專案 177 個測試全過、覆蓋率 100% | Claude（依 Robin 回報指示） |
| 2026-07-31 | Robin 回報 `pending_user_knowledge` 三個問題：(1) 問「陳東東是誰」被回不知道後換問完全無關的「吳凱吉是誰」，被誤存成陳東東的答案，新問題也沒被回答 (2) 「吳鎧吉」（同音字打錯，知識庫其實有「吳凱吉」）被誤判不知道，正常人一看就知道在找誰 (3) 明確說「不用紀錄啦」還是被存進知識庫，且建議句重複出現兩次；新增 ADR-6（部分 supersede ADR-5）：改由同一次 LLM 呼叫判斷「答案／拒絕／新問題」（`【SAVE_ANSWER】`／`【DECLINE_SAVE】`／無標記），不再無條件存檔；`handle_pending_user_knowledge_step()` 整併進 `handle_chat_message()`；prompt 加入同音字/形似字容錯規則；`router.py` `_dispatch_active_flow` 改吃整包 `state` 並新增 `llm_client`／`text_llm_client` 參數；全專案 184 個測試全過、覆蓋率 100% | Claude（依 Robin 回報指示） |
| 2026-08-01 | Robin 測試後回報三項調整：(1) ADR-6 的打字誤植容錯「直接假設並回答」太冒進，改為新增 ADR-7：先反問確認（`【CONFIRM_NAME】` 標記＋`pending_name_confirm` 狀態），等使用者這則回覆確認或否認後才真正回答 (2) 補充 FR-3(f)：回答太囉唆（問年齡附加完整計算過程、問顏色附加整段外觀描述），加入精簡回答規則，單純事實性問題只給核心答案 (3) 新增 FR-10：`/clean-all-dialog` 指令，清除使用者自己的 `conversation_logs`＋`conversation_summaries`（軟刪除/重置），刻意不動 `knowledge_base`，並與規劃中的 `/clean-target-dialog`（會連知識庫一起清）明確區隔；`templates.APPENDIX_A_TEXT` 補上第 4 點使用須知；全專案 192 個測試全過、覆蓋率 100% | Claude（依 Robin 回報指示） |
| 2026-08-01 | Robin 再回報代名詞指涉 bug：連續問「小雯有養動物嗎」→（中間插入一則不相關問題）→「范麗芳是誰」→「她老公是誰」，Robinson 誤把「她」理解成更早之前提過的小雯，而不是最近一次才明確點名問過的范麗芳；補強 FR-3(e)：明確規定代名詞一律以使用者「最近一次」明確點名的對象為準（即使中間插入其他問題也不可跳回更早之前的人），且只要沒有百分之百把握就必須先反問使用者，不能用可能錯誤的假設硬答 | Claude（依 Robin 回報指示） |
| 2026-08-01 | Robin 測試又回報四個問題：(1) `/clean-all-dialog` 沒有先確認就直接刪除，補強 FR-10：新增 `commands.start_clean_all_dialog_confirm()`／`handle_clean_all_dialog_confirm_step()`，先告知目前對話紀錄筆數並反問確認，使用者確認（LLM 判定 `CONFIRM`）後才真正執行，任何非確定回覆一律視為取消，保守優先；`router.py` 新增 `pending_clean_all_dialog_confirm` 分派 (2) Robin 請 Robinson 把家庭成員背景新增到知識庫，Robinson 謊稱已新增（實際上沒有對應寫入路徑，目前唯一真的會寫入的管道只有 `pending_user_knowledge` 的 `【SAVE_ANSWER】` 流程），新增 FR-3(g) 誠實性規則，禁止在沒有實際寫入的情況下宣稱已記錄／已新增／已儲存 (3) 新增 `src/migrations/0011_add_family_pets_to_family_knowledge.sql`，寫入阿牛（牛牛，Robin 家的狗）與龜龜（Robin 爸爸養的蘇卡達陸龜）兩筆寵物背景 (4) 問「阿牛是誰」（知識庫當時沒有這筆資料）被誤反問「你是說『吳凱吉』嗎？」，原因是 prompt 反問範例寫死了一個真實家人姓名，模型照抄範例而非真的比對知識庫，修正 CONFIRM_NAME 反問規則要求帶出資料中真實存在且高度相似的人名，沒有相似人名時要走「不知道」規則；全專案 201 個測試全過、覆蓋率 100% | Claude（依 Robin 回報指示） |
