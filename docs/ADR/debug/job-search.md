# 求職模組 修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。

## 2026-08-18 「職缺關鍵字設定」新增關鍵字，單一技術詞（如「AI」）被誤判成 UNCLEAR

**現象**：在「求職設定→職缺關鍵字設定→➕ 新增關鍵字」輸入「AI，薪資 5 到 6 萬」，系統回覆「不太確定職缺關鍵字，請再描述得明確一些。」，沒有成功新增；改輸入「AI 相關職缺，薪資 5 到 6 萬」則成功新增（清單顯示為「刪除：AI」，代表 LLM 這次正確把「AI 相關職缺」拆解出關鍵字「AI」）。

**排查過程**：這一步是把使用者輸入丟給 `commands._JOB_SEARCH_CRITERIA_PARSE_PROMPT`（`src/bot/commands.py`），由 Gemini 判斷 `STATUS: CLEAR/UNCLEAR` 與 `KEYWORD`／`REGION`／`SALARY_MIN`／`SALARY_MAX`；`job_settings.handle_criteria_add()` 只要 `STATUS != "CLEAR"` 或 `KEYWORD` 空白，就直接回「不太確定」，不會新增。比對兩次輸入的差異——「AI」單獨出現 vs. 搭配「相關職缺」——確認是 Gemini 對輸入內容的語意判斷差異，不是程式解析邏輯的問題（`_parse_key_value_block()` 兩次呼叫都能正常解析出完整欄位，差別只在 `STATUS` 判斷結果）。因為 Cowork 沙盒連不到正式環境用的 Gemini API，這次排查是對照 Robin 提供的實際對話截圖比對兩次輸入/輸出，而非在沙盒內重現。

**根因**：`_JOB_SEARCH_CRITERIA_PARSE_PROMPT` 雖然有註明「職稱、技能、產業方向都算關鍵字」，但沒有明確說明「單一縮寫詞／技術詞（如『AI』、『Python』）本身就足夠算作關鍵字」；Gemini 對過短、過於籠統的孤立詞彙（單獨的「AI」，不搭配任何職稱、動詞或「相關」「工程師」之類的修飾詞）傾向保守判成 `UNCLEAR`，即使該詞在求職情境下其實已經是明確技能/技術方向。

**修復方式**：尚未修改程式碼，待 Robin 確認是否要調整 prompt。目前有可行的操作面繞過方法（輸入時幫關鍵字加一個修飾詞，例如「OO 相關職缺」「OO 工程師」），Robin 已用這個方式成功新增全部 3 筆設定。若要從根本解決，預計調整方向：在 `_JOB_SEARCH_CRITERIA_PARSE_PROMPT` 明確追加一條規則，例如「即使只有單一技術詞/縮寫（如 AI、Python、UI/UX）沒有搭配職稱或其他修飾詞，也視為明確關鍵字，一律填 CLEAR」，降低這類輸入被誤判成 UNCLEAR 的機率。

**驗證方式**：尚未驗證（沙盒無法呼叫正式 Gemini API）；若之後調整 prompt，須請 Robin 在正式環境用「AI，薪資 5 到 6 萬」這類「單一技術詞＋薪資，不帶職稱修飾詞」的輸入重新測試，確認能一次成功新增，且不影響既有其他成功案例（如「台北的 AI 工程師，薪資 5 到 8 萬」）。

## 2026-08-18 續：Robin 確認要調整 prompt，已補上規則（連同多地區支援一併處理）

**現象**：同上一則；Robin 同一次對話中確認要從根本解決，並額外提出「職缺關鍵字設定」清單不顯示地區/薪資、無編輯功能、無法設定多地區三個相關需求（見 `docs/ADR/discuss/job-search.md` 2026-08-18「職缺關鍵字設定支援多地區、清單顯示地區/薪資、新增編輯功能」條目）。

**排查過程**：無新增排查，沿用上一則的根因判斷；本次是實作修復。

**根因**：同上一則（Gemini 對孤立單一技術詞過度保守判成 `UNCLEAR`）。

**修復方式**：`src/bot/commands.py` 的 `_JOB_SEARCH_CRITERIA_PARSE_PROMPT` 追加規則：「即使只有單一技術詞、技能縮寫或職稱（例如「AI」「Python」「UI/UX」），沒有搭配其他修飾詞，也視為明確關鍵字，一律填 CLEAR，不要因為詞彙簡短或看起來籠統就判成 UNCLEAR」。同一批連帶完成多地區支援與清單顯示/編輯功能，詳見對應 discuss ADR 條目與 SPEC.md FR-41c。

**驗證方式**：全專案測試 `python3 -m pytest`（1602 項，含新增的 6 個 `test_job_settings.py` 案例）全數通過，`ruff check` 全過；但 prompt 文字調整本身無法在 Cowork 沙盒對正式 Gemini API 驗證語意判斷效果是否真的改善。**尚待 Robin 在正式環境用「AI，薪資 5 到 6 萬」這類輸入實測**，確認一次就能成功新增、且不影響既有帶職稱修飾詞的成功案例。

