# Gemini 對話核心 討論紀錄

## 2026-07-31 [標籤：AI] ADR-1：查無答案時採「單次 API 呼叫＋Google Search grounding」（superseded by ADR-5）

**狀態**：superseded by ADR-5（2026-07-31，`gemini-2.5-flash` 對新產生的 Gemini API Key 直接 404「no longer available to new users」，Gemini 2.5 世代已對新專案關閉存取，grounding 整條路走不通，非額度或選型問題）

**背景**：FR-12 要求「查不到答案才上網查」，需要一個機制判斷「知識庫是否足夠回答」。

**討論內容**：比較方案 A（單次呼叫，開啟 `google_search` 工具讓模型自行判斷要不要查，呼叫成本低但可控性依賴模型自我判斷）與方案 B（先只給知識庫呼叫一次，模型回傳約定字串才觸發第二次帶搜尋工具的呼叫，兩倍呼叫成本）。

**決策**：採方案 A（2026-07-31 Robin 確認）。

**理由**：兩方案都無法完全避免依賴模型自我判斷，方案 A 更符合 NFR-1（免費額度優先）與「不過度工程」原則。

**後果**：`submodules/llm/client.py` 新增 `generate_with_search()`，`gemini-2.5-flash` 固定用於 grounding（免費額度依模型世代分桶）。

## 2026-07-31 [標籤：AI] ADR-2：存檔確認流程沿用 `ConversationStateStore`（superseded by ADR-5）

**狀態**：superseded by ADR-5（2026-07-31，flow 改名為 `pending_user_knowledge`，且不再需要 yes/no 確認）

**背景**：FR-4 需要在「查到網路答案」之後，等使用者下一則訊息確認要不要存檔。

**決策**：比照 feature-toggles ADR-1 的作法，用同一個 `ConversationStateStore`，新增 `flow: "pending_kb_save"`。

**理由**：與既有兩種 flow 一致的機制，路由層只需要多一個 `elif` 分支。

## 2026-07-31 [標籤：AI] ADR-3：長記憶採「滾動式摘要」，而非全量塞入或向量搜尋

**狀態**：accepted

**背景**：Robin 指出短記憶只抓最近 10 則會忘記很久以前的對話，需要在「記得住重點」與「成本/複雜度可控」之間取捨。

**討論內容**：比較方案 A（滾動式摘要，成本有上限，但記的是濃縮重點非逐字原文）、方案 B（全部原文塞進 prompt，token 用量無上限成長，不可行）、方案 C（語意向量搜尋 RAG，需要 pgvector 與 embedding pipeline，對個人家用機器人規模是過度工程）。

**決策**：採方案 A（2026-07-31 Robin 確認）。

**理由**：方案 B 必然不可行，方案 C 對這個規模是過度工程，方案 A 用最小的新增複雜度換取「記得住重點」的核心需求。

**後果**：新增 `conversation_summaries` 表（`user_id` UNIQUE、`summary`、`summarized_up_to_log_id`）；新增 `src/bot/memory.py`；摘要更新失敗時 `try/except` 包住，只跳過本次摘要更新，不影響聊天回覆本身。

## 2026-07-31 [標籤：AI] ADR-4：`/function` 改版——總覽獨立小型 LLM 呼叫，細節追問併入既有聊天核心

**狀態**：accepted

**背景**：Step 1.1 的 `/function` 是一次性完整清單，不符合 FR-56「總覽＋按需深入＋情境範例＋人格化語氣」新規格，核心問題是使用者追問某功能細節時要怎麼接。

**討論內容**：比較方案 A（併入既有聊天核心，`/function` 總覽走獨立小型 LLM 呼叫，細節追問直接讓使用者用自然語言問，沿用聊天核心 context）與方案 B（獨立狀態機，仿 `/my_toggles` 的 flow 設計）。

**決策**：採方案 A（2026-07-31 Robin 確認）。

**理由**：方案 B 的可控性提升有限，卻要多付一整套新狀態機的實作與維護成本；方案 A 直接利用 Step 1.3 已經做好的 context 組裝與人格化改寫機制。

**後果**：`templates.py` 新增 `build_function_overview_raw_text()`／`build_function_manual_text()`；`knowledge.py` 新增 `get_persona_text()`；`chat._build_prompt()` 固定附上功能手冊區塊。

## 2026-07-31 [標籤：AI] ADR-5：移除 Google Search grounding，改為誠實回報不知道＋使用者自行提供答案（supersede ADR-1、ADR-2）

**狀態**：`pending_user_knowledge` 的「下一則輸入無條件視為答案」機制部分 superseded by ADR-6（2026-07-31）；其餘（移除 grounding、誠實回報不知道）維持 accepted

**背景**：2026-07-31 Robin 排查一把新產生的 `GEMINI_API_BOT_KEY` 時，發現 `generate_with_search()` 固定使用的 `gemini-2.5-flash` 直接回傳 404「no longer available to new users」，證實 Gemini 2.5 整個世代已對新專案關閉存取（見 submodules-core SPEC.md ADR-8）。Gemini 3 世代免費層 grounding 額度是 0，Robin 決定不追加成本，直接放棄 grounding 功能。