## 2026-08-24 職缺清單訊息過長打不開

**現象**：Robin 在 Telegram「求職設定」點擊「職缺清單」，完全沒有任何回應（沒有錯誤訊息、沒有新訊息）。

**排查過程**：追蹤 `job_search:jobs` callback 分派到 `job_settings.start_jobs_list()`，發現它把 `db.select("job_postings")`（資料庫裡**所有**職缺、沒有任何筆數上限）整批串成一則文字訊息回傳。104 爬蟲每組搜尋條件最多翻 20 頁（`_MAX_PAGES_PER_CRITERIA = 20`），每頁最多 20 筆（`_LIST_PAGE_SIZE = 20`），Robin 目前設定 3 組關鍵字，且 `job_postings` 從不清理，長期累積下容易讓這則訊息超過 Telegram 單則訊息 4096 字元上限。再往下追到 `src/bot/webhook.py` 處理 callback_query 的段落（約 560～577 行），發現 `send_text()` 是包在 `try/except Exception` 裡「失敗只記 log，不做任何事」（刻意設計成避免單一功能壞掉波及其他功能）——所以一旦訊息因超字數被 Telegram API 拒收，使用者端就是完全沒有任何反應，連錯誤提示都看不到，跟 Robin 描述的現象完全吻合。

**根因**：`start_jobs_list()` 沒有分頁機制，職缺數量隨每週爬蟲持續累積後，單則訊息遲早會超過 Telegram 4096 字元上限；`webhook.py` 既有的「送出失敗只記 log」防護網又讓這個失敗對使用者完全不可見，兩者疊加造成「按了完全沒反應」的體感。

**修復方式**：`job_settings.start_jobs_list()` 新增 `page` 參數，改成每頁固定 `_JOBS_LIST_PAGE_SIZE`（＝10）筆，訊息標題附「第 X／Y 頁」，並依是否有上一頁／下一頁動態附「⬅️ 上一頁」「➡️ 下一頁」按鈕（`job_search:jobs:page:<n>`）；`router.py` 新增對應分派。不修改 `webhook.py` 既有的失敗吞例外設計（那是刻意的整站安全網，本次只從源頭避免訊息真的超長）。

**驗證方式**：新增 `tests/bot/test_job_settings.py::test_jobs_list_paginates_instead_of_one_giant_message`（25 筆職缺驗證 3 頁分頁與按鈕正確性）及 `test_jobs_list_out_of_range_page_clamps_to_last_page`；全專案 `pytest -q` 1617 passed，`ruff check` 全過。分頁按鈕本身無法在沙盒對正式 Telegram Bot API 實測，**尚待 Robin 在正式環境確認「職缺清單」能正常開啟並翻頁**。

## 2026-08-24 推薦職缺不分青紅皂白

**現象**：Robin 回報 Mobile App「推薦職缺」有三個問題：①只爬到少量職缺，且很多明顯不相關（工地主任、人資助理）；②每筆後面的分數看起來都是「一分」，不知道代表什麼、為什麼全部一樣；③明知道不合適也硬推薦，沒有「找不到就不推薦」的邏輯。

**排查過程**：先查 `src/services/app_analytics.py::jobs()`，發現 `recommendations` 是 `open_postings[:10]`——依 `match_score DESC NULLS LAST` 排序後**無條件**取前 10 筆，沒有任何「是否已評分」或「分數是否夠高」的門檻。接著查為什麼分數看起來都一樣：Mobile 前端 `mobile/app/analytics/[module].tsx` 顯示 `` `${item.match_score ?? "—"} 分` ``，NULL 分數會 fallback 顯示破折號「—」，在小字體螢幕截圖裡很容易被誤看成「一」——不是真的「1 分」，是根本沒有分數。再往上追為什麼分數全是 NULL：`src/bot/job_search.py::check_and_run_weekly_job_search()` 只有在呼叫端傳入非 `None` 的 `llm_client` 時才會執行 FR-37 Gemini 契合度評分；`main.py::_check_job_search_weekly_crawl()` 只有環境變數 `GEMINI_API_JOB_SEARCH_KEY` 有設定時才會建立這個 `llm_client`，未設定就傳 `None`，評分與雙重排名 Excel 寄送整段「優雅跳過」，不出錯也不通知任何人。**2026-08-24 當天 Robin 一開始表示尚未設定這個變數，事後（同日稍晚）改口確認 `GEMINI_API_JOB_SEARCH_KEY` 其實早就設定在 Render 上，並截圖比對變數名稱與 `main.py` 讀取的 `GEMINI_API_JOB_SEARCH_KEY` 完全一致——原本判斷「金鑰未設定」是根因，這點是錯的，見下方補充。**

**根因（2026-08-24 當天原始判斷，已修正，見下方補述）**：~~`GEMINI_API_JOB_SEARCH_KEY` 未設定 → 契合度評分（FR-37）從未真正執行過~~。修正後：真正卡住評分的門檻是 `list_scorable_jobs()`（見 `src/bot/job_search.py`）——只有「所屬公司背景資料（`job_companies.background`）已回填」的職缺才會被納入評分，Robin 尚未透過 FR-35 的 CSV／Drive 協作流程回填任何公司背景資料，導致 `list_scorable_jobs()` 回傳空清單，`score_jobs()` 沒有任何職缺可評、`score` 恆為 `NULL`。Mobile 推薦清單因為當時沒有評分門檻，把「爬到的職缺」直接當成「推薦的職缺」全部塞給使用者，包含 104 自己寬鬆全文檢索比對出來、跟履歷完全不相關的結果。這是「評分管線因公司背景資料缺漏而空轉」加上「推薦清單沒有品質門檻」兩個問題疊加的結果。

**修復方式**：分兩部分。①Robin 需要透過既有 FR-35 協作流程，把每週寄出的「新公司列表」CSV 填上公司背景資料後上傳回 Google Drive，`list_scorable_jobs()` 才會有職缺可評（此為資料填寫，非程式碼變更；已排除金鑰問題）。②`app_analytics.py::jobs()` 新增 `_RECOMMENDATION_MIN_SCORE = 60`（沿用既有 high／medium 60 分分界）門檻，`recommendations` 改成只保留「`match_score` 非 NULL 且 ≥ 60」的職缺再取前 10 筆；找不到符合門檻的職缺時回傳空陣列。Mobile 前端 `[module].tsx` 空清單文案由「這段期間沒有推薦職缺」改為「目前沒有符合的推薦職缺」，更精確反映「有評估過但沒有合適的」而非「這段期間剛好沒資料」。104 搜尋比對過於寬鬆導致爬到不相關職缺（問題①的另一半成因）屬 104 外部服務行為，目前只能靠評分機制事後過濾，不在本次處理範圍內。

**驗證方式**：新增 `tests/services/test_app_analytics.py::test_jobs_recommendations_exclude_unscored_and_low_score_postings`、`test_jobs_recommendations_empty_when_nothing_meets_threshold`；全專案 `pytest -q` 1617 passed，`ruff check` 全過。評分管線是否真的開始產生分數，**尚待 Robin 回填公司背景資料、下週一排程實際跑過一次後，用真實資料確認推薦清單是否合理**。

## 2026-08-24 週排程爬蟲遇 104 429 限流，整批中斷

**現象**：Robin 提供 Render 正式環境錯誤 log，`_check_job_search_weekly_crawl()` 於 01:01:01 記錄「求職模組週排程（104 職缺爬蟲／FR-37 評分）失敗」，追蹤例外是 `crawl_and_upsert_jobs()` 呼叫 `job104_client.fetch_job_detail()` 時收到 `429 Too Many Requests`，重試耗盡後例外往外拋出，整個排程函式中止。

**排查過程**：讀 `src/bot/job_search.py::crawl_and_upsert_jobs()`：外層 `for criteria in criteria_list` 每組關鍵字、內層 `while page <= _MAX_PAGES_PER_CRITERIA` 每頁清單、再內層 `for job in matching_jobs` 逐筆呼叫 `fetch_job_detail()`；FR-34c 每次請求後有 2～4 秒隨機延遲（`_polite_delay()`），`submodules/job104/client.py::_is_retryable_requests_error()` 把 429 視為可重試，`call_with_retry()` 最多重試 3 次、Backoff 1／2／4 秒。但 `fetch_job_detail()` 這一行本身沒有包 `try/except`——重試 3 次仍是 429 時，例外會直接往外傳出**整個** `crawl_and_upsert_jobs()`，導致這組條件當下這一筆之後、以及後面尚未處理的所有條件／分頁全部被跳過，這次排程直接視為失敗（`main.py` 的外層 try/except 只記 log，不會續跑）。已寫入資料庫的職缺（例外發生之前逐筆 upsert 的部分）會保留，但當次排程沒爬完的部分全部遺失，下次排程才會補上（若下次沒有再被同一問題卡住）。這也補上了 Robin 先前反映「只有爬到 10 個職缺」的另一個成因：不只是 Mobile 推薦清單固定只顯示前 10 筆（已知），實際爬蟲本身很可能也常常被 104 限流提早中斷，導致 `job_postings` 累積的職缺總數遠低於預期。