**決策**：完全移除 `generate_with_search()` 與相關 grounding 邏輯。`chat.py` 改呼叫 `generate_text()`；prompt 明確告知模型自己沒有查詢網路的能力，資料不足時必須誠實回報不知道，回覆最後加系統標記 `【NOT_FOUND】`；`chat.py` 偵測到標記後附加「你可以先自行上網查詢，查到後把答案打給我」，並把狀態改名為 `pending_user_knowledge`（不再需要 yes/no 確認）。

**替代方案**：換回舊專案的 Key 專門處理 grounding（已否決，舊 Key 存續狀態不確定）；開通計費帳戶讓 Gemini 3 世代也能用 grounding（已否決，涉及 Robin 個人帳務決定）。

**理由**：Robin 直接指示移除，且盤點後這個功能只影響「一般聊天問到即時性資訊」這個情境，其餘主力功能都不依賴 grounding。

**後果**：`submodules/llm/client.py` 刪除 `generate_with_search()`；`src/bot/chat.py` 新增 `handle_pending_user_knowledge_step()`；`router.py` 的 flow 改名。

## 2026-07-31 [標籤：AI] ADR-6：`pending_user_knowledge` 改由同一次 LLM 呼叫判斷「答案／拒絕／新問題」（部分 supersede ADR-5）

**狀態**：accepted（2026-08-02 追加修正三選一分流的措辭偏誤）

**背景**：ADR-5 上線當天 Robin 實測回報三個問題：①問「陳東東是誰」被回不知道後換問完全無關的新問題，被誤存成答案，新問題也沒被回答 ②同音字打錯字（「吳鎧吉」vs「吳凱吉」）被誤判不知道，完全沒有容錯 ③明確回「不用紀錄啦」表示拒絕，仍被存進知識庫，且建議句重複出現兩次。

**討論內容**：比較方案 A（維護一組「拒絕詞」關鍵字比對，零額外 API 呼叫但只解決拒絕詞問題，治標不治本）與方案 B（同一次 LLM 呼叫讓模型先判斷這則新訊息是「提供答案」「拒絕記錄」還是「問了個無關的新問題」，三種情況分別輸出對應標記）。

**決策**：採方案 B。同時補兩條規則：(a) 遇到跟知識庫人名高度相似（同音字/形似字）的名字，先假設是打字誤植；(b) 附加建議句之前先去除回覆文字裡可能已存在的同一句建議，避免重複。

**理由**：方案 A 治標不治本，方案 B 沒有增加 API 呼叫次數，泛化能力明顯更好。

**後果**：`chat.py` 新增 `pending_question` 參數；`pending_user_knowledge` 狀態新增 `original_question` 欄位；刪除 `handle_pending_user_knowledge_step()`，功能併入 `handle_chat_message()`。

**2026-08-02 追加修正**：Robin 回報問完氣溫（誠實回不知道）後換講一句完全無關的新事情（陳述句，非問句），被誤判成「拒絕記錄」；追查發現「無關新內容」選項措辭侷限在「問句」，修正為「除了以上情況以外的任何內容」的 catch-all 寫法，「拒絕」選項收緊為必須是明確拒絕/跳過語句。

## 2026-08-01 [標籤：AI] ADR-7：打字誤植改為「先反問確認，等使用者回覆才回答」（部分 supersede ADR-6）

**狀態**：accepted（ADR-6 的「直接假設並回答」機制部分 superseded）

**背景**：ADR-6 為同音字/形似字打字誤植加了容錯規則，但作法是「假設是打字誤植、直接用最相近的知識庫人名回答」。Robin 實測後認為太冒進——萬一猜錯人，會在使用者沒發現的情況下講出錯誤資訊。

**討論內容**：比較方案 A（維持假設並直接回答，回覆末尾附確認句，少一輪來回但假設錯了會直接輸出錯誤資訊）與方案 B（先反問確認，等使用者回覆確認/否認後才真正回答，多一輪來回但不會講錯）。

**決策**：採方案 B（2026-08-01 Robin「先確認再回答比較好喔」指示）。

**理由**：打錯字猜錯人的代價比多問一句的代價更高，值得用一輪來回換取正確性。

**後果**：`chat.py` 新增 `_CONFIRM_NAME_MARKER`；偵測到標記時設定 `pending_name_confirm` 狀態。

**2026-08-01 追加修正**：Robin 回報問「阿牛是誰」（知識庫當時沒有這筆資料）卻被反問「你是說『吳凱吉』嗎？」，原因是 prompt 範例寫死了一個真實家人姓名，模型照抄範例而非真的比對知識庫；修正反問句必須帶出資料中真實存在且高度相似的人名，沒有相似人名時要走「不知道」規則。