**根因**：`crawl_and_upsert_jobs()` 對單筆 `fetch_job_detail()` 失敗沒有任何容錯／略過機制，104 在既有 2～4 秒延遲下仍會不定期回 429（可能是短時間內單一 IP 請求量累積觸發），重試 3 次仍失敗時，一次限流就會讓整批（可能涵蓋多組關鍵字、多頁）爬蟲全部中斷，而不是只跳過那一筆職缺。

**修復方式**：與 Robin 討論後採選項①，不動選項②（不調整共用重試模組的延遲秒數，避免影響其他呼叫端）。`crawl_and_upsert_jobs()` 把 `fetch_job_detail()` 這筆呼叫包 `try/except`，單筆持續失敗（例如重試 3 次仍 429）記 log 並略過該筆，繼續處理下一筆／下一組條件，不讓整批中斷；回傳統計摘要新增 `skipped_job_count` 記錄略過筆數，方便之後追蹤限流頻率。見 `docs/specs/SPEC.md` FR-41f。

**驗證方式**：新增 `tests/bot/test_job_settings.py::test_crawl_skips_single_failed_job_instead_of_aborting_whole_batch`（模擬中間一筆 `fetch_job_detail` 拋例外，驗證前後兩筆仍正常寫入、`skipped_job_count == 1`）；同步更新 `tests/bot/test_job_search.py` 既有對回傳值做完整字典比對的測試，補上新欄位。全專案 `pytest -q` 1618 passed（`test_migration_sql.py` 1 項因沙盒環境限制失敗，屬既有已知問題非本次程式碼問題），`ruff check .` 對本次異動檔案全過。**尚待 Robin 在正式環境觀察下一次排程執行紀錄，確認單筆 429 不再讓整批中斷、`job_postings` 累積筆數是否明顯回升**。

## 2026-08-24 週排程寄送公司列表信件 SMTP 連線失敗

**現象**：同一批 Render log 另外顯示 02:22:58 排程執行 `send_new_companies_email()` 時，`smtplib.SMTP_SSL` 連線 `smtp.gmail.com:465` 拋出 `OSError: [Errno 101] Network is unreachable`。

**排查過程**：查 `submodules/email/client.py`，`_SMTP_HOST = "smtp.gmail.com"`、`_SMTP_PORT = 465`，直接用 `smtplib.SMTP_SSL` 對外連線，沒有經過任何 Email API 中介服務。`Network is unreachable` 是網路層級直接失敗（不是帳密、憑證或逾時問題），這個 Cowork 沙盒本身連不到 Render 正式環境，無法直接重現或排除，只能從錯誤型態判斷：這個訊息型態常見於雲端平台對外站 SMTP（尤其是直連 25／465／587 這類埠）出站流量的限制。

**根因**：尚未確認。高度懷疑是 Render 這個服務方案對外直連 SMTP 埠有網路層限制，但這只是推測，需要 Robin 自行查證 Render 文件／支援管道是否有此限制，或觀察此錯誤是每次必定發生還是偶發。

**修復方式**：查證 Render 官方 changelog 確認免費方案確實自 2025 年 9 月起封鎖對外 SMTP 埠 25／465／587，只有升級付費方案能恢復；Robin 明確表示不想付費，改走 Email API。比較 Resend（現行政策需驗證自有網域，Robin 沒有網域，否決）與 SendGrid（提供 Single Sender Verification，只需驗證單一信箱、不需網域，符合 Robin 現況），與 Robin 討論後選定 SendGrid。Robin 完成 SendGrid 帳號、Single Sender Verification（驗證信箱與既有 `GMAIL_USER` 同一組）、API Key 並貼到 Render 環境變數 `SENDGRID_API_KEY` 後，`submodules/email/client.py` 的 `send_text()`／`send_text_with_attachment()` 改成呼叫 SendGrid HTTPS API（走 443 埠，不受此限制影響），取代原本直連 `smtplib.SMTP_SSL`；讀信 IMAP（993 埠）不受影響，維持原樣。完整架構決策見 `docs/ADR/discuss/submodules-core.md` 2026-08-24「`submodules/email` 寄信改走 SendGrid API，取代直連 Gmail SMTP」條目。

**驗證方式**：`tests/submodules/email/test_client.py` 全面改寫寄信相關測試（mock `requests.post` 取代 mock `smtplib.SMTP_SSL`），涵蓋成功寄送、缺少 `send_api_key` 時報錯、429 重試、401/403/400 等永久性錯誤不重試；`tests/bot/test_webhook.py` 同步更新 FR-19b 備援通知測試（新增 `SENDGRID_API_KEY` 環境變數檢查與缺少時不寄信的案例）。全專案 `pytest -q` 1619 passed（`test_migration_sql.py` 1 項因沙盒環境限制失敗，屬既有已知問題），`ruff check .` 對本次異動檔案全過。**尚待 Robin 在正式環境觀察下次排程寄送公司列表信件、以及 Telegram 故障時的備援通知是否都能成功送達**。