## 2026-08-01 [標籤：AI] ADR-8：主動新增知識與 `/clean-target-dialog`——共用知識庫寫入/刪除一律限定 Owner

**狀態**：accepted

**背景**：「使用者主動要求就把資訊寫進知識庫」的機制早已標記為已知缺口；Robin 明確指示「主動記知識的功能、/clean-target-dialog API 現在先開發吧」，需要決定：(1) 主動新增知識時誰能寫進全家共用的知識庫；(2) `/clean-target-dialog` 誰能刪共用知識庫的資料。

**決策**（2026-08-01 Robin 確認）：①寫入範圍——`general_persona`／`general_family` 只有 Robin 能編輯，非 Owner 一律只能寫進自己的 `custom`，最終 `category` 由 Python 依 `auth.is_owner()` 現場強制覆蓋，不信任模型判斷 ②刪除範圍——只有 Robin 觸發時候選清單才納入共用知識庫 ③新增知識時額外記錄分類/標籤（`knowledge_base.label`）④兩個功能都沿用 ADR-6/ADR-7 已建立的「單次使用者可見 LLM 呼叫先反問確認，下一輪內部 LLM 呼叫做分類判斷」模式 ⑤`knowledge_base` 對 `/clean-target-dialog` 一律硬刪除，`conversation_logs` 沿用軟刪除慣例。

**理由**：與既有「伺服器端防線」慣例一致，不信任 LLM 對權限範圍的自我判斷；兩輪反問確認架構已驗證過可行且複雜度可控。

**後果**：`src/bot/knowledge.py` 新增 `save_knowledge()`；`chat.py` 新增 `_REQUEST_SAVE_MARKER`；`commands.py` 新增 `handle_save_knowledge_confirm_step()`／`start_clean_target_dialog_confirm()`。

## 2026-08-02 [標籤：AI] ADR-9：語音的最終執行確認——高風險操作在「語意確認」之後再加一道「逐字打字」硬性關卡（FR-16a）

**狀態**：accepted

**背景**：2026-08-02 Robin 指出具體風險情境：「使用者用語音說執行 A 決策，但 LLM 聽錯了，直接執行 B 決策，且已刪除的紀錄無法回頭補上」——如果聽錯的內容剛好符合 CONFIRM 語意，現有機制會照樣放行執行。

**決策**（2026-08-02 Robin 選定「復誦＋最終執行前一定要打字答一次」）：①適用範圍——`/clean-all-dialog`、`/clean-target-dialog`、主動記知識三個高風險 flow，判定 CONFIRM 後不馬上執行，轉入 `pending_*_final_confirm` 狀態，要求打字逐字輸入「確認執行」②語音一律不通過最終確認，`router.handle_message()` 新增 `via_voice` 參數 ③非語音但沒逐字輸入關鍵字一律視為取消 ④語音訊息刻意不清除 `pending_*_final_confirm` 狀態，避免使用者搞不清楚原本操作算不算數 ⑤權限判斷不重複，強制邏輯留在轉入最終確認狀態之前做完 ⑥（2026-08-02 追加）下載/轉錄前先短路：卡在最終確認狀態時收到新語音，直接短路拒絕，不下載/轉錄，避免浪費 Drive/Groq 額度。

**理由**：「聽錯」與「聽對但語意分類錯」是兩種不同層次的風險，前者無法靠加強 prompt 解決，只能靠改變輸入管道本身——要求最後一步必須是打字。

**後果**：`commands.py` 新增 `_FINAL_EXECUTE_KEYWORD = "確認執行"` 與三個 `handle_*_final_confirm_step()`；`router.py` 新增 `via_voice`／`_FINAL_CONFIRM_FLOWS`。

## 2026-08-01 [標籤：AI] `/clean-all-dialog` 觸發即直接刪除改為「先反問確認再執行」

**狀態**：accepted

**背景**：`/clean-all-dialog` 原始實作是觸發詞一送出就立即清除該使用者的對話紀錄與摘要，Robin 實測後回報沒有給使用者反悔的機會，違反專案「操作前先確認」的一貫原則。

**決策**：觸發後不再立即刪除，改為先回覆固定文字「你目前有 {N} 筆對話紀錄，確定要清除嗎？（不會影響你的知識庫內容）」（不經過 LLM），設定 `pending_clean_all_dialog_confirm` 狀態，等使用者下一則回覆經單次 LLM 判斷 CONFIRM/CANCEL 後才真正執行 `handle_clean_all_dialog()`；任何非 CONFIRM 的判定結果一律視為取消。

**理由**：延續專案既有的「確認再執行」模式，避免不可逆的刪除操作缺乏反悔機會。

**後果**：這是後續 2026-08-02 ADR-9（FR-16a 逐字打字最終確認）在 `/clean-all-dialog`／`/clean-target-dialog`／主動記知識三個高風險 flow 上疊加第二層防護的前置基礎——先有本次的「反問確認」，才有 ADR-9 進一步要求「確認後仍需再打字輸入『確認執行』」。
