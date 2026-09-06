---
updated: 2026-09-06
---


# 開發進度

> 本檔案整併自兩份舊紀錄：`docs/specs/_archive/robinson/PROGRESS.md`（Claude Code 協作的產品階段里程碑）與 `docs/specs/_archive/codex.md`（Codex 開發異動紀錄，內容集中在 Mobile App）。
> 「開發者」欄依內容來源判斷：Claude Code 協作里程碑標 `Claude`、codex.md 工作階段標 `Codex`、Claude Code 協作開始前由 Robin 自行完成的項目標 `Robin`。
> 除錯敘事（現象／根因／修復／驗證）已拆到 `docs/ADR/debug/`，決策脈絡已拆到 `docs/ADR/discuss/`，本檔只保留「哪一天、做了什麼、誰做的、狀態」。

## 目前有效進度

> 本區是唯一的現行狀態摘要；下方「歷史時程與任務紀錄」只保留當時開發脈絡，
> 其舊「待開發／待推版」字樣不再代表目前狀態。

| 範圍 | 目前狀態 | 依據／剩餘工作 |
| --- | --- | --- |
| Telegram Phase 6 選單化、功能開關、排程、一般對話、FR-6c 草稿保護、FR-77 取消功能清理 | 完成（已 push／部署／實機驗收） | 既有功能 commit `1601f34`；migration 修復 commit `07e986a`。Render 於 2026-08-18 12:25 依序成功套用 0084～0094，0094 已完成四張取消功能資料表清理；Mobile 客訴與舊錯誤結案死程式已由 commit `fb8c616` 移除，Robin 已 push 並完成實機驗收。 |
| FR-72b 帳號層隱私數字遮罩 | 完成 | Mobile 與 Telegram 共用 `users.privacy_mask_enabled`；Telegram 資料查詢已套用遮罩。 |
| FR-19j～FR-20 跨平台系統錯誤治理 | 已 push／部署；Telegram 管理頁已實機確認 | commit `005752b`、文件 commit `94eea15` 已在 `origin/main`。Owner Telegram 錯誤管理畫面已由 Robin 提供實機截圖確認；Mobile API 未預期 5xx 事故通報、10 分鐘合併、受影響者追蹤與跨平台康復通知已實作，Mobile 真實 5xx 不刻意於正式環境製造事故。 |
| Telegram 重構後 Mobile 跨端相容修正 | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `fb8c616` 與文件 commit `fa9f03c` 已 push。一般生活模組不再受舊 `feature_toggles` 關閉；Mobile 客訴與舊錯誤結案程式徹底移除；考試成績顯示 `note`；求職 Top 推薦排除關閉職缺、契合度分布保留全部本期分析。無 Migration、無正式資料刪除。 |
| FR-6a／FR-6b 舊 Slash Command 入口清理 | 完成 | Slash Command 只保留 `/start`；`/rule`、`/my_toggles`、`/set_toggle`、`/set_family_birthday`、`/friend_chat` 及舊文字狀態機、死程式與過時測試均已移除。功能改由使用規則選單、功能開關與排程設定、重要日子設定及自然語言「陪我聊聊」提供。 |
| Mobile 分析頁、目標摘要、成果置頂、求職與考試頁改版（FR-64b～FR-64d／FR-73a／FR-76b） | 完成（已 push／實機驗收；最終批部署狀態未單獨回報） | commit `28ad29a`、`e667a11`、`83db1ec`、`2f7de66` 與對應文件 commit 已 push。Robin 已完成全部實機驗收；求職三頁籤、考試證照切換分析及四個獨立頁載入畫面正常。 |
| 英文口說／其他語言學習、非 TOEIC 證照題庫 | 擱置／未排入 Roadmap | 只放 `DRAFT.md`，不列為當前待開發任務。 |
| 最終跨頁回歸與根目錄 README | 完成（已 commit／待 push） | commit `37b3345`。完整 `pytest -q`：1806 passed、1 項第三方 warning；`ruff check .`、Mobile TypeScript、Expo Web export 與文件交叉檢查通過。根 README 已依現行架構、功能、啟動、測試、部署、Migration、安全與文件索引重寫。 |
| 「職缺關鍵字設定」多地區、清單顯示、編輯功能（FR-41c） | 完成（已 commit／待 push） | commit `07adf1f`。不需 Migration。`src/bot/commands.py`（Prompt）、`src/bot/job_search.py`（多地區 OR 比對＋`update_search_criteria()`／`format_search_criteria()`）、`src/bot/job_settings.py`（清單顯示＋編輯流程）、`src/bot/router.py`（`criteria:edit:*`）已異動；`tests/bot/test_job_settings.py` 新增 6 項測試，全專案 `pytest -q` 1602 passed（`tests/migrations/test_migration_sql.py` 1 項因 Cowork 沙盒未攜帶完整 `.sql` migration 檔案而失敗，屬環境限制非程式碼問題）；`ruff check .` 對本次異動檔案全過。Prompt 對單一技術詞判斷的實際效果待 Robin 在正式環境用 Gemini 實測驗證。 |
| Mobile App 帳密登入連續錯誤鎖定＋鎖定通知（FR-65a） | 完成（已 commit `cb65652`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 新增 migration `0098_add_mobile_login_lockout_to_users.sql`（`users.mobile_login_failed_attempts`／`mobile_login_locked_at`）。`src/services/app_auth.py`（`AccountLockedError`、`login()` 鎖定判斷與累加、鎖定觸發時呼叫可選的 `notify_owner_locked` 回呼）、`src/api/app_auth.py`（`/auth/login` 新增 `ACCOUNT_LOCKED` 錯誤碼、`_notify_owner_account_locked()` 透過 Telegram 私訊 Owner）、`src/bot/auth.py`（`list_mobile_login_locked_users()`／`unlock_mobile_login()`）、`src/bot/commands.py`（權限管理選單新增「🔓 解鎖 Mobile App 帳號」按鈕與 callback）、`mobile/app/login.tsx`（`ACCOUNT_LOCKED` 併入密碼欄位錯誤顯示）已異動。新增 `tests/bot/test_permission_unlock_mobile.py`（5 項）與 `tests/api/test_app_auth.py` 新增 6 項（含鎖定通知觸發／未設定環境變數不通知）；`python3 -m pytest tests/api tests/bot -q`：1246 passed；`ruff check .` 對本次異動檔案全過。決策脈絡見 `docs/ADR/discuss/mobile-app.md` 2026-08-23 條目及續篇。 |
| SPEC.md 補登 FR-41c（文件缺漏修正） | 完成（文件修正，無程式碼異動） | 發現 FR-41c（多地區、清單顯示、編輯功能，commit `07adf1f`）從未寫入 `SPEC.md`，違反「已上線需求須有正式規格」原則；本次僅補上 `SPEC.md` FR-41c 條目，不涉及程式碼變更。 |
| Telegram「職缺清單」分頁（FR-41d） | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。`src/bot/job_settings.py`（`start_jobs_list()` 新增 `page` 參數，每頁 `_JOBS_LIST_PAGE_SIZE`＝10 筆，動態上一頁／下一頁按鈕）、`src/bot/router.py`（`job_search:jobs`／`job_search:jobs:page:<n>` 分派）已異動。新增 `tests/bot/test_job_settings.py::test_jobs_list_paginates_instead_of_one_giant_message`、`test_jobs_list_out_of_range_page_clamps_to_last_page`；全專案 `pytest -q` 1617 passed，`ruff check .` 對本次異動檔案全過。根因排查見 `docs/ADR/debug/job-search.md` 2026-08-24「職缺清單訊息過長打不開」條目。分頁按鈕實際操作待 Robin 在正式環境確認。 |
| Mobile App 推薦職缺加上分數門檻（FR-41e） | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。`src/services/app_analytics.py`（`jobs()` 新增 `_RECOMMENDATION_MIN_SCORE`＝60 門檻，只保留已評分且 ≥60 分職缺）、`mobile/app/analytics/[module].tsx`（空清單文案改為「目前沒有符合的推薦職缺」）已異動。新增 `tests/services/test_app_analytics.py::test_jobs_recommendations_exclude_unscored_and_low_score_postings`、`test_jobs_recommendations_empty_when_nothing_meets_threshold`；全專案 `pytest -q` 1617 passed，`ruff check .` 對本次異動檔案全過。根因排查見 `docs/ADR/debug/job-search.md` 2026-08-24「推薦職缺不分青紅皂白」條目（2026-08-24 當日已修正：`GEMINI_API_JOB_SEARCH_KEY` 其實早已設定，真正卡住評分的是公司背景資料尚未回填）。評分管線本身尚待 Robin 回填公司背景資料並經下週排程實際跑過一次後，才能用真實資料驗證推薦結果是否合理。 |
| 週排程爬蟲單筆容錯，429 限流不再中斷整批（FR-41f） | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。`src/bot/job_search.py`（`crawl_and_upsert_jobs()` 單筆 `fetch_job_detail()` 失敗改記 log 略過，回傳新增 `skipped_job_count`）已異動。新增 `tests/bot/test_job_settings.py::test_crawl_skips_single_failed_job_instead_of_aborting_whole_batch`；同步更新 `tests/bot/test_job_search.py` 既有 4 項對回傳值做完整字典比對的測試。全專案 `pytest -q` 1618 passed，`ruff check .` 對本次異動檔案全過。根因排查見 `docs/ADR/debug/job-search.md` 2026-08-24「週排程爬蟲遇 104 429 限流，整批中斷」條目；實際效果尚待 Robin 在正式環境觀察下次排程執行結果。 |
| `submodules/email` 寄信改走 SendGrid API（取代直連 SMTP） | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。起因：Render 免費方案封鎖對外 SMTP 埠，直連 Gmail SMTP 寄信全面失效（含 FR-19b Telegram 故障備援通知、FR-35b 公司列表協作信）。`submodules/email/client.py`（`send_text()`／`send_text_with_attachment()` 改呼叫 SendGrid HTTPS API，新增建構參數 `send_api_key`；讀信 IMAP 不動）、`main.py`、`src/bot/webhook.py`（傳入 `SENDGRID_API_KEY`）已異動；`.env.example`／`README.md` 新增 `SENDGRID_API_KEY` 說明。`tests/submodules/email/test_client.py` 全面改寫寄信測試（mock `requests.post`），`tests/bot/test_webhook.py` 新增 1 項、更新既有 2 項。全專案 `pytest -q` 1619 passed，`ruff check .` 對本次異動檔案全過。架構決策見 `docs/ADR/discuss/submodules-core.md` 2026-08-24 條目；根因排查見 `docs/ADR/debug/job-search.md` 2026-08-24「週排程寄送公司列表信件 SMTP 連線失敗」條目。實際寄信效果尚待 Robin 在正式環境觀察下次排程與備援通知是否成功送達。 |
| TOEIC 單字題生成節流退避（不再燒光嘗試次數） | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。起因：Robin 提供 Render 錯誤 log，發現 `generate_track2_vocab_questions()` 撞 `submodules/llm` 本地端節流保護（8 次/60 秒）時直接放棄該次嘗試、無等待，導致 63 次嘗試機會在毫秒內燒光，實際只有前段極少數呼叫真正成功。`src/bot/toeic.py`（新增 `sleep_func` 參數，捕捉 `LLMQuotaGuardError` 時退回 `attempts` 計數並等待 8 秒再重試）已異動。新增 `tests/bot/test_toeic.py::test_generate_track2_waits_and_retries_on_quota_guard_error_without_wasting_attempt`、`test_generate_track2_quota_guard_retries_do_not_count_toward_max_attempts`。全專案 `pytest -q` 1621 passed，`ruff check .` 對本次異動檔案全過。根因排查見 `docs/ADR/debug/skill-growth.md`（新檔案）2026-08-24「TOEIC 單字題生成撞本地端節流上限」條目。實際效果尚待 Robin 在下次週排程（週日 22:00）觀察。 |
| 公司背景 CSV 涵蓋歷史缺漏＋寄信失敗不拖累評分（FR-35 修正） | 完成（已 commit `7c648a1`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。起因：Robin 追問「之前沒收到過新公司列表信，是不是 Email 功能壞掉」，排查發現 `send_new_companies_email()` 沒有容錯，寄信失敗會讓後面更重要的 FR-37 評分流程也跟著中斷；且 CSV 寄送範圍只看「這次新增的公司」，已存在的舊公司永遠不會被排進未來的 CSV，導致歷史累積的公司背景永久卡住。`src/bot/job_search.py`（新增 `list_companies_without_background()`，CSV 範圍改成「所有背景仍缺漏的公司」；`send_new_companies_email()` 呼叫包 try/except）已異動。新增 `tests/bot/test_job_search.py::test_check_and_run_weekly_job_search_resends_historical_company_missing_background`、`test_check_and_run_weekly_job_search_email_failure_does_not_block_scoring`；`tests/bot/conftest.py` 補上 `background IS NULL` 查詢支援。全專案 `pytest -q` 1624 passed，`ruff check .` 對本次異動檔案全過。根因排查見 `docs/ADR/debug/job-search.md` 2026-08-24 續「公司背景 CSV 寄信失敗會拖累整個評分流程、且歷史公司永久卡住」條目。 |
| Telegram 職缺清單排版加空行（FR-41d 補充） | 完成（已 commit `126b9dd`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。Robin 反饋原本排版太擠；`src/bot/job_settings.py`（`start_jobs_list()` 每筆職缺之間改用空行分隔）已異動，分頁機制與頁數不變。新增 `tests/bot/test_job_settings.py::test_jobs_list_has_blank_line_between_each_job`。全專案 `pytest -q` 1624 passed，`ruff check .` 對本次異動檔案全過。**2026-08-24 追記**：`7c648a1` 這筆 commit message 宣稱已完成此變更，但事後比對實際程式碼發現變更並未真正寫入，部署後仍是舊排版；已於 `126b9dd` 補上正確程式碼並用 `git show` 逐行核對內容。詳見 `docs/ADR/debug/job-search.md` 2026-08-24 續「職缺清單排版太擠」條目。 |
| `/healthz` 排程檢查改共用單一資料庫連線（FR-21a） | 完成（已 commit `dc1e50c`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。起因：Robin 收到 Neon「已用 80% compute CU-hours」email，排查發現既有 FR-21 監控只涵蓋儲存空間、沒涵蓋 compute CU-hours；並發現 `/healthz`（cron-job.org 每 10 分鐘觸發）過去讓 14 個 `_check_*()` 各自開關資料庫連線，一天累積 2016 次連線 churn，疑似是額度快速消耗的主因。`main.py`（`_run_background_checks()` 統一建立單一 `CloudSQLClient()` 共用傳給 14 個 `_check_*(db)`，跑完才統一關閉一次；14 個函式簽名改為接受 `db` 參數）已異動。`tests/test_main.py` 全面更新（14 個函式測試改傳共用 `fake_db`），新增 `test_healthz_dispatches_all_checks_via_background_thread`（驗證共用同一個 db）與 `test_healthz_skips_all_checks_when_database_url_missing`。`tests/test_main.py` 35 passed，`ruff check main.py tests/test_main.py` 全過。根因排查見 `docs/ADR/debug/infra.md`（新檔案）2026-08-24 條目。CU-hours 是否明顯回落尚待 Robin 下週觀察 Neon 用量曲線。 |
| 🎯 目標追蹤體態摘要改綜合評估（FR-45a 補充） | 完成（已 commit `44faef1`，尚未 push／部署） | 不需 Migration。起因：Robin 反饋「體態目標摘要應該像教練一樣綜合飲食和運動紀錄評估，不能只看體重」；追問後定案只有 `goal_type == "weight"` 的目標才同時參考體重／運動／飲食三項近期紀錄，`exercise`／飲食型目標維持只看自己那一種紀錄。`src/services/goal_summary_job.py`（`_gather_body_activity_text()` 拆成 `_weight_text()`／`_exercise_text()`／`_diet_text()`，weight 型目標組合三者）已異動。新增 `tests/services/test_goal_summary_job.py` 3 項測試（分別驗證三種 `goal_type` 各自撈到的資料範圍）。`tests/services/test_goal_summary_job.py` 10 passed，`ruff check` 全過。決策脈絡見 `docs/ADR/discuss/robinson.md` 2026-08-24 補充條目。 |
| Telegram「職缺清單」加縣市篩選＋排版改版（FR-41g） | 完成（已 commit `44faef1`，尚未 push／部署） | 不需 Migration。Robin 要求點擊「職缺清單」先選縣市（全台 22 縣市＋「不限」），選定後才顯示職缺；排版改為每筆用分隔線包起來，第一行「公司名稱 | 地區」、第二行「職缺名稱（ID=...，分數：...）」。`src/bot/job_settings.py`（新增 `start_jobs_region_menu()`、`start_jobs_list()` 新增 `region` 參數）、`src/bot/job_search.py`（新增 `get_companies_by_id_map()`）、`src/bot/router.py`（`jobs:region:*` 分派，`jobs:page:*` 舊版相容）已異動。新增 `tests/bot/test_job_settings.py` 7 項測試。`tests/bot` 全部 1131 passed（另有 4 項既有 `test_job_search.py` 失敗屬本次雲端沙盒暫存快取版本較舊，與本次改動無關，非回歸範圍），`ruff check` 全過。決策脈絡見 `docs/ADR/discuss/job-search.md` 2026-08-24 補充條目。 |
| Mobile App「逾期待辦」補抓已自動過期事項＋按鈕難點擊修正 | 完成（已 commit `965755f`，尚未 push／部署） | 不需 Migration。起因：Robin 回報一筆代辦事項到期後 Mobile App 完全看不到；排查發現 `mark_overdue_as_expired()` 約每 10 分鐘就把過期 `pending` 轉成 `expired`，而 `src/services/app_analytics.py` 的 `todos()` 方法 `overdue_items`／`calendar_counts` 查詢都寫死只抓 `status='pending'`，導致逾期待辦幾乎永遠是空的。`src/services/app_analytics.py`（`overdue_items`／`calendar_counts` 篩選改為 `status IN ('pending', 'expired')`，`items`／即將到期清單不動）已異動。新增 `tests/services/test_app_analytics.py::test_todos_overdue_and_calendar_counts_include_auto_expired_items`；`pytest tests/services/test_app_analytics.py -q` 39 passed，`ruff check .` 對本次異動檔案全過。已確認 `update_record()` 標記完成／取消對 `expired` 待辦本來就能正常運作。**2026-08-24 續**：push 後 Robin 實機測試回報同一筆到期日為當天的待辦仍看不到，且逾期待辦按鈕難點擊；追查發現 `overdue_items` 查詢還留著多餘的「到期日 < 今天」限制，改成 `status = 'expired'` 直接算逾期、`pending` 才用日期判斷；`mobile/app/analytics/[module].tsx` 的 `recordActions`／`recordButton` 加上 `flexWrap`、加大觸控熱區。新增 `test_todos_overdue_shows_expired_item_due_today_even_though_date_is_not_before_today`；`pytest tests/services/test_app_analytics.py -q` 42 passed。根因排查見 `docs/ADR/debug/todo.md`（新檔案）2026-08-24 及續篇條目。實際效果尚待 Robin push 後在正式環境／Mobile App 實機確認。 |
| TOEIC 聽力題目庫改版（FR-25b／FR-27 修正）——`_cutoff` 整包音檔切割、解答照片統一驅動、聽力題禁止顯示文字 | 完成（已 commit `387eb66`，尚未 push／部署） | 新增 migration `0099_make_certificate_questions_image_nullable.sql`（`certificate_questions.image_gdrive_url` 改 nullable）。起因：Robin 打算直接上傳整份 ~45 分鐘聽力錄音，但既有整包切割邏輯假設「1 題=1 段獨立音檔」，不適用共用音檔的 Part 3/4；經多輪對話釐清後定案只自動切 Part 1+2；過程中發現 Part 2 沒有印刷內容可拍照，既有「一定要有題目照片才能建題」設計會讓 Part 2 永遠無法建題，且若 fallback 用解答照片充當題目圖會在作答前洩題；最終定案聽力題內容全部改由解答照片統一驅動，題目照片改選填僅供顯示，並修正呈現邏輯讓聽力題完全不顯示文字（只顯示圖片/音檔），閱讀題不受影響。`src/bot/toeic.py`（`_FILENAME_PATTERN` 新增選填 `cutoff` 群組、`_split_whole_audio()` 支援裁切、新增 `_LISTEN_ANSWER_VISION_PARSE_PROMPT`／`_process_listen_questions()` 一階段建題、`_process_answer_keys()` 限縮為只處理 write）、`src/bot/certificate_answer.py`（`_build_certificate_question_view()` 依 `question_type` 分流顯示邏輯）已異動。新增／改寫多項測試，`pytest tests/bot/test_toeic.py tests/bot/test_certificate_answer.py -q` 85 passed，`ruff check` 對本次異動四個程式檔全過。同步更新 `docs/specs/SPEC.md`（FR-25／FR-25b／FR-27）、`docs/reference/db_schema.md`、`docs/ADR/discuss/skill-growth.md`（新增 ADR-32）。實際效果尚待 Robin 上傳真實錄音／照片並在正式環境／Telegram 實機驗收。 |
| Telegram 每日 08:00 待辦摘要漏推「預定時間早於 08:00」的事項 | 完成（已 commit `0a9719b`，尚未 push／部署） | 不需 Migration。起因：Robin 把一筆待辦到期時間改成當天 07:30，隔天沒收到 08:00 摘要推播；一開始誤判為使用者自己標記 `completed` 才沒推播，Robin 確認 07:30／08:00 當下其實還是 `pending`；排查發現 `mark_overdue_as_expired()` 跟 `check_and_push_daily_digest()` 都借用同一個 `/healthz`（約 10 分鐘一次）排程，只要預定時間早於 08:00，08:00 那次摘要執行前的某次 `/healthz` 就已經把它從 `pending` 轉成 `expired`，而摘要查詢只認 `status='pending'`，導致這筆永遠不會被推播——跟 2026-08-24 Mobile App「逾期待辦」看不到已過期事項是同一個根因模式，只是這次發生在 Telegram 推播。`src/bot/todo.py`（`check_and_push_daily_digest()` 查詢改成 `status IN ('pending', 'expired')`）已異動；`tests/bot/conftest.py` 的 `FakeCloudSQLClient._matches()` 同步更新對應 SQL 字串比對。新增 `tests/bot/test_todo.py::test_check_and_push_daily_digest_includes_item_already_auto_expired_earlier_today`、`test_check_and_push_daily_digest_still_excludes_completed_and_cancelled`；`pytest tests/bot/test_todo.py -q` 29 passed，全專案 `pytest tests/bot -q` 1142 passed（另有 4 項既有 `test_job_search.py` 失敗屬雲端沙盒暫存快取版本較舊，與本次改動無關，非回歸範圍），`ruff check` 對本次異動三個檔案全過。根因排查見 `docs/ADR/debug/todo.md` 2026-08-26 條目。實際效果尚待 Robin push 後在正式環境觀察下一筆預定時間早於 08:00 的待辦是否能正常收到摘要推播。 |
| Neon compute CU-hours 本月超額（101.28／100） | 決策完成，無程式碼異動（文件記錄已 commit `58c0827`／`79c0512`／`77e221d`） | 不需 Migration。8/24 才部署過連線共用修復（`dc1e50c`），兩天後用量依然打滿；請 Robin 到 Neon 後台截圖確認後，找到真正主因是 Free 方案鎖死 5 分鐘 Autosuspend delay，跟 `/healthz` 10 分鐘觸發頻率疊加，導致 compute 一天約一半時間都在被計費「活躍」，跟連線數／查詢量幾乎無關；8/24 那次修復方向正確但沒有觸及主要成本來源。跟 Robin 討論「升級付費方案維持即時性」vs.「不花錢但接受提醒變慢」的取捨後，Robin 選擇後者，改為由 Robin 自行到 cron-job.org 後台拉長 `/healthz` 觸發間隔（外部排程設定，非本專案程式碼，不需要 commit 或部署）；cron-job.org 介面沒有 25 分鐘選項，且考量家人即將加入使用、真實流量會成長的不確定性，Robin 最終定案採用 **30 分鐘**（`_REMINDER_WINDOW` 剛好等於 30 分鐘、無安全緩衝，屬已知取捨；15 分鐘雖緩衝較大但 31 天長月下用量緩衝空間較小，優先保守處理未知的家人使用量）。根因修正說明見 `docs/ADR/debug/infra.md` 2026-08-26 續篇條目；決策、31 天用量估算與後果見 `docs/ADR/discuss/infra.md`（新檔案）2026-08-26 條目。待 Robin 實際調整後觀察下個月用量曲線（含家人加入後的成長幅度）與各項排程通知的實際延遲是否在可接受範圍。 |
| Render 免費方案 750 小時 instance hours 本月逼近上限（710／750），cronjob 因連續 503 被自動停用 | 完成，無程式碼異動 | 不需 Migration。9/1 Robin 收到 Render 逼近額度信與 cron-job.org 因連續 26 次 503 自動停用信；排查發現跟 8/26 Neon 事件是同一個根因模式撞上 Render 自己的獨立額度——Render 免費方案閒置約 15 分鐘才會休眠，`/healthz` 原本 10 分鐘觸發一次的頻率讓服務幾乎整月保持醒著，逼近 750 小時上限；打滿後 Render 直接整月停權（非計費消耗），導致 cron-job.org 連續收到 503 被自動停用。經 Render Dashboard 與瀏覽器直接觸發 `/healthz` 確認服務程式碼本身正常（deploy 為 Live、能正常冷啟動回應），只是休眠中沒有請求喚醒。Robin 已到 cron-job.org 重新啟用該 cronjob（間隔維持 8/26 決定的 30 分鐘不變，同一個調整同時緩解 Neon／Render 兩邊問題），並額外開啟「單次失敗即通知」設定（先前只在完全停用時才通知，導致 8/31 18:00 起近 5 小時完全狀況外）。根因排查見 `docs/ADR/debug/infra.md` 2026-09-01 續二條目，明確結論「機率大幅降低但非保證不再發生」，需持續觀察家人加入使用後的用量成長。 |
| Render 30 分鐘間隔重新啟用後仍零星 503，發現「不休眠」與「不超額」互斥 | 決策完成，無程式碼異動；**2026-09-05 已被下一列取代（方向 A → 方向 C）** | 不需 Migration。重新啟用後 Robin 回報 cron-job.org 仍持續零星 503；排查發現 `/healthz` 原始設計初衷就是「用高頻率觸發讓 Render 別休眠」，30 分鐘已超過 Render 約 15 分鐘休眠門檻，服務真的會時睡時醒，喚醒過程偶爾失敗；評估重試機制（不可行，容器未啟動前程式碼介入不了）與拉長 cron-job.org timeout（免費方案鎖死最大 30 秒，改不動）皆無法解決，確認「不休眠」與「不超過 750 小時／月」在 Render 免費方案上互斥、無中間值。與 Robin 討論方向 A（接受偶爾冷啟動失敗）／B（拉短間隔、接受再次逼近額度風險）／C（升級付費方案徹底解決）後，Robin 當時定案方向 A，並把 cron-job.org 失敗通知門檻從 1 次調高為 5 次。決策與後果見 `docs/ADR/discuss/infra.md` 2026-09-01 條目（現已標記 superseded）；技術排查見 `docs/ADR/debug/infra.md` 2026-09-01 續三條目。 |
| Render 方向 A 被推翻，改採方向 C——升級 Render Web Service 為付費 Starter 方案（$7/月） | 完成（Render Dashboard 操作，非程式碼異動，不需 commit／push） | 不需 Migration。cronjob 在同一週內第二次因連續失敗被自動停用（非單次失敗通知），Robin 認為此代價已超出可接受範圍（家人即將依賴此 Bot／App），改為升級 Render Instance Type，從 Free 升級為 **Starter（$7/月，0.5 CPU／512 MB RAM）**；升級過程中因未綁定付款卡片一度失敗（`Plan requires payment information on file`），Robin 加卡後重試成功，Render Dashboard 確認 Compute plan updated、服務重新部署為 Live。**`/healthz` 觸發間隔維持 30 分鐘不變**——Render 升級只解除 Render 側「不休眠／不超額」互斥，完全不影響 Neon 側額度限制（Neon 目前仍免費，10 分鐘頻率會撞上 CU-hours 上限），故不會改回 10 分鐘。Neon→Render Postgres 資料庫搬家已與 Robin 討論但明確表示屬未來大工程、本次先擱置、不需要文件細節，僅記錄「已有共識、待未來另外規劃」。決策脈絡見 `docs/ADR/discuss/infra.md` 2026-09-05 條目。 |
| 「開始作答」入口修正：移至主選單、修文字回覆路由缺口、跨證照標示 | 完成 | 不需 Migration。Robin 回報回覆推播訊息承諾的「開始作答」沒有進入作答流程，排查發現 `router.py::handle_message()` 完全沒有涵蓋這句文字，會掉進一般聊天；改用按鈕時進一步發現按鈕藏在「考試設定→每日題數設定→選證照」很深的路徑，且該按鈕實際上不分證照、一次清完當天所有待答題目，放在單一證照頁面底下本身就誤導。三項一併修正：①主選單新增獨立項目「▶️ 開始作答」（`menu.py`），移除原本藏在深處的同名按鈕與對應 callback；②補上文字觸發詞「開始作答」；③作答畫面新增證照類型標示（「📝【證照類型】第 N/總題數 題」），解決跨證照切換看不出目前科目的問題。`src/bot/menu.py`、`src/bot/router.py`、`src/bot/certificate_settings.py`、`src/bot/certificate_answer.py`、`src/bot/commands.py` 已異動，`tests/bot/test_router.py` 同步更新／新增測試。`pytest tests/bot -q` 1136 passed（另有 4 項既有 `test_job_search.py` 失敗屬雲端沙盒暫存快取版本較舊，與本次改動無關），`ruff check` 全過。`docs/specs/SPEC.md` FR-27 同步更新。決策脈絡見 `docs/ADR/discuss/robinson.md` 2026-09-06 條目。 |
| 待辦事項前置提醒視窗（`_REMINDER_WINDOW`）由 30 分鐘放寬為 40 分鐘 | 完成（已 commit `85923bc`，尚未 push） | 不需 Migration。Robin 追問「30 分鐘頻率會不會漏推提醒」，確認 8/26 已知取捨依然存在：視窗＝觸發頻率＝30 分鐘，零緩衝，實際觸發間隔一旦超過 30 分鐘就可能漏推事前提醒。`src/bot/todo.py`（`_REMINDER_WINDOW` 改為 `timedelta(minutes=40)`，換取 10 分鐘容錯緩衝；`check_and_push_reminders()` 原本寫死「30 分鐘」的提醒文字改為依實際剩餘分鐘數動態組字）已異動。`tests/bot/test_todo.py::test_check_and_push_reminders_range_todo_anchors_on_start_at` 斷言同步更新（原本斷言的「30 分鐘」本來就跟測試情境的實際 20 分鐘不符，屬順帶修正）。`pytest tests/bot -q` 1135 passed（另有 4 項既有 `test_job_search.py` 失敗屬雲端沙盒暫存快取版本較舊，與本次改動無關，非回歸範圍），`ruff check` 對本次異動檔案全過。`docs/specs/SPEC.md` FR-31b／FR-32 同步更新為「前 40 分鐘內提醒」。決策脈絡見 `docs/ADR/discuss/infra.md` 2026-09-05 續條目。 |

## 目前修復中

| 日期 | 範圍 | 問題／處理 | 開發者 | 狀態 | 驗證 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-18 | Migration `0084`～`0094` | `0025` 已建立 `exercise_logs.note`，未套用的 `0084` 又執行 `ADD COLUMN note`，Render 啟動 migration 因 `DuplicateColumn` 中斷，導致 `module_goals` 等後續資料表不存在、`0094` 取消功能資料表也未刪除。已移除 0084 的重複加欄並補回歸測試。 | Codex | 完成（已 push／部署） | commit `07e986a`、文件 commit `b67cce0`。RED：聚焦測試 1 failed；GREEN：聚焦測試 1 passed。全專案 `pytest -q`：1823 passed、1 項第三方 `pydub` warning；`ruff check .`、`git diff --check` 通過。Render 於 12:25 明確記錄 0084～0094 共 11 筆全數完成，服務正常啟動。 |

## 歷史時程與任務紀錄

> 以下「狀態」與「待」敘述是各條目建立當時的歷史快照；若與上方「目前有效進度」不同，以上方為準。

| 日期 | 對應 FR | 任務內容 | 開發者 | 狀態 | 備註 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-23 | FR-65a | 發現 Mobile App 帳密登入無錯誤次數限制，`user_id` 又是可預測序號（`user01`、`user02`...），存在無限次密碼嘗試風險；與 Robin 討論後定案「連續錯誤 2 次即鎖定，僅 Owner 於 Telegram 手動解鎖，不自動過期」，並確認 Owner 身分綁定 Telegram、與 Mobile 密碼無關，Robin 自己被鎖也能自救；Robin 明確接受「惡意鎖定」副作用的 tradeoff | Claude | 完成（已 commit `cb65652`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 新增 migration `0098`。詳見上方「目前有效進度」列與 `docs/ADR/discuss/mobile-app.md` 2026-08-23 條目。 |
| 2026-08-23 | FR-65a 補充 | Robin 追問「家人帳號被鎖，是不是只能等對方主動講」，確認原設計確實是被動；建議並經同意改為鎖定觸發當下主動用 Telegram 私訊通知 Owner，取代原「不做鎖定通知」決策（該點標記 superseded） | Claude | 完成（已 commit `cb65652`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | `login()` 新增可選 `notify_owner_locked` 回呼，僅在觸發鎖定當下呼叫且吞掉通知本身失敗，不影響登入錯誤回應；不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/mobile-app.md` 2026-08-23 續篇條目。 |
| 2026-08-24 | FR-41c 補登 | 發現 FR-41c（多地區、清單顯示、編輯功能，commit `07adf1f`）從未寫入 `SPEC.md`，違反已上線需求須有正式規格的原則，補上正式規格條目 | Claude | 完成（文件修正，無程式碼異動） | 詳見上方「目前有效進度」列。 |
| 2026-08-24 | FR-41d | Robin 回報 Telegram「求職設定→職缺清單」點擊完全沒反應；排查發現訊息無分頁機制、職缺累積後超過 Telegram 4096 字元上限被拒收，且 `webhook.py` 既有「送出失敗只記 log」防護網讓失敗對使用者不可見；與 Robin 討論後定案改為分頁按鈕（上一頁／下一頁） | Claude | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/job-search.md` 2026-08-24「職缺清單訊息過長打不開」條目。 |
| 2026-08-24 | FR-41e | Robin 回報 Mobile App「推薦職缺」全部顯示「一分」且包含明顯不相關職缺，要求「找不到合適的就不要硬推薦」；排查一開始誤判為 `GEMINI_API_JOB_SEARCH_KEY` 未設定，Robin 事後確認該金鑰早已設定、變數名稱比對無誤，修正根因為公司背景資料（`job_companies.background`）尚未回填導致 `list_scorable_jobs()` 空清單、FR-37 評分從未真正執行過、`score` 恆為 NULL；推薦清單原本也沒有任何分數門檻；與 Robin 討論後定案新增 60 分門檻，無符合項目時顯示「目前沒有符合的推薦職缺」 | Claude | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/job-search.md` 2026-08-24「推薦職缺不分青紅皂白」條目（已修正根因）。評分要真正運作，尚待 Robin 透過 FR-35 協作流程回填公司背景資料。 |
| 2026-08-24 | FR-41f | Robin 提供 Render 正式環境錯誤 log，發現週排程爬蟲遇 104 429 限流時，`fetch_job_detail()` 重試耗盡後例外炸穿整個 `crawl_and_upsert_jobs()`，讓當次排程後面所有還沒爬的關鍵字／分頁全部被跳過，是「只爬到 10 個職缺」的另一半成因；與 Robin 討論後定案改成單筆容錯（略過該筆記 log，不整批中斷），不調整共用重試模組的延遲秒數 | Claude | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/job-search.md` 2026-08-24「週排程爬蟲遇 104 429 限流，整批中斷」條目。 |
| 2026-08-24 | 寄信改走 SendGrid API | Robin 提供 Render 正式環境錯誤 log，發現寄信全面失效（`Network is unreachable`）；查證 Render 官方 changelog 確認免費方案封鎖對外 SMTP 埠 25／465／587，且需付費才能解除；Robin 明確表示不想付費，改走 Email API；比較 Resend（需驗證自有網域，Robin 沒有網域，否決）與 SendGrid（Single Sender Verification 免網域），選定 SendGrid；Robin 完成帳號設定並貼上 `SENDGRID_API_KEY` 後動工 | Claude | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/submodules-core.md`、`docs/ADR/debug/job-search.md` 對應日期條目。 |
| 2026-08-24 | TOEIC 單字題節流退避 | Robin 提供 Render 錯誤 log 反映 TOEIC 單字題生成撞本地端節流保護；排查發現撞到節流時直接放棄、不等待，導致嘗試機會瞬間燒光；與 Robin 討論後定案改成等待後重試、不消耗嘗試次數 | Claude | 完成（已 commit `179e068`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/skill-growth.md`（新檔案）對應日期條目。 |
| 2026-08-24 | FR-35 修正 | Robin 追問「之前沒收到過新公司列表信，不是 Email 功能壞掉嗎」，排查發現寄信失敗會拖累整個評分流程、且已存在的舊公司永遠不會被排進未來 CSV，導致背景資料永久卡住；與 Robin 討論後定案改成 CSV 涵蓋所有背景缺漏公司、寄信失敗不中斷評分 | Claude | 完成（已 commit `7c648a1`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/job-search.md` 2026-08-24 續「公司背景 CSV 寄信失敗會拖累整個評分流程、且歷史公司永久卡住」條目。 |
| 2026-08-24 | FR-41d 補充 | Robin 反饋 Telegram 職缺清單排版太擠，要求每筆職缺之間空一行；確認加空行後單頁內容仍遠低於 Telegram 4096 字元上限，不需調整分頁大小 | Claude | 完成（已 commit `126b9dd`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。`7c648a1` 曾誤植 commit message 但實際程式碼未變更，已於 `126b9dd` 補正。詳見上方「目前有效進度」列與 `docs/ADR/debug/job-search.md` 2026-08-24 續「職缺清單排版太擠」條目。 |
| 2026-08-24 | FR-21a | Robin 收到 Neon「compute CU-hours 已用 80%」email 主動反映；排查發現既有 FR-21 監控只涵蓋儲存空間，且 `/healthz` 每次觸發都讓 14 個排程檢查各自開關資料庫連線（一天 2016 次），疑似是額度快速消耗的主因；與 Robin 討論後定案改成共用單一連線 | Claude | 完成（已 commit `dc1e50c`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/infra.md`（新檔案）2026-08-24 條目。 |
| 2026-08-24 | FR-45a 補充 | Robin 反饋體態目標摘要應該綜合飲食和運動紀錄評估，不能只看體重；追問後定案只有體重目標需要跨資料佐證，運動／飲食目標維持只看自己那一種紀錄 | Claude | 完成（已 commit `44faef1`，尚未 push／部署） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/robinson.md` 2026-08-24 補充條目。 |
| 2026-08-24 | FR-41g | Robin 要求職缺清單加上縣市篩選（全台 22 縣市＋不限），並給出具體排版範例（分隔線＋公司名稱＋地區） | Claude | 完成（已 commit `44faef1`，尚未 push／部署） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/job-search.md` 2026-08-24 補充條目。 |
| 2026-08-24 | Mobile App 逾期待辦看不到已過期事項 | Robin 回報代辦到期後 Telegram 有推播但 Mobile App「待辦事項」頁面完全找不到該筆；排查發現 `mark_overdue_as_expired()` 會把過期 `pending` 自動轉成 `expired`，而 `app_analytics.py` 的逾期待辦／月曆計數查詢只抓 `status='pending'`，兩者時間交互從未被檢查過，導致「逾期待辦」形同虛設；與 Robin 討論後定案改為同時納入 `pending` 與 `expired` | Claude | 完成（已 commit `b51c71d`，尚未 push／部署） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/todo.md`（新檔案）2026-08-24 條目。 |
| 2026-08-24 | Mobile App 逾期待辦補抓後 id=4 仍看不到＋編輯按鈕難點擊 | Robin push 並實機測試後回報 id=4（到期日為當天）仍看不到；排查發現 overdue_items 查詢除了 status 還多了「到期日 < 今天」的日期限制，把「今天到期但已 expired」的項目排除在外，是同一個 bug 的第二個獨立成因；另反映逾期待辦彈窗三顆按鈕很難點擊，排查發現 按鈕列沒有允許換行也沒有加大觸控熱區 | Claude | 完成（已 commit `965755f`，尚未 push／部署） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/todo.md` 2026-08-24 續篇條目。 |
| 2026-08-25 | FR-25b／FR-27 修正 | Robin 打算直接上傳整份 TOEIC 聽力錄音，經多輪對話釐清三種上傳情境與 Part 3/4 不適用整包切割後，定案新增 `_cutoff` 檔名後綴只自動切 Part 1+2；過程中發現 Part 2 無題目照片可拍會讓既有「一定要有題目照片才能建題」設計卡死，且 fallback 用解答照片充當題目圖會洩題；最終定案聽力題內容全部改由解答照片統一驅動，題目照片改選填僅供顯示，`image_gdrive_url` 改 nullable，並修正呈現邏輯讓聽力題完全不顯示文字 | Claude | 完成（已 commit `387eb66`，尚未 push／部署） | 新增 migration `0099_make_certificate_questions_image_nullable.sql`。詳見上方「目前有效進度」列與 `docs/ADR/discuss/skill-growth.md` ADR-32。 |
| 2026-08-26 | 待辦事項 | Robin 把待辦到期時間改成當天 07:30 後隔天沒收到 08:00 摘要推播；排查發現 `mark_overdue_as_expired()` 跟 `check_and_push_daily_digest()` 借用同一個 `/healthz` 排程，預定時間早於 08:00 的待辦會在摘要執行前就被自動轉成 `expired`，摘要查詢只認 `pending` 因而永遠漏推 | Claude | 完成（已 commit `0a9719b`，尚未 push／部署） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/debug/todo.md` 2026-08-26 條目。 |
| 2026-08-26 | 基礎設施（Neon） | Robin 收到 Neon 100% compute CU-hours 用完通知；8/24 才部署過連線共用修復仍不夠，經 Neon 後台截圖排查找到真正主因是 Free 方案鎖死 5 分鐘 Autosuspend delay 跟 `/healthz` 10 分鐘頻率疊加；與 Robin 討論花錢升級 vs. 不花錢但降低提醒即時性的取捨，Robin 選擇後者，決定自行調整 cron-job.org 排程頻率為 30 分鐘（介面無 25 分鐘選項） | Claude | 決策完成，無程式碼異動（文件記錄已 commit `58c0827`） | 不需 Migration。詳見上方「目前有效進度」列、`docs/ADR/debug/infra.md` 2026-08-26 續篇條目與 `docs/ADR/discuss/infra.md`（新檔案）2026-08-26 條目。 |
| 2026-08-26 | 基礎設施（Neon）補充 | Robin 追問 15 分鐘／31 天長月是否會超額，以及即將有家人加入使用、真實流量會成長的不確定性；與 Robin 討論後確認 15 分鐘與 30 分鐘在 31 天下都不會超額但緩衝不同，且 30 分鐘零緩衝漏推風險機率極低、影響輕微，Robin 最終維持 30 分鐘、先觀察家人加入後的用量再決定 | Claude | 決策完成，無程式碼異動（文件記錄已 commit `79c0512`／`77e221d`） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/infra.md` 2026-08-26 續二條目。 |
| 2026-09-01 | 基礎設施（Render） | Robin 收到 Render 750 小時額度逼近上限與 cron-job.org 自動停用通知；排查確認跟 Neon 事件同一根因模式；重新啟用 cronjob 後仍零星 503，進一步發現 `/healthz` 原始設計初衷是靠高頻率觸發讓 Render 別休眠，跟 8/26 拉長間隔的決策互相衝突，「不休眠」與「不超額」在免費方案上互斥；評估重試機制與拉長 timeout 皆不可行（cron-job.org 免費方案 timeout 鎖死 30 秒）；Robin 定案接受方向 A（維持 30 分鐘、接受偶爾冷啟動失敗），並調高失敗通知門檻為 5 次 | Claude | 決策完成，無程式碼異動；**2026-09-05 已被方向 C 取代** | 不需 Migration。詳見上方「目前有效進度」列、`docs/ADR/debug/infra.md` 2026-09-01 續二／續三條目與 `docs/ADR/discuss/infra.md` 2026-09-01 條目（現已標記 superseded）。 |
| 2026-09-05 | 基礎設施（Render） | cronjob 在同一週內第二次因連續失敗被自動停用（非單次失敗通知），Robin 認為方向 A 的代價已超出可接受範圍（家人即將依賴此 Bot／App），改為升級 Render Web Service Instance Type，從 Free 升級為 Starter（$7/月，0.5 CPU／512 MB RAM）；升級過程曾因未綁定付款卡片失敗，加卡後重試成功；確認 `/healthz` 間隔仍須維持 30 分鐘不變（Render 升級不影響 Neon 免費方案的額度限制）；Neon→Render Postgres 資料庫搬家已與 Robin 討論但明確擱置為未來工程，本次不記錄細節 | Claude | 完成（Render Dashboard 操作，非程式碼異動，不需 commit／push） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/infra.md` 2026-09-05 條目。 |
| 2026-09-05 | 待辦事項提醒視窗 | Robin 追問 30 分鐘觸發頻率會不會漏推提醒；確認視窗＝頻率零緩衝的已知取捨依然存在，改為放寬 `_REMINDER_WINDOW` 為 40 分鐘、換取 10 分鐘容錯緩衝，並修正原本寫死「30 分鐘」的提醒文字改為動態計算實際剩餘分鐘數 | Claude | 完成（已 commit `85923bc`，尚未 push） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/infra.md` 2026-09-05 續條目。 |
| 2026-09-06 | 「開始作答」入口修正 | Robin 回報回覆推播訊息承諾的「開始作答」掉進一般聊天，排查發現文字路由完全沒有涵蓋這句話；追查按鈕入口發現藏在很深的路徑且不分證照類型；改為主選單新增獨立項目、補上文字觸發詞、作答畫面加上證照類型標示三項一併修正 | Claude | 完成（尚未 commit） | 不需 Migration。詳見上方「目前有效進度」列與 `docs/ADR/discuss/robinson.md` 2026-09-06 條目。 |
| 2026-08-20 | FR-41c | 「職缺關鍵字設定」實機使用後三項調整：①`_JOB_SEARCH_CRITERIA_PARSE_PROMPT` 修正單一技術詞（如「AI」）被誤判 `UNCLEAR` 的問題，追加「單一技術詞/縮寫即視為明確關鍵字」規則②`job_search_criteria.region` 支援逗號分隔多地區，`crawl_and_upsert_jobs()` 比對邏輯改成任一地區符合即算通過（OR）③清單改為同時顯示關鍵字／地區／薪資範圍（新增 `job_search.format_search_criteria()`），並新增「✏️ 編輯」操作（`job_search:criteria:edit:<id>`，新增 `job_search.update_search_criteria()`），走跟新增相同的自然語言整段描述、整筆覆蓋 | Claude | 完成（已 commit `07adf1f`，已 push／部署；Robin 回報 push 後測試無異常，部分需排程時間才能觀察的效果尚待後續驗證） | 不需 Migration。`tests/bot/test_job_settings.py` 新增 6 項測試；全專案 `python3 -m pytest -q`：1602 passed（`tests/migrations/test_migration_sql.py` 1 項因本次雲端沙盒未攜帶完整 `.sql` migration 檔案而失敗，屬環境限制、非本次程式碼問題，未計入回歸範圍）；`ruff check .` 對本次異動檔案全過。`docs/reference/db_schema.md`（`job_search_criteria.region` 格式慣例）已同步；完整互動決策見 `docs/ADR/discuss/job-search.md` 2026-08-18「職缺關鍵字設定支援多地區、清單顯示地區/薪資、新增編輯功能」條目；根因排查見 `docs/ADR/debug/job-search.md`。Prompt 調整效果無法在 Cowork 沙盒對正式 Gemini API 驗證，待 Robin 正式環境實測。 |
| 2026-08-19 | FR-64b～FR-64d | Mobile 分析頁共用基礎與待辦第一批：一般分析支援 1～30 天、體態／記帳共用目標摘要與區間／最新紀錄、圖表 X／Y 軸刻度、未逾期待辦與逾期待辦分流及完成／延期／取消入口 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `28ad29a`。Robin 已回報 push 並完成實機測試；實機發現軸名與目標摘要順序兩項小問題，已於第二批修正。TDD RED：4 failed；GREEN：96 passed；全專案 1798 passed。1 項第三方 warning；`ruff`、typecheck、Web export、`git diff --check` 通過。 |
| 2026-08-19 | FR-64b～FR-64d | Mobile 分析頁第二批：圖表補 X／Y 軸名、目標摘要移至日期篩選上方、體態／飲食／運動頁籤、記帳只留收支比較、心情小記移除圖表並補最近紀錄 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `e667a11`、文件 commit `557ec10`。Robin 已回報 push 並完成實機測試；實機發現首次進入頁面會短暫顯示不完整內容，已納入第三批修正。 |
| 2026-08-19 | FR-64b～FR-64d／FR-73a／FR-76b | Mobile 第三、四批：統一首次載入畫面、收藏目標摘要、Mobile／Telegram 跨端成果置頂與排序 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `83db1ec`、文件 commit `ccfd08a`已 push。Robin 已實機驗收，並回報四個獨立頁缺少載入文案，本批另行修正。 |
| 2026-08-19 | FR-64b～FR-64d | Mobile 分析收尾：四個獨立頁補完整載入畫面；求職分析完成總覽／推薦／應徵頁籤；考試成績完成證照切換、目標進度、練習／弱點／正式成績 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `2f7de66`、文件 commit `99fc3a5`。TDD RED：證照分析契約 1 failed；GREEN：分析 API／Service 62 passed。全專案 `pytest -q`：1806 passed、1 項第三方 warning；`ruff check .`、Mobile typecheck、Web export 通過。本批無 Migration。 |
| 2026-08-19 | 文件治理 | 最終跨頁自動化回歸、現行文件狀態清理及根目錄 README 完整重寫 | Codex | 完成（已 commit／待 push） | commit `37b3345`。`pytest -q`：1806 passed、1 項第三方 `pydub` warning；`ruff check .`、Mobile TypeScript、Expo Web export 通過。README 不含正式網址、Token 或密碼。 |
| 2026-08-19 | FR-64c／FR-72a | Telegram 全目標手動完成：統一體態、飲食、運動、記帳、收藏與考試的完成操作、二次確認、權限檢查及連動事件清理 | Codex | 完成（已 push／部署／實機驗收） | commit `c2b3d50`。Robin 已核准 `0096`，完成 push、正式環境部署與 Telegram 實機驗收。Codex 聚焦測試 100 passed；全專案 1796 passed、1 項第三方 warning；`ruff check .`、`git diff --check` 通過。自動達成仍保留；正式考試分數達標會持久化 achieved，運動可建立累積型或文字里程碑。 |
| 2026-08-18 | FR-64b～FR-64d／FR-76b | 定案 Mobile 分析頁、共用目標摘要、紀錄分區、圖表座標、逾期待辦、體態／記帳／心情、收藏目標、求職／考試頁及跨端成果置頂規格 | Codex | 規格完成／已 push／第一批已開工 | commit `0fad51f`。已由 DRAFT 移入 SPEC；2026-08-19 開始實作共用基礎與待辦第一批。成果置頂如需 Schema 變更，Migration SQL 必須另行審核。 |
| 2026-08-18 | 功能開關 FR-3／FR-30／FR-41b／FR-77 | Telegram 大重構後 Mobile 跨端盤點與相容修正：一般功能忽略舊開關、清除客訴與舊錯誤結案殘留、顯示正式考試備註、區分關閉職缺的推薦與歷史分布 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `fb8c616`、文件 commit `fa9f03c`。TDD RED：聚焦測試 3 failed；GREEN：API／Service 聚焦測試 59 passed。全專案 `pytest -q`：1793 passed、1 項第三方 `pydub` warning；Mobile `tsc --noEmit`、`ruff check .`、`git diff --check` 通過。無 Migration、無資料刪除。 |
| 2026-08-18 | FR-19j～FR-20 | 異常通知、康復通知與 Owner 系統錯誤管理擴充至 Mobile App 事故；新增 Telegram 管理選單、Mobile 5xx 通報、10 分鐘去重、受影響者關聯、處理追蹤與跨平台康復通知 | Codex | 已 push／部署；Telegram 管理頁已實機確認 | commit `005752b`、文件 commit `94eea15` 已在 `origin/main`。Robin 已核准 migration `0095`；Owner 管理頁由 Robin 提供正式 Telegram 截圖確認。移除舊「錯誤ID=N 已處理：…」與 Mobile 結案 API；Mobile 當下只回安全文案且僅通知 Owner。Codex 聚焦測試 332 passed；全專案 `pytest -q`：1791 passed、1 項第三方 `pydub` warning；`ruff check .`、`git diff --check` 通過。Mobile 真實 5xx 未刻意於正式環境製造事故。 |
| 2026-08-18 | FR-6a／FR-6b／FR-51～FR-53 | 移除最後五個 Slash Command：`/rule`、`/my_toggles`、`/set_toggle`、`/set_family_birthday`、`/friend_chat`；同步刪除舊版本人／代管功能開關與家人生日文字狀態機，保留對應選單與「陪我聊聊」自然語言入口 | Codex | 完成（已 push／部署／實機驗收） | commit `759fbf5`、文件 commit `6ceed9d`。聚焦 Router／Commands 測試 206 passed；全專案 `pytest -q`：1785 passed、1 項第三方 `pydub` warning；`ruff check .` 與 `git diff --check` 通過。Robin 已回報 push 並完成全部實機測試。 |
| 2026-08-18 | FR-6c／FR-77 | 功能模式 10 分鐘逾時、草稿 30 分鐘保護、跨功能三選一、草稿恢復二選一與固定別名選單導引；移除客訴、持久化知識庫、逐則對話與長摘要的執行程式、Mobile 分析入口及相關測試 | Codex | 完成（已 push／部署／實機驗收） | commit `1601f34`。Codex 全專案 `pytest -q`：1822 passed、1 項第三方 `pydub` warning；`ruff check .`、`git diff --check` 通過，Robin 本機亦回報測試通過。正式盤點：`complaints` 0 筆、`knowledge_base` 5 筆、`conversation_logs` 180 筆、`conversation_summaries` 1 筆，均僅外鍵指向 `users.id`。Robin 已二次核准 `0094_drop_cancelled_chat_tables.sql`，並明確決定不留備份、直接刪除；舊 migration 保留，`0094` 不使用 `CASCADE`。 |
| 2026-08-18 | 一般對話 FR-1～FR-17 | 一般對話縮限與媒體防呆：改為不落地的 10 分鐘短期上下文；停止正式路由的知識庫、逐則對話與長摘要讀寫；圖片依說明處理或預設整理；語音／音檔先確認轉錄；長按語音超時鎖定改為 5 分鐘並取消 15 分鐘修正限制；音檔不限時；影片及其他檔案統一拒絕 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `5c0c093`、文件 commit `e78b01c`（2026-08-18）。Codex 全專案 `pytest -q`：1849 passed、19 skipped、1 項第三方 `pydub` warning；Robin 已完成 push 與 Telegram 實機驗收，結果正常。19 項 skip 為已取消的舊知識／清除對話流程測試。三張舊資料表的 DROP 尚未建立，須完成正式資料量盤點並取得 Robin 二次核准；固定拒絕文案為「我只能處理對話框文字、語音、圖片和音檔喔！」 |
| 2026-08-18 | FR-1～FR-4a／FR-6e～FR-6g／FR-20a／FR-72a／FR-74b | 功能開關與排程設定選單化：角色分流、三項 Owner 功能開關、個人通知開關、唯讀系統工作、統一重要日子／目標／旅遊日期發送器，並移除未記帳與未完成考題催促 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `669accc`、文件 commit `fe5f828`（2026-08-18）。Robin 已回報 push 並完成 Telegram 實機測試，結果正常；未另行回報 Render 部署狀態。新增 `schedule_settings.py`、`scheduled_notifications.py`、migration `0093` 與對應測試；關閉通知不停止背景工作，關閉功能則停止整個功能。Codex `pytest -q`：1918 passed（1 項第三方 warning）；`ruff check .` 與 `git diff --check` 全數通過。 |
| 2026-08-18 | FR-19k／FR-20 | 系統事故收件與康復通知選單化：事故及 Robin Telegram→Email 備援送達狀態落地，Owner 先選事故、再勾選實際收過事故通知的家人，預覽後二次確認發送 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `e761deb`、文件 commit `92dc623`（2026-08-18）。Robin 已回報 push 並完成 Telegram 實機測試，結果正常；未另行回報 Render 部署狀態。 |
| 2026-08-18 | FR-24／FR-26／FR-30a～FR-30b／FR-6e | 考試設定選單化：主選單改名、證照名冊、目標／每日題數／正式考試紀錄四個子選單；TOEIC 固定三軌題數、非 TOEIC 尚無題庫提示、區間覆蓋不可重疊、正式成績補充內容 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `20fd6c7`（2026-08-18）；文件 commit `bde3731`。Robin 已回報 push 並完成 Telegram 實機測試，結果正常。見 `docs/ADR/discuss/skill-growth.md` 2026-08-18 ADR-31。全專案 `pytest -q`：1921 passed（1 項第三方 `pydub` deprecation warning）；`ruff check .` 與 `git diff --check` 全數通過。 |
| 2026-08-18 | 求職 FR-41／FR-41a | 「💼 求職分析」改為「💼 求職設定」並接上 `job_search:*` 選單：履歷／期望工作內容獨立編輯與二次確認清空、必要條件三欄位分段設定、職缺關鍵字新增與二次確認刪除、依分數排序的唯讀職缺清單、已應徵／面試／Offer 清單與四種狀態切換、全部職缺的人工關閉／重新開啟，以及既有其他平台職缺流程改由按鈕進入；移除舊 Slash Command、文字觸發詞與 `ID=...職缺...` 文字狀態更新。新增 migration `0090_add_job_posting_manual_closed_override.sql`，人工關閉覆寫旗標為 TRUE 時，週爬蟲不覆寫 `is_closed` | Codex | 完成（已推版／實機驗收） | commit `2c5da38`（2026-08-18）；Robin 已完成 push，Render 已隨 push 部署，並完成 Telegram 實機驗收且結果正常。Robin 於 2026-08-18 本機執行 `pytest -q`：1922 passed（僅 1 項第三方 `pydub` deprecation warning）；`ruff check .`：全數通過。求職相關測試：250 passed。DB Schema Reference 已同步；完整互動決策見 `docs/ADR/discuss/job-search.md` 2026-08-18 補充段落。 |
| 2026-08-18 | FR-5／FR-6e／FR-57a | 兩項 Robin 直接核准的變更：①「使用規則」文字改為 Robin 逐字核准的最終版本（`src/bot/templates.py` `APPENDIX_A_TEXT`，隱私承諾「聊天記錄」改「日常紀錄」）②主選單「💡 Youtube 技術分享設定」（原「💡 技術分享」）從 `_NOT_YET_IMPLEMENTED_KEYS` 移除，接上新的 `youtube_settings:*` 子選單（`src/bot/commands.py`／`src/bot/router.py`），比照 `collections.py`／`achievements.py` 單層選單＋按鈕式二次確認刪除模式；主題數量上限 `youtube.MAX_TOPICS`＝5（達上限隱藏「➕ 新增主題」按鈕＋`add_topic()` 內同步擋下雙重保護），移除改「選主題→✅ 確認移除／❌ 取消」二次確認才真正刪除；舊文字觸發詞（`/my_youtube_topics`／`/add_youtube_topic`／`/remove_youtube_topic` 及中文別名）與對應舊處理函式全數移除 | Claude | 完成（已 push／部署） | commit `aa240e9`；已由 `origin/main` 確認 push；完整設計內容見 `docs/ADR/discuss/youtube-intel.md` 2026-08-18「`tech_intel` 主選單按鈕接上 YouTube 主題設定子選單」條目、`docs/ADR/discuss/robinson.md` 2026-08-18「「使用規則」文字模板由 Robin 逐字稿核准＋「技術分享」選單更名接上 YouTube 主題訂閱設定」條目；改寫／新增 `tests/bot/test_templates.py`（逐字比對新版 `APPENDIX_A_TEXT`）、`tests/bot/test_youtube.py`（`add_topic()` 新增 `limit_reached` 欄位斷言、新增 `test_add_topic_limit_reached`）、`tests/bot/test_youtube_topic_commands.py`（整份改寫測新函式）、`tests/bot/test_router.py`（移除 3 項測舊文字觸發詞的過時測試，新增 3 項測 `menu:tech_intel`／`youtube_settings:*` callback 流程的整合測試）；Robin 本機執行 `ruff check .`（本次異動檔案）全過、`pytest -q` 首輪 18 failed（3 項為測試舊文字觸發詞的過時測試，因該行為本批已刻意移除而觸發下游 fallback 邏輯噴錯、非既有回歸；其餘 15 項為 `test_templates.py`／`test_youtube.py`／`test_youtube_topic_commands.py` 未同步本次文字與函式異動），改寫測試後第二輪 2 failed（`test_router.py` 2 項新增測試自身斷言誤把 tuple 回傳值當字串比對、誤判移除清單文字在訊息本文而非按鈕文字），修正後**全數通過**；`docs/reference/` 未異動（本批未變更 DB Schema／API，`youtube_topics` 資料表結構不變）|
| 2026-08-18 | FR-9c／FR-9d | 批次4「🔍 資料查詢」實作完成：新增 `src/bot/query.py`，直接複用 Mobile App 既有 `AppAnalyticsService` 各模組唯讀查詢方法，不重寫查詢邏輯；可查範圍限定 7 個有日期區間概念的模組（待辦／體態分析／記帳／心情／技術分享／求職分析／考試成績），重要日子／收藏與旅遊／成果展示／目標追蹤維持只能從各自主選單查看；流程為選最終日期（快速按鈕「今天」「昨天」，或打字走 LLM 判斷 CLEAR／UNCLEAR，明確允許未來日期）→ 系統自動往前推 6 天組出最多 7 個曆日區間 → 模組複選 →「🔍 開始查詢」；查詢結果逐日列出區間內全部日期，沒有紀錄的日子顯示「查無紀錄」，每筆紀錄的欄位不寫死固定樣板改依實際欄位動態呈現；多模組查詢依模組分則 Telegram 訊息送出（避開 4096 字元上限），沒有 `telegram_client` 時優雅降級成合併一則訊息；`privacy_mask_enabled=True` 時把數字欄位逐位替換成 `*`；`menu.py` 把 `query` 移出 `_NOT_YET_IMPLEMENTED_KEYS`，新增 `QUERY_MODULES`；`router.py` 新增 `menu:query`／`query:*` 分派與 `pending_query_date` 文字流程分派 | Claude | 完成（已 push／部署） | 完整設計內容與使用者確認脈絡見 `docs/ADR/discuss/robinson.md` 2026-08-18「批次4『🔍 資料查詢』開工前 SDD 計畫確認」；沿用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路）；完整 `python3 -m pytest -q`：**1912 個測試全過**（原 1897 個 baseline 全過，新增 15 個：`tests/bot/test_query.py` 全新 15 項；另 `tests/bot/test_menu.py` 新增 1 項、`tests/bot/test_router.py` 既有 2 項斷言隨規格變動改寫）；`ruff check .` 對本次異動檔案全過（既有 `tests/services/test_app_life_exploration.py` 14 項 E701/E702 是本批之前就存在的既有技術債，非本次異動範圍）；`docs/reference/` 未異動（本批未變更 DB Schema／API，純複用既有 `AppAnalyticsService`）；commit `21f5131`，已由 `origin/main` 確認 push |
| 2026-08-18 | FR-41～FR-44 | 批次5「💰 記帳」按鈕化＋摘要確認實作完成：日常紀錄五個子項目（心情／運動／飲食／體態／記帳）至此全數改版完畢，`_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS` 清空。子選單 `commands.start_finance_menu()`（設定預算／新增記帳／補記記帳／我的記帳紀錄／我的記帳摘要／🎯 目標／🔙 返回）；新增／補記記帳的 type→category→amount→note 四輪反問後改為先組摘要（類型／分類／金額／備註／日期）＋「✅ 確認送出」／「❌ 取消」按鈕，`finance:confirm_save` 才真正寫入 `transactions`（取代原本 note 步驟直接寫入）；「我的記帳紀錄」改按鈕式清單（每筆「✏️ 編輯」`finance:edit:<id>`／「🗑 刪除」`finance:delete:<id>`，刪除走二次確認按鈕重新驗證擁有者），取代原本「輸入編號→LLM 分類更新或刪除→LLM CONFIRM/CANCEL」三段式文字流程；預算月份覆蓋確認（全局預設／某幾個月覆蓋值）從自由文字 LLM CONFIRM/CANCEL 改成 ✅ 確認覆蓋／❌ 取消按鈕（`finance:budget_confirm_save`／`finance:budget_override_confirm_save`）；移除全部 7 組舊文字觸發詞常數（`_FINANCE_SET_BUDGET_TRIGGERS` 等），目標入口併入子選單「🎯 目標」按鈕沿用批次3既有 `_dispatch_module_goal_callback()`；記帳分類／類型／幣別與 `finance.py` 純邏輯層本批未異動 | Claude | 完成（已 push／部署） | 完整設計內容與使用者確認脈絡見 `docs/ADR/discuss/robinson.md` 2026-08-18「批次5『💰 記帳』按鈕化＋摘要確認開工前 SDD 計畫確認」；沿用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路）；完整 `python3 -m pytest -q`：**1913 個測試全過**（原 1912 個 baseline，`tests/bot/test_commands.py`／`tests/bot/test_router.py`／`tests/bot/test_menu.py` 既有記帳相關測試改寫成按鈕/確認流程斷言，`tests/bot/test_goal_tracking_router.py` 三項記帳目標文字觸發詞測試改成 `finance:goal:new` callback 觸發，淨增 1 項新選單快照測試）；`ruff check .` 對本次異動檔案全過（既有 `tests/services/test_app_life_exploration.py` 14 項 E701/E702 是既有技術債，非本次異動範圍）；`docs/reference/` 未異動（本批未變更 DB Schema／API）；commit `977a880`（10 files changed, 522 insertions/383 deletions），已由 `origin/main` 確認 push |
| 2026-08-17 | FR-41b／FR-73a／FR-48／FR-24a | 批次3補做「不得漏做的三項功能」：①記帳／收藏清單目標補上 Google Calendar 同步問句——`module_goals` 新增 `sync_to_calendar`／`google_calendar_event_id` 欄位（migration 0088），`goals.py` 新增 `set_calendar_event_id()`，`commands.py` 新增 `handle_module_goal_calendar_sync_step()`（比照 `body.py` 既有 `handle_goal_calendar_sync_step()`），`router.py` 新增 `pending_module_goal_calendar_sync` 流程分派並把 `calendar_client` 一路串到 `finance:`／`collections:` 分支；②飲食目標補上自動達成判斷——解決「以上/以下方向不明確」問題：`body_goals` 新增 `target_direction` 欄位（migration 0089），`goal_parser.py` 的 `_parse_diet()` 讓 LLM 一併判斷 MIN／MAX 方向，`body.py` 新增 `_diet_cumulative_value()`／`check_and_push_diet_goal_achievements()`，`main.py` `/healthz` 串接；③考試成績自動判斷——`certificate_goals.py` 新增 `check_score_achievement()`，`commands.handle_exam_score_value_step()` 記錄實際成績後立即比對 `target_score`，達標附加恭喜文字 | Claude | 完成（已 push／部署） | 起因：Robin 對批次3原始交付的「已知的刻意簡化」三項明確表達不接受，要求全部補做，見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3補做：不得漏做的三項功能」；沿用雲端沙箱跑滿整套測試流程；完整 `python3 -m pytest -q`：**1897 個測試全過**（原 1878 baseline 全過，新增 19 個：`tests/bot/test_goals.py` 新增 2 項 Calendar 同步、`tests/bot/test_body.py` 新增 4 項飲食目標達成判斷、`tests/bot/test_certificate_goals.py` 新增 7 項成績比對、`tests/bot/test_certificate_exam_scores_commands.py` 新增 2 項整合、`tests/bot/test_goal_tracking_router.py` 新增 1 項記帳目標 Calendar 同步全流程整合，另有既有測試調整為新的預設值斷言）；`ruff check .` 全過；MAX 方向飲食目標若沒有設定期限，數學上沒有「結束邊界」可判斷是否超標，暫時無法自動判斷（設計上的真實限制，非偷懶簡化，已在 SPEC.md FR-48 明確寫出）；`docs/reference/db_schema.md`／SPEC.md 已同步新欄位；後續已由 commit `27c8476` 整併並 push／部署 |
| 2026-08-17 | FR-45a／FR-41b／FR-73a／FR-24a／FR-48 | 批次3「六模組目標泛化＋🎯 目標追蹤新選單」實作完成：新增 3 支 migration（0085 `module_goals` 通用目標表／0086 `goal_summaries` 每日摘要快取表／0087 `body_goals.target_unit` 欄位）；新增 `src/services/goal_parser.py`（方案A LLM 輔助解析目標值/單位）、`src/services/goal_summary_job.py`（每日 01:00 排程，掃描 `body_goals`／`module_goals`／`certificate_goals` 三來源生成快取摘要）、`src/bot/goals.py`（`module_goals` 通用 CRUD＋記帳/收藏清單達成判斷）；`goal_important_day_sync.py` 新增 `sync_module_goal()`；`menu.py` 新增「🎯 目標追蹤」主選單項目與 `GOAL_TRACKING_MODULES`；`commands.py` 新增 `start_module_goal_*`／`handle_module_goal_*`／`start_goal_tracking_*` 系列函式；`router.py` 新增 `finance:goal:*`／`collections:goal:*`／`goal_tracking:*` 分派與共用的 `_dispatch_module_goal_callback()`；`finance.py` 新增指令觸發詞 `/finance_goal`／`/my_finance_goals`，`handle_transaction_note_step()` 寫入交易後檢查目標達成；`collections.py` 子選單新增「🎯 目標」按鈕，標記造訪後檢查目標達成；`body.py` 的 `create_goal()`／`update_goal()` 支援 `target_unit`，飲食目標新增流程接上方案A解析；`main.py` `/healthz` 新增 `_check_module_goal_deadline_reminders()`／`_check_goal_summaries()` 兩個排程檢查（共 16 個） | Claude | 完成（已 push／部署） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3：六模組目標泛化＋🎯 目標追蹤新選單 實作完成」；沿用批次1／批次2「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路，見 `docs/ADR/debug/robinson.md`「Sandbox network limits」），**不是只做語法驗證**；完整 `python3 -m pytest -q`：**1878 個測試全過**（原 1844 baseline 全過，新增 34 個：`tests/services/test_goal_parser.py` 9 項、`tests/services/test_goal_summary_job.py` 7 項、`tests/bot/test_goals.py` 13 項、`tests/bot/test_goal_tracking_router.py` 7 項路由整合測試，另擴充 `tests/bot/conftest.py`／`tests/bot/test_collections.py` 支援新表）；`ruff check .` 全過；**已知的刻意簡化**：①記帳/收藏清單目標新增流程省略 Google Calendar 同步問句（body.py 才有，理由見設計文件）②飲食目標（FR-48 方案A）本批只做結構化欄位解析與儲存，暫不新增自動達成判斷（語意是「以上」還是「以下」不明確，例如熱量控制在X以內是上限、蔬菜攝取X次是下限，需要更明確規則才能安全自動判斷）③考試目標（FR-24a）整合進🎯目標追蹤但不新增自動達成判斷（無應考結果資料可供判斷）；`docs/reference/db_schema.md` 已同步新表／新欄位；後續已由 commit `27c8476` 整併並 push／部署 |
| 2026-08-17 | FR-47／FR-47a | 運動紀錄改版（批次2）實作完成：新增 `exercise_categories` 全域類別表（migration 0084，同批清空舊 `exercise_logs` 並改結構）；`body.py` 新增 `list_exercise_categories()`／`find_or_create_exercise_category()`（正規化比對＋LLM 語意判斷兩段式同義詞合併），改寫 `create_exercise_log()`／`update_exercise_log()`／`format_exercise_log_list()`；`commands.py`／`router.py` 運動流程全面改版為選類別→時長→心率（可跳過）→補充內容（可跳過）→AI／人工熱量二選一→摘要確認；`app_records.py` 同步改寫 exercise 驗證邏輯（`category_id`／`custom_category`／`use_ai_calorie`），新增 `GET /api/app/exercise-categories`（`app_analytics.py`）；Mobile `RecordModal.tsx` 改用 `SearchableSelect` 動態載入類別，移除雙頁籤與重訓特殊分支 | Claude | 程式完成（已部署／實機驗收）；DB 待補套 | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「運動紀錄改版（批次2）實作完成」；沿用批次1「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路），**不是只做語法驗證**；完整 `python3 -m pytest -q`：1844 passed（原 1842 baseline 全過，新增 2 項運動類別測試，改寫既有運動相關測試約 15 項）；`ruff check .` 全過；Mobile 端 `npx tsc --noEmit` 型別檢查通過（前端未設定 lint／單元測試 script）；`docs/reference/db_schema.md`／`api_schema.md` 已同步；commit（`a6fd474`）與 push 皆已完成，Robin 已完成 Telegram Bot 與 Mobile App 實機測試。2026-08-18 DB 查核更正：0084 當時實際未套用，原因與修復見 `docs/ADR/debug/robinson.md`。 |
| 2026-08-17 | FR-45／FR-46 | Phase 6 第二批 2h（日常紀錄－體態）批次1實作完成：`body.py` 合理範圍收斂（身高 140～200 公分、腰圍 50～150 公分、體重新增上限 150 公斤）並新增動態範圍文案函式、`get_body_summary()`／`format_body_summary()`、`update_goal()`／`get_goal()`；`commands.py` 刪除六個舊指令（`/set_height`／`/set_waist`／`/log_weight`／`/backfill_weight`／`/my_weight_logs`／`/set_body_goal`），全面改選單按鈕＋摘要→二次確認，體重歷史清單改按鈕式編輯/刪除；目標子流程重寫成 `body:goal:*` 運動/飲食/體態三入口共用，支援多筆並存＋編輯/刪除；`menu.py` 把 `body` 移出開發中名單；`router.py` 新增 `body:*`／`_dispatch_body_goal_callback()` 分派，`_FINAL_CONFIRM_FLOWS` 新增 6 個新摘要確認 flow（涵蓋全站語音確認機制） | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「日常紀錄－體態（Phase 6 第二批 2h）實作完成」；本批因 Cowork 沙箱本機無網路裝不了套件，改用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程，**不是只做語法驗證**；完整 `python3 -m pytest -q`：1842 passed（原 1809 baseline 全過，新增/改寫 33 項體態相關測試）；`ruff check .` 全過；改寫 `tests/bot/test_body.py`／`test_body_commands.py`（大幅重寫）／`test_body_router.py`（大幅重寫）／`test_menu.py`／`test_router.py`；`docs/reference/` 未異動（本批未變更 DB Schema／API）；commit `30c5303`（11 files changed, 1400 insertions/614 deletions），Robin 已推版並完成 Telegram 實機驗收 |
| 2026-08-16 | FR-48 | 修復飲食補記日期解析 NameError（2g 部署後實機驗收發現）：`handle_diet_backfill_date_step()` 呼叫了不存在的 `_parse_date_description()`，輸入「昨天」等補記日期時直接噴錯 | Claude | 完成（已部署／實機驗收） | 根因與修復細節見 `docs/ADR/debug/robinson.md` 2026-08-16「飲食補記日期解析 NameError」；改用既有 `_parse_key_value_block`＋`_parse_date_only` 解析流程；新增 `tests/bot/test_body_commands.py` 回歸測試；順帶用 `pyflakes` 掃過 `src/bot/`／`src/services/` 全部模組確認無同類「呼叫未定義名稱」問題；commit `fb5e4e2`，Robin 已推版並完成 Telegram 實機驗收（新增今天飲食紀錄→補記昨天→輸入「昨天」正常） |
| 2026-08-17 | — | 純程式品質治理：清除 `ruff check .` 檢出的 99 個既有警告，並把「commit 前跑 `ruff check .`」記錄為固定開發慣例 | Claude | 完成（已部署） | 起因是上一筆飲食補記 NameError（`ast.parse` 語法檢查抓不到「呼叫未定義名稱」，靜態 Lint 才抓得到），Robin 要求記錄慣例並開獨立任務清掉既有警告；新增 `ruff.toml` 明確鎖定 isort `known-first-party = ["src", "submodules"]`（過程中發現同一 ruff 版本在 Robin 本機與 Claude 沙箱因無設定檔而判斷不一致，導致排序建議兩邊對不上，加了設定檔後才穩定一致）；`requirements-dev.txt` 新增 `ruff`；`AGENTS.md`／`docs/templates/AGENTS-TEMPLATE.md` 新增對應開發慣例段落；修正內容含 import 排序、7 處 `date.today()` 改時區感知寫法（DTZ011，均改用專案既有 `_TAIWAN_TZ`／`commands._now()` 模式）、2 處 DTZ007 經人工覆核確認為誤判改加 `# noqa` 註解說明（`important_days.py::_parse_hhmm()` 只取鐘面時刻與時區無關、`newsfeed/client.py::_parse_pub_date()` 下一行即補時區），其餘 RUF059／F841／RUF012／FLY002／FURB157／PIE810／ISC004／SIM117／SIM118 等規則修正，共 35+ 檔案；驗證：`ast.parse`／`pyflakes`／`ruff check .` 全過，Robin 本機 `pytest tests/ -q` 1806 passed／3 failed（僅既有 `test_toeic.py` 缺 `ffmpeg` 環境問題，與本次異動無關）；commit `6bd7540`，Robin 已推版（純程式品質改動，無對外行為變化，不需個別實機驗收） |
| 2026-08-17 | FR-45～FR-48 | Phase 6 第二批 2h（日常紀錄－體態）前置：拆批決策定案，分成①體態選單化②運動紀錄改版③六模組目標泛化三批，並定案體態範圍與運動改版細節 | Claude | 已由後續批次完成 | 決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-17「日常紀錄－體態（Phase 6 第二批 2h）前置討論：範圍拆分與三批決策」；本篇純盤點與定案，後續已開發完成，各批仍需個別提出 SDD 實作計畫並等待確認 |
| 2026-08-17 | FR-45／FR-45a／FR-46／FR-47a／FR-48 | 依 Robin 要求，SPEC.md 提前改寫為體態/運動改版/目標追蹤的定案目標版本（尚未實作，條文內已標註「已定案、尚未實作」並附 ADR 連結） | Claude | 已由後續批次完成 | 純文件同步，未動程式碼；DRAFT.md 無對應項目（已定案不屬於待討論範圍）、reference/ 未異動（尚無 Schema／API 變更） |
| 2026-08-16 | FR-48／FR-16b | Phase 6 第二批 2g：飲食選單化、照片辨識與全站語音轉錄確認 | Claude | 完成（已 push／部署） | commit `a6b49ba`；Robin 本機回歸測試確認本批造成的 15 項問題已修復，後續已由 `origin/main` 確認 push。 |
| 2026-08-16 | FR-31／FR-31a／FR-31b／FR-32／FR-56e／FR-66a | Phase 6 第二批 2f：待辦事項選單化、摘要確認與清單按鈕操作 | Claude | 完成（已部署／實機驗收） | commit `eabed3b`；Robin 已驗收新增、自然語言入口、摘要確認、完成／取消按鈕與舊 `/my_todos` 失效。 |
| 2026-08-16 | — | 純文件治理：AGENTS.md 與 `docs/templates/AGENTS-TEMPLATE.md` 新增「Workflow: Commit → 推版 → 部署後續」，把「commit 指令→版號回報→PROGRESS.md 記錄（push 狀態固定寫『MM/DD Robin已推版』）→第二次 commit 指令→部署後主動提供實機測試步驟」的既有慣例固化成規則 | Claude | 完成 | 使用者要求不用每次重複交代這套流程；兩份檔案同步修改（`Git 與文件同步規則` 補一條指向新 Workflow 的連結、新增完整 Workflow 段落），範本版把「Robin已推版」改成 `<使用者>` 佔位字，保持可攜性；不涉及產品功能，無對應 FR；commit `57619bb`（3 files changed, 52 insertions） |
| 2026-08-16 | FR-6e／FR-6h／FR-45／FR-76／FR-76a | Phase 6 第二批 2e（成果展示）實作完成：新檔 `src/bot/achievements.py` 複用既有 `AppLifeExplorationService`，`menu.py` 移出開發中名單，`router.py` 新增 `achievements:*` callback 分派與 `achievement` flow 分支；同步修正 SPEC.md FR-45／FR-76 條文，改為描述「開啟成果展示清單才被動掃描候選」的實際機制，Telegram 端刪除改為直接執行、不提供二次確認與復原（與 Mobile App 既有 5 秒復原不同） | Claude | 完成（已 push／部署） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2e（成果展示）實作計畫」及「開工完成」補述；新增 `tests/bot/test_achievements.py`（10 項），更新 `tests/bot/test_menu.py` 一項斷言；Claude 沙箱還原 `achievements.py`／`menu.py`／`app_life_exploration.py`／`app_important_days.py`／`geocoding.py` 最小依賴環境後執行 `test_achievements.py`＋`test_menu.py` 共 19 項全過，`router.py` 因依賴鏈過深未在沙箱執行、也未擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試（比照 2d 縮小範圍）。**2026-08-16 Robin 本機驗證**：`test_achievements.py`＋`test_menu.py` 19 項全過；完整 `pytest tests/ -q` 首輪回報 4 項失敗，3 項為既有 `test_toeic.py` `ffmpeg` 環境問題（與本批無關），1 項為 `test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set` 舊斷言未同步 `achievements` 移出開發中名單（比照 2d 曾發生的同類迴歸），修正該斷言後重跑全套 1796 passed／3 failed（僅剩既有 `ffmpeg` 環境問題）；commit `a400f36`（9 files changed, 536 insertions/12 deletions） |
| 2026-08-15 | FR-6h／NFR-19 | 補正 Mobile 日期特例並定案 Telegram 重構採漸進式資料遷移，不整庫刪除重建 | Codex | 規格治理完成 | Mobile 不限今日範圍包含待辦、重要日子、收藏、旅遊、探索、成果；先做唯讀 Schema／引用盤點，必要時採 V2 表回填切換，未執行 Migration 或刪表 |
| 2026-08-15 | FR-3～FR-6h／FR-9c～FR-9d／FR-20a／FR-72b／NFR-18 | 定案 Telegram 角色選單、帳號安全、歷史 CRUD、統一功能流程、七日查詢、排程通知與 Phase 6 執行順序 | Codex | 已由後續批次完成 | 查詢由最終日期往前推 6 天且可跨多模組；Mobile 仍只異動今日生活紀錄，Telegram 負責歷史回補；隱私遮罩改帳號層雙端共用；草稿保留 30 分鐘、功能模式 10 分鐘 |
| 2026-08-15 | FR-3～FR-6h | Phase 6 第二批（Telegram 選單與狀態機）開工前盤點：確認現況無 `/start`、無按鈕基礎設施、`state.flow` 約 85 種、`/set_invite_codes` 移除範圍，並拆出子批次 2a／2b... | Claude | 已由後續批次完成 | 決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批拆批盤點」；2a＝按鈕基礎設施＋選單骨架＋認證選單化（含移除 `/set_invite_codes`），2b 起才逐批遷移既有 85 個 flow |
| 2026-08-15 | FR-3／FR-4／FR-4a～FR-4d／FR-5／FR-6a～FR-6e | Phase 6 第二批 2a 實作完成：Telegram 按鈕基礎設施（`reply_markup`／`answer_callback_query`）、`webhook.py` callback_query 解析與分派、`menu.py` 選單骨架、`/start` 正式實作、Owner 權限管理選單化並移除 `/set_invite_codes` | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2a 實作計畫」及「開工完成」補述；主選單其餘 7 項（日常紀錄／資料查詢／待辦事項／重要日子／收藏與旅遊／成果展示／排程設定）2a 先回覆「功能開發中」，實際邏輯留給 2b 起逐批接上；新增 `tests/bot/test_menu.py`、擴充 `test_router.py`／`test_commands.py`／`test_webhook.py`／`tests/submodules/telegram/test_client.py`，Claude 沙箱 1716 項全過，Robin 本機 1750 項通過／3 項失敗（`test_toeic.py` 因本機未裝 `ffmpeg`，屬既有環境問題，與本批無關）；commit `f623566`，8/15 Robin 已推版；8/15 Robin 已完成實機驗收（/start 首綁流程、主選單 Owner／非 Owner 差異、開發中項目返回按鈕、權限管理建立／停用／恢復／重發密碼、舊指令 /set_invite_codes 已失效） |
| 2026-08-15 | FR-3～FR-6h | 定案 Phase 6 第二批 2b 起子批次分組順序（風險由低到高，資料查詢與排程設定殿後） | Claude | 已由後續批次完成 | 順序：①重要日子②日常紀錄－心情、運動③收藏與旅遊④成果展示⑤待辦事項⑥日常紀錄－飲食⑦日常紀錄－體態⑧日常紀錄－記帳⑨資料查詢（FR-9c/9d）⑩排程設定；決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2b 起子批次分組順序」；僅定案順序，未定案各批次實作細節與起始日期，各批仍需個別提出 SDD 實作計畫並等待確認 |
| 2026-08-15 | FR-6e／FR-6h／FR-72a | Phase 6 第二批 2b（重要日子）實作完成：新檔 `src/bot/important_days.py` 複用既有 `AppImportantDayService`，`router.py` 新增 `menu:important_days`／`important_days:*` callback 分派與對應 flow 分支，`menu.py` 移出開發中名單 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2b（重要日子）實作計畫」及「開工完成」補述；範圍為 CRUD＋清單顯示，FR-72a 主動提醒發送器留給後續「排程設定」批次；新增 `tests/bot/test_important_days.py`（13 項，獨立 FakeDatabase）；擴充 `tests/bot/conftest.py` 共用假 DB 與 `tests/bot/test_router.py`（4 項整合測試）；`webhook.py` 未異動（2a 的通用 callback 機制可直接沿用）；8/16 Robin 本機執行完整 `python3 -m pytest` 全數通過，並完成 Telegram 實機驗收（新增／清單／編輯／刪除／非 Owner 一般使用者皆正常）；commit `f921230` |
| 2026-08-16 | FR-47／FR-49／FR-50 | Phase 6 第二批 2c（日常紀錄－心情、運動）實作完成：`menu.py` 新增「日常紀錄」子選單並移出開發中名單，`router.py`／`commands.py` 心情、運動全面改選單觸發（移除舊 Slash Command／文字觸發詞），兩模組皆補上「摘要→二次確認」關卡，查詢清單改按鈕式編輯／刪除 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c（日常紀錄－心情、運動）實作計畫」及「開工完成」補述；同步移除 `_MOOD_ACTION_CLASSIFY_PROMPT`／`_MOOD_DELETE_CONFIRM_PROMPT`／`_EXERCISE_ACTION_CLASSIFY_PROMPT`／`_EXERCISE_DELETE_CONFIRM_PROMPT` 等 LLM 分類 Prompt，改用明確按鈕；改寫 `tests/bot/test_router.py` 心情 4 項整合測試為按鈕驅動，新增運動 5 項與 `daily_log` 子選單 2 項整合測試，更新 `tests/bot/test_menu.py` 對應斷言；Claude 沙箱還原完整依賴後執行 `tests/` 全數 155 項通過；文件複查發現 FR-47／FR-49 條文原寫死舊指令名稱，已同步更新 `docs/specs/SPEC.md` 對應段落（詳見 ADR「開工完成（2026-08-16 補正）」）；`docs/specs/DRAFT.md`／`docs/reference/` 確認不需異動；commit `8d0ba92`，8/16 Robin 已推版（`git log origin/main` 已確認），並完成 Telegram 實機驗收 |
| 2026-08-16 | FR-6e／FR-6h／FR-73～FR-74a | Phase 6 第二批 2d（收藏與旅遊）實作完成：新檔 `src/bot/collections.py`／`src/bot/trips.py` 複用既有 `AppCollectionService`／`AppLifeExplorationService`，收藏與旅遊一次做完（比照 2c 決策，不拆兩個子批次）；地址定位比照 Mobile 規則，改成「📍 定位地址／⏭ 略過定位」按鈕才呼叫 Nominatim；行程新增支援交通／住宿／飲食／門票／購物／其他六類逐一輸入預估支出；`menu.py` 移出開發中名單，`router.py` 新增 `collections:*`／`trips:*` callback 分派與 `collection`／`collection_delete_confirm`／`trip`／`trip_delete_confirm`／`trip_complete_select` 五個 flow 分支 | Claude | 完成（已 commit／推版，**實機驗收發現 1 個問題，見下一筆補修紀錄**） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2d（收藏與旅遊）實作計畫」及「開工完成」補述；新增 `tests/bot/test_collections.py`（10 項）、`tests/bot/test_trips.py`（8 項），更新 `tests/bot/test_menu.py` 一項斷言，皆用獨立 `FakeDatabase`（服務層驗證邏輯已在 `tests/services/test_app_collections.py`／`test_app_life_exploration.py` 覆蓋，這裡只測 Telegram 流程）；**本批 Claude 沙箱未執行 `pytest`**（與 2b／2c 不同，這次連輕量測試都還沒在沙箱跑過），Robin push 前本機執行測試通過；也**未擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試**；`docs/specs/SPEC.md`（FR-6e／FR-73～FR-74a 為既有已定案規格，本批純實作）／`docs/reference/api_schema.md`／`db_schema.md`（沒有新增 HTTP 路由或資料表異動）／`docs/specs/DRAFT.md`（無相關項目）確認不需更新；commit `bf715ff`（9 files changed, 1486 insertions），8/16 Robin 已推版 |
| 2026-08-16 | FR-73／FR-6h | Phase 6 第二批 2d 補修：Telegram 收藏清單新增「🧭 標記已造訪」動作，直接呼叫既有 `AppLifeExplorationService.visit_collection()`，補上「收藏可不經行程、直接標記已造訪」入口 | Claude | 完成（已 commit／推版／實機驗收） | 根因與修復細節見 `docs/ADR/debug/robinson.md` 2026-08-16「Telegram 新增的收藏不會出現在探索地圖」；`src/bot/collections.py` 新增 `start_visit()`／`handle_visit_step()`，`src/bot/router.py` 新增 `collections:visit:<id>` callback 與 `collection_visit` flow 分支；新增 `tests/bot/test_collections.py` 3 項測試，Robin 本機 `pytest tests/bot/test_collections.py` 13 項全過；順帶修正 `tests/bot/test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set` 斷言（2d 主批次移出 `collections` 開發中名單時漏改這個舊斷言，屬於迴歸修正，Robin 本機確認 PASSED）；Robin 執行完整 `pytest tests/` 另回報 19 項與本次無關的既有失敗（16 項心情／運動測試與 2c 遺留的函式簽章／已移除函式不符，3 項因本機缺 `ffmpeg`），詳見 `docs/ADR/debug/robinson.md` 補述段落，根因已排查完成（見下一筆）；`docs/specs/SPEC.md` 不動（FR-73 既有規格已涵蓋「狀態依行程關聯與造訪紀錄自動推導」，本次是補齊 Telegram 端遺漏的入口，非規格變更）；commit `9932732`（7 files changed, 208 insertions），08/16 Robin 已推版並完成 Telegram 實機驗收（新增收藏成功定位→標記已造訪→探索地圖出現圓形標記皆正常） |
| 2026-08-16 | FR-47／FR-49 | 修復 2c 遺留、與心情／運動相關的 16 項既有測試失敗（非本次 2d 功能異動，純測試同步）：`handle_mood_content_step`／`handle_exercise_heart_rate_step` 已在 2c 改為「摘要→二次確認」關卡不再直接寫入，`start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 已在 2c 移除，但 `tests/bot/test_commands.py`／`tests/bot/test_body_commands.py`／`tests/bot/test_body_router.py` 從未同步更新 | Claude | 完成（已 commit／推版） | 根因與修復方式見 `docs/ADR/debug/robinson.md` 2026-08-16「補述之二」段落；`tests/bot/test_commands.py`：改寫 4 項 `handle_mood_content_step` 測試為「內容步驟只組摘要」＋「`handle_mood_confirm_save` 才寫入」兩段式斷言，刪除呼叫已移除函式的 11 項測試（清單／更新/刪除流程的端對端覆蓋已存在於 `tests/bot/test_router.py`，見 `test_mood_list_update_and_delete_full_flow()`／`test_mood_delete_only_owner_can_target_own_journal()`，確認無覆蓋率缺口）；`tests/bot/test_body_commands.py`：修正 `test_exercise_full_log_flow_with_calorie_estimate` 呼叫 `handle_exercise_heart_rate_step` 的參數與二段式寫入流程；`tests/bot/test_body_router.py`：改寫 `test_log_exercise_full_flow`／`test_my_exercise_logs_full_flow_delete` 改用現行按鈕入口（`daily_log:exercise`→`exercise:new`／`exercise:list`→`exercise:delete:<id>`→`exercise:confirm_delete:<id>`），取代已移除的舊文字觸發詞；Robin 本機執行 `pytest tests/bot/test_commands.py tests/bot/test_body_commands.py tests/bot/test_body_router.py -v` 201 項全過，完整 `pytest tests/` 1787 passed／3 failed（僅剩既有 `ffmpeg` 環境問題，與本次無關），16 項迴歸已全數修復；`docs/specs/DRAFT.md` 2026-08-16 待討論項目已移除（見下方 DRAFT 同步）；commit `f0f7349`（6 files changed, 83 insertions/168 deletions），08/16 Robin 已推版 |
| 2026-08-15 | FR-77 | 定案取消功能的路由、流程、測試與資料表清理 | Codex | 完成（已 push／部署／實機驗收） | 第一批淘汰 `complaints`、`knowledge_base`、`conversation_logs`、`conversation_summaries`；一般聊天正式路由已停止持久化，其餘客訴路由、舊函式、相關測試及四張資料表仍待清理。NFR-14～NFR-15 架構遷移已於 2026-08-18 取消，不再列入 Roadmap |
| 2026-08-15 | FR-19k | 定案 Owner 錯誤通知的 Telegram／Email／未送達狀態追蹤與系統錯誤管理呈現 | Codex | 部分完成 | 本次已實作送達管道與時間落地；Owner 系統錯誤管理選單的展示仍待後續批次。Email 成功不重複通知，且不適用一般使用者推播。 |
| 2026-08-15 | FR-1～FR-4（功能開關） | 將技術分享、求職分析、考試成績改為 Robin／Owner 永久專屬，取消非管理者授權與個別排程設計 | Codex | 完成（已 push／部署／實機驗收） | 一般使用者 Telegram／Mobile 不顯示入口且後端拒絕存取；Mobile 另需同步角色顯示、移除客訴入口、成果候選跨端狀態及系統錯誤送達狀態；既有資料保留 |
| 2026-08-15 | FR-19h～FR-20／FR-45／FR-72a／FR-74b／FR-76 | 定案 Telegram 主動推播邊界、重要日子統一提醒、成果候選雙端確認，以及 Owner 異常／康復通知規則 | Codex | 完成（已 push／部署／實機驗收） | 保留待辦、重要日子、月底月報、預算 50%／80%、低頻非同步結果與三項授權功能推播；取消日常紀錄催促及重複操作成功通知 |
| 2026-08-15 | FR-6c | 定案 Telegram 功能模式切換、10 分鐘逾時、草稿保護與功能名稱確認入口 | Codex | 完成（已 push／部署／實機驗收） | 2026-08-18 補充確認：模式逾時後草稿保留至 30 分鐘且期間可一般聊天；只有已有輸入的新增／編輯流程算草稿，每位使用者每個功能最多一份且可跨功能並存；再次進入原功能須先顯示草稿摘要並提供繼續／放棄；自然語言採固定名稱／別名，只導向選單、不使用 LLM 猜測或直接異動資料。權限檢查套用選單、Callback、文字／語音名稱偵測與模式切換 |
| 2026-08-15 | FR-4～FR-8／FR-10～FR-12 | 停用持久化家庭／個人知識庫、逐則對話與長記憶，改用靜態人格 Prompt 及 10 分鐘記憶體上下文 | Codex | 完成（已 push／部署／實機驗收） | 對應路由、流程與三張資料表已納入 FR-77 Phase 6 清理；DROP 前仍須完成依賴、備份與回滾審核 |
| 2026-08-15 | FR-2／FR-9a／FR-9b | 縮限 Telegram 一般對話為個人資料彈性查詢、內容整理分析及功能導引；正式資料異動一律走選單 | Codex | 完成（已 push／部署／實機驗收） | 持久化知識庫與對話記憶已另行定案停用，只保留 10 分鐘記憶體上下文 |
| 2026-08-15 | FR-6a／FR-6b | Telegram 除 `/start` 外全面取消 Slash Commands，所有一般與 Owner 操作改由權限化選單及引導式對話 | Codex | 完成（2026-08-18） | 最後五個舊指令及兩套過時文字狀態機已移除；自然語言／語音功能名稱確認入口仍保留。 |
| 2026-08-15 | FR-5／FR-6／FR-56 | Telegram「使用規則」改為固定模板選單並精簡文案；取消 `/function` 與功能總覽／細節追問 | Codex | 完成（已 push／部署／實機驗收） | 精簡模板沿用於首次綁定歡迎，刪除條目後重新連號 |
| 2026-08-15 | | 建立新專案與未來新功能的資料模型準則，並明定本專案既有表不因整理目的刪除重建 | Codex | 完成 | 同步 AGENTS、通用 Template 與 DB Schema Reference；純文件治理，未執行 Migration |
| 2026-08-15 | FR-2～FR-4／FR-4a～FR-4d | Phase 6 第一批（認證／使用者綁定）：新增 `nickname`／`family_title`／`is_active`、通關密碼 24 小時到期與 5 次錯誤鎖定 30 分鐘、`create_user_and_invite()`／`resend_passcode()`／`set_user_active()` | Claude | 完成（已部署／實機驗收） | 範圍刻意只做後端資料模型與核心驗證邏輯，Owner「權限管理」選單化流程延後到下一批（Telegram 選單與狀態機）一起做，避免與選單重構混在同一不可回退批次；`try_bind_invite_code()` 對外行為相容，`router.py` 呼叫端未變動；鎖定計數存 process 記憶體不落地（理由見 db_schema.md 0083 條目）；新增 `tests/bot/test_auth.py` 27 項測試全數通過，Robin 本機亦已覆核通過。**2026-08-15 追加修正**：`0083` 把 `invite_codes.expires_at` 改 NOT NULL 後，發現既有 `/set_invite_codes` 指令流程（`src/bot/commands.py`）未帶該欄位會直接寫入失敗，已補上 `expires_at`／`family_title`／`is_active`，屬本批次內部迴歸修正，未變更該指令對外行為。**2026-08-15 Robin 實機確認**：Render 部署後 Migration `0083` 已自動套用，`/set_invite_codes` 寫入正常、家人帳號輸入密碼綁定成功 |
| 2026-08-15 | FR-60～FR-63 | 原「使用者建檔與移除客訴」條目拆分：客訴入口、API、流程與資料表清理保留在 FR-77 Phase 6 統一清理範圍，不併入本批 | Claude | 完成（已 push／部署／實機驗收） | 見 FR-77 那筆任務 |
| 2026-08-14 | FR-64／FR-65 | 修復重要日子家庭成員查詢與求職分析契合度欄位錯置 | Codex | 完成（已部署驗收） | 使用者 ID 改由 `users.id` 動態產生；求職 SQL 改讀 `score AS match_score`；2026-08-15 Robin 已確認正式環境功能正常 |
| 2026-08-14 | FR-72a／FR-74／FR-75 | 探索篩選與定位提示、旅遊行程今日標示、重要日子載入相容修正及目標日期同步 | Codex | 完成（已部署驗收） | `0082` 體態／證照目標的重要日子關聯與既有資料回填已部署；2026-08-15 Robin 已確認功能正常 |
| 2026-08-14 | FR-73／FR-75 | 收藏地址選填、漸進式近似定位及收藏操作按鈕修復 | Codex | 完成（已實機驗收） | 地址定位、區域 fallback 與跨平台確認 Modal 已於 2026-08-15 由 Robin 確認正常 |
| 2026-08-14 | FR-73～FR-76a | 收藏清單／旅遊行程／探索地圖／成果展示 Phase 5 實作 | Codex | 完成（已部署／實機驗收） | `0079`～`0080`、生活探索 API／Service、Mobile 畫面、記帳關聯與 Nominatim 已部署，2026-08-15 Robin 確認功能正常 |
| 2026-08-14 | FR-75 | 完成 Nominatim 地址轉座標、快取、頻率限制及探索重新定位 | Codex | 完成（已部署驗收） | 正式環境已設定 Nominatim 識別 User-Agent；2026-08-15 Robin 已確認定位與探索功能正常 |
| 2026-08-14 | FR-73 | 修復 Mobile App 首頁「新增收藏」Modal 在手機窄螢幕跑版 | Codex | 完成（已實機驗收） | 選項換行、捲動區與底部按鈕間距已於 2026-08-15 由 Robin 確認正常 |
| 2026-08-14 | FR-73～FR-75 | 收藏地點組合選單、固定捲動區、行程目的地過濾、重要日子同步與探索刪除修正 | Codex | 完成（已部署／實機驗收） | `0081` 已部署；組合選單、固定捲動區、目的地過濾、行程行事曆、重要日子同步與探索刪除已於 2026-08-15 確認正常 |
| 2026-08-14 | FR-69／FR-70／FR-71 | 正式取消 Mobile App 目標與指標設定、功能開關頁及 Robin 專屬排程設定，從 SPEC 與 Roadmap 移除 | Codex | 已取消 | 既有 Telegram 設定流程不受影響；見 DRAFT 與 mobile-app ADR |
| 2026-08-14 | | 專案開發治理規則統一：AGENTS／Template 補齊文件生命週期、commit 同步、ADR／Reference 規範，並修正 `.claude/` 指令與代理規則漂移 | Codex | 完成 | 純文件治理；不需程式測試 |
| 2026-07-28 | | 專案緣起：完成外部服務註冊／API 金鑰申請、Telegram Bot 基礎設定，與 Gemini 腦力激盪收斂 PRD 雛形 | Robin | 完成 | Claude Code 協作開始前 |
| 2026-07-29 | | 完成需求彙整，建立產品規格書 `docs/specs/robinson/SPEC.md` | Claude | 完成 | 里程碑 |
| 2026-07-29 | | 建立開發階段紀錄文件 PROGRESS.md | Claude | 完成 | 里程碑 |
| 2026-07-29 | FR-15 | 調整語音修正限制為 15 分鐘窗口 | Claude | 完成 | 里程碑 |
| 2026-07-29 | | 完成 `submodules/` 共用子模組骨架（`neon_postgres`／`telegram_client`／`gemini_client`），新建 submodules-core SPEC | Claude | 完成 | 里程碑 |
| 2026-07-29 | | `submodules/` 依指定樣板重構為 `llm`／`cloudsql`／`telegram`，統一四檔案結構 | Claude | 完成 | 里程碑 |
| 2026-07-29 | FR-19 | 重寫 FR-19：錯誤處理擴充為 5 步驟自主診斷流程（ADR-7），AI 診斷延後至 Phase 2 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6a～FR-6c | 7 項待確認事項全數回覆，Phase 1 解除阻塞；通關密碼設定改為 Owner 對話流 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-19f～FR-19i | 新增例外分級降級、決策執行狀態閉環回饋、外部 API 重試機制與 NFR-9／NFR-10 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 新增 `docs/profile/Robinson.png`（永久禁止刪除），記錄於 SPEC「重要資產」章節 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | `.env.example` 新增 `GITHUB_TOKEN`／`GITHUB_REPO`，同步更新 NFR-5 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6d／FR-55／FR-56 | 新增驗證成功歡迎訊息、`/rule` 與 `/function` 路由；新增附錄 A 規範文本 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 補上「專案緣起」段落；目標時程由一週改為兩週 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-57～FR-59 | 新增 YouTube 技術情報模組（ADR-9）：每週四推播 Top 3 技術影片、三層輕量篩選 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Phase 3 因 YouTube 模組由 2 天延長為 3 天，Phase 4／緩衝日順延 1 天 | Claude | 完成 | 里程碑 |
| 2026-07-30 | NFR-13 | 概要新增「使用性質聲明」（個人非商業用途） | Claude | 完成 | 里程碑 |
| 2026-07-30 | NFR-12 | 新增 ADR-10（Schema 先審核後執行）；建立 `db_schema.md`／`api_schema.md` 骨架 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-60～FR-63 | 新增客訴收集功能（`/complaint` 路由、內容記錄、Gemini 分析私訊、人工決策），Phase 1 新增 Step 1.9 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-55 | 附錄 A 開頭語句改為「📋 以下是羅賓森的使用須知：」 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 金鑰外洩事故處理：測試腳本將 `TELEGRAM_BOT_TOKEN`／`YOUTUBE_API_KEY` 明文印出於對話紀錄，金鑰已重新產生 | Claude | 完成 | 里程碑／事故 |
| 2026-07-30 | | 發現 Cowork sandbox 對外部服務有網路白名單限制（連不到 Neon／Telegram／Google／Notion API） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.5a 完成：建立 `src/migrations/`、`CloudSQLClient.execute()`、開機自動套用 migration | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.3 完成：Render 部署成功並取得正式網址 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.4 完成：cron-job.org 每 10 分鐘呼叫 `/healthz` | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.5 第一批 5 張表核准並 push（`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Render 部署 log 確認 `0001`～`0005` migration 全數套用，Phase 0 全數完成 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6d | Phase 1 Step 1.1 完成：通關密碼驗證、Owner `/set_invite_codes` 對話流、歡迎訊息、`/rule`／`/function` | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-17／FR-56 | 多模態與人格化語氣大改版：四把 Gemini Key＋Groq `VOICE_API_KEY`（ADR-12、ADR-13） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | `0006` migration 套用成功，Robinson 人格背景與家人背景寫入 `knowledge_base` | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-2a | 確認 Step 1.2 功能開關權限模型（使用者自管、Owner 代管），展開獨立 feature-toggles SPEC | Claude | 完成 | 里程碑 |
| 2026-07-31 | | 確認查無答案採「單次 API 呼叫＋Google Search grounding」，展開獨立 chat-core SPEC | Claude | 完成 | 里程碑 |
| 2026-07-31 | | 記憶架構改為「長記憶＋短記憶＋知識庫＋上網查資料」，核准 `conversation_summaries` 建表 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-56e～FR-56h | 補上待辦／求職／體態管理／心情小記情境範例，補充 FR-31a、FR-46 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-9 | Phase 1 Step 1.3a 完成：`/function` 改為總覽＋按需深入＋情境範例（ADR-4） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-7 | 實測撞到 Gemini 429，`webhook.py` 未攔截例外造成 Telegram 重試風暴，新增安全網 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-7a | 追加兩層額度防護（`update_id` 去重、本地端節流） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-17 | 確認 429 為真實額度超限；確認 Step 1.3b 設計（`media_uploads` 表統一記錄圖片／語音 Drive 網址） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-17／FR-17a～c | Phase 1 Step 1.3b 完成：影像辨識基礎流程，新增 `submodules/gdrive/` | Claude | 完成 | 里程碑 |
| 2026-07-31 | | `GEMINI_API_BOT_KEY` 換新後 `gemini-2.5-flash` 回傳 404，排查並確認 Gemini 2.5 世代模型可用性 | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-11／FR-12 | chat-core 多項修正與新功能（日期幻覺、代名詞指涉、打字誤植先反問、`/clean-all-dialog`／`/clean-target-dialog`） | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-14／FR-15 | Phase 1 Step 1.4 完成：語音轉文字流程，新增 `submodules/voice/`（Groq Whisper） | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-14 | Step 1.4 追加修正：補上 `message.audio`（上傳音檔）支援 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-16a | 新增語音最終執行確認關卡，防聽錯誤觸不可逆操作 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-16a | 追加優化：最終確認狀態收到新語音一律短路，避免浪費 Drive／Groq 額度 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-14 | 補上 FR-14 規則 1：單次語音超過 10 分鐘才觸發 15 分鐘全面鎖定 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-15 | 語音功能被限制／恢復時主動提醒使用者（修正窗口提醒） | Claude | 完成 | 里程碑 |
| 2026-08-02 | | 修正 Telegram `send_text` 400 錯誤，並排查 gdrive 金鑰路徑問題 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-13／FR-13a～d | Phase 1 Step 1.5 完成：個資偵測與遮蔽機制，展開獨立 privacy-masking SPEC | Claude | 完成 | 里程碑 |
| 2026-08-02 | | gdrive 改用 OAuth 2.0（真人帳號身分），解決 Drive `403 storageQuotaExceeded` | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-19a／FR-20／FR-21 | Phase 1 Step 1.6 完成：基礎錯誤處理層 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31／FR-31a／FR-32 | Phase 1 Step 1.7 完成：待辦事項模組 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-49／FR-50 | Phase 1 Step 1.8 完成：心情小記模組 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-60～FR-63 | Phase 1 Step 1.9 完成：客訴收集模組，Phase 1（MVP）全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-02 | | Bug 修正：「完全不理我」空回覆防呆 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31 | Bug 追加修正（上一輪非真正主因）＋兩個待辦事項問題 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31b | 新增待辦事項支援時間區間 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-49 | 心情小記擴充補記／更新／刪除 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-41～FR-44 | Phase 2 Step 2.1 完成：記帳模組（Phase 1 全數完成，進入 Phase 2） | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-13 | Bug 修正：個資遮蔽語意層暫時性外部錯誤導致整則訊息完全無回覆 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-44a | 記帳模組擴充：月底自動推播月報 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-41a／FR-42a | 記帳模組擴充：預算特殊月份覆蓋、每日記帳提醒 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-45～FR-48 | Phase 2 Step 2.2 完成：體態管理模組 | Claude | 完成 | 里程碑 |
| 2026-08-04 | | 移除 Notion 後台改採 Mobile App（React Native + Expo），新增 ADR-14 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-53 | Phase 2 Step 2.3 完成：重要通知模組（超級重要通知／一般重要通知） | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-19b | Step 2.4 開工前範疇簡化，新增 ADR-15（supersede ADR-7） | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-19b | Phase 2 Step 2.4 完成：錯誤 log 雲端連結 | Claude | 完成 | 里程碑 |
| 2026-08-05 | | 新增 ADR-16：Telegram 故障時的 email 備援通知 | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-66 | 新增 Step 2.7、ADR-17（規格層級）：Google Calendar 整合 | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-66 | Phase 2 Step 2.7 完成：Google Calendar 整合（家人共用一律免費帳號、唯讀權限） | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-19i | Phase 2 Step 2.5 完成：外部 API 重試機制，新增共用 `submodules/retry` | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-19f～FR-19h | Phase 2 Step 2.6 完成：例外分級降級與決策執行狀態閉環回饋，Phase 2 全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-22／FR-23 | Phase 3 Step 3.1 完成：每日重點技術分享 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-22 | Step 3.1 當日修正：拆成 23:00 收集／08:00 推播兩階段，改用 `skill_growth_digests` 表 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-2 | 功能開關拆分：`skill_growth` 拆成 `tech_intel`／`certificate`／`language` | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-24／FR-25a～f | Phase 3 Step 3.2 完成：TOEIC 雙軌題庫 Pipeline | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-25 | Step 3.2 當日修正：整包 MP3 切割改為自動判斷開頭有無作答說明語音 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-25 | Step 3.2 追加：`exam_type` 泛用化，不寫死證照種類清單（ADR-18 決策 4） | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-26～FR-30 | Step 3.3 規格定案（尚未實作），新增 ADR-19 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-27 | Step 3.3 第一階段實作：答案照片比對機制＋新資料表 | Claude | 完成 | 里程碑 |
| 2026-08-08 | | Production 事故：`/healthz` 逾時＋Phase 2／3 migration 疑似未套用（大量 `UndefinedColumn`） | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | | Production 事故根因找到並修復：migration 卡在 `0018` 的 `IndexError` | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | | Production 事故解決確認：一口氣套用 25 筆待處理 migration | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | FR-26 | Step 3.3 每日推播／作答細部設計定案，新增 ADR-20 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-26 | Step 3.3 每日 08:00 推播出題機制實作完成，新增 3 張表 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-26 | Step 3.3 彈性排程新增第四種語意「平攤」（ADR-20 決策 5／6 補充） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-46 | Phase 2 體態管理擴充：新增腰圍設定 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-64a | Phase 4 Mobile App 新增藍牙體重計整合規格（規格層級） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-27／FR-28 | Step 3.3 作答與批改流程＋20:00 提醒＋彈性排程對話流程實作完成 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-24／FR-29／FR-30 | Step 3.3 剩餘範圍全數完成（成效彈性文字問答、目標設定與方向建議、正式成績記錄） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-57～FR-59 | Step 3.4 開工前規格釐清，新增 ADR-21（supersede ADR-9） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-58a | Step 3.4 再修正：移除「排除 Shorts」規則，改為完全交給 LLM 判讀品質 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-57～FR-59 | Step 3.4 實作完成：YouTube 技術情報模組全數落地 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-51／FR-52 | Step 3.5 開工前規格定案，新增 ADR-22 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-51／FR-52 | Step 3.5 實作完成：好友模式，Phase 3 全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-08 | | `language`（語言學習）功能規劃決議擱置，新增 ADR-23 | Claude | 完成 | 里程碑；見 `docs/specs/DRAFT.md` 擱置中 |
| 2026-08-08 | FR-33～FR-36 | Step 4.1 開工前規格定案，新增 ADR-24 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-22 | 生產環境回饋修正：`skill_growth_digests` 改為一天多筆、一筆一來源管道，推播改三行式精簡格式（ADR-25） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-33／FR-36 | Step 4.1 正式開工，完成 Phase A（DB migration）＋Phase B（對話式收集流程） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34／FR-35 | Step 4.1 Phase C～F 一次完成：104 爬蟲＋公司背景 Email 協作＋週排程掛載 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34a | Step 4.1 真實流量驗證完成（瀏覽器 DevTools Network 實測修正欄位對照與端點路徑） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34a | Step 4.1 地區／產業篩選機制修正：產業篩選移除、地區改子字串比對 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34 | `job_postings.is_closed` 新增並串接爬蟲（解決 ADR-26 決策 5 原問題） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-37／FR-38 | Step 4.2 開工前規格定案，新增 ADR-26 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-37／FR-38 | Step 4.2 全數實作完成：Gemini 契合度評分＋技能缺口分析＋雙重排名 Excel 交付 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 開工前規格定案，新增 ADR-27 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 資料結構設計修正：外部管道職缺改用 `source` 欄位共用同一張表 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 全數實作完成：應徵成效追蹤＋外部管道職缺，Phase 4 求職主線全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64～FR-72 | Mobile App（Step 4.4／4.5）規格盤點與定案，新增 ADR-28 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64～FR-72 | Mobile App 規格追加確認＋定名「羅賓森」 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-22 | 每日技術分享改回深入摘要、拆成三則獨立訊息，修正 IThome RSS 解析 bug（ADR-29，supersede ADR-25 部分） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64 | Mobile App 使用者體驗方向第二輪確認，建立獨立 mobile-app SPEC | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-19j | 客訴回饋頁設計修正＋新增 FR-19j（系統錯誤記錄與解法追蹤，Placeholder） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-53f／FR-19j | FR-53f 重要通知邏輯修正＋FR-19j 系統錯誤記錄與解法追蹤全數實作完成（ADR-30） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-64 | 首頁新增「體重紀錄」卡片規劃（純規格文件更新，尚未開工） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-64～FR-72 | Mobile App 剩餘待確認事項一次盤點並定案（純規格文件更新，尚未開工） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-65 | Mobile App Step 4.4／4.5：登入與 Token 機制（後端 App Auth API、bcrypt 密碼、JWT Access Token、Refresh Token rolling、Expo 登入頁、SecureStore、Telegram 忘記密碼） | Codex | 完成 | codex.md |
| 2026-08-10 | FR-65 | 登入頁預覽回饋調整：移除品牌文案／卡片標題、placeholder 統一「請輸入」、顯示切換改眼睛 icon | Codex | 完成 | codex.md |
| 2026-08-10～2026-08-12 | FR-64／FR-64a／FR-65／FR-67／FR-68／FR-72 | Step 4.4／4.5 Mobile App「羅賓森」由 Placeholder 大幅推進為實作中 | Codex | 完成 | 里程碑；本輪由 Codex Desktop 開發，逐階段明細見下列 codex.md 條目 |
| 2026-08-11 | FR-67b／FR-68 | 個人基本資訊頁與安全修改密碼（密碼強度、歷史密碼不可重用、`user_password_history` 表、改密後撤銷 Refresh Token） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 操作介面、體態身高與最新紀錄權限調整（身高存 `users.height_cm`、全期間最新體態卡片、跨平台 TimePicker） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64／FR-64a | 今日單筆紀錄、待辦狀態下拉與腰圍趨勢（`body_weight_logs.waist_cm`、飲食／心情／體態每日單筆） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 首頁快速紀錄與今日紀錄 CRUD（`app_records` Service、六種紀錄 Modal、10 分鐘重複偵測、歷史唯讀） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 體重紀錄卡片、輸入視窗與同日趨勢修正（`DISTINCT ON (entry_date)` 同日只取最新一筆） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | Web Bluetooth／Bluefy 相容性 POC：結論為 PWA＋Bluefy 無法取代原生 BLE | Codex | 完成 | codex.md；決策見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-11 | FR-64a | 全面移除 BLE，改為手動記錄體重（`40.0～150.0 kg`、二次確認、API 邊界同步驗證） | Codex | 完成 | codex.md；決策見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-11 | FR-64a | 藍牙體重計量測與體重寫入（Yoda1 廣播解析、`POST /api/app/body/weight-logs`）＋待辦行事曆區間標示、登入／問候 icon 調整 | Codex | 完成 | codex.md；本項後由「全面移除 BLE」取代 |
| 2026-08-11 | FR-65 | 登入前使用者 ID 預先辨識（`POST /api/app/auth/identify`、五種辨識狀態、密碼欄依辨識結果啟用） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | Step 4.5 唯讀儀表板與分析頁面（`app_analytics` Service／API、八個分析模組、`react-native-svg` 圖表、AppShell／DateRangeFilter） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-65 | 登入欄位、Toast 與背景圖案調整（使用者 ID 改明碼、忘記密碼防呆 Toast、漸層＋點陣背景） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64／FR-65 | 預覽回饋調整（全站共用背景、性別頭像、上次／最近登入時間、行事曆式日期選擇、技術分享單日查詢） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | 待辦日期範圍、件數與清單互動修正（待辦改 1～7 天且允許未來日期、月曆件數、點擊捲動） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | 待辦區間 API、今日標示與狀態卡片修正（`parse_todo_date_range()`、四種狀態標籤配色） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-65／FR-67 | 登入提示、性別頭像與登出修正（一次性登入提示 Modal、`boy.png`／`woman.png`、自訂登出確認 Modal） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 首頁體態卡片標題修正與紀錄視窗標題靠左對齊 | Codex | 完成 | codex.md |
| 2026-08-11 | FR-67b／FR-68 | 個人選單按鈕視覺一致性修正（改為與左側功能選單相同的白底圖示文字列） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-67b／FR-68 | 個人選單項目靠左修正 | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64～FR-72 | Step 4.4／4.5 大量未 commit 程式碼正式 commit＋push，完成正式上線部署（後端 Render＋前端 Vercel） | Claude | 完成 | 里程碑 |
| 2026-08-12 | FR-65 | Web 版 PWA「加入主畫面」體驗修正：SPA 路由 404、App icon、雙指縮放 | Claude | 完成 | 里程碑 |
| 2026-08-12 | | 收藏清單第一階段、首頁新入口與資料結構（`0071`～`0077` migration、收藏 CRUD API、收藏頁／首頁卡片） | Codex | 完成 | codex.md；規格未定案，見 `docs/specs/DRAFT.md` 待討論 |
| 2026-08-12 | FR-64 | 行事曆多活動防跑版（固定日期格高度、重要日子單行「+N」摘要） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 首頁本周重要日子、iPhone 輸入體驗與飲水紀錄（當週邊界過濾、`food`／`water` 分流、輸入字級 ≥16px） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 全行事曆文案去重與語意配色統一（節日紅、重要日子藍、件數橘／黑；同名節日只留一筆） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 操作可靠性與誤刪復原（請求鎖防連點、失敗保留輸入、刪除 5 秒復原期） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64a | 飲食拍照／相簿辨識、內容確認與營養估算（`app_diet_photo` Service、辨識→確認→估算→再確認、新增／取代模式） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 待辦日期區間行事曆資料同步修正（三個行事曆共用同一份月份資料、重要通知與生日合併） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 重要日子設定與待辦整合行事曆（`0069` 三張表、`app_important_days` Service／API、管理頁、首頁重要通知改時程清單） | Codex | 完成 | codex.md；Telegram 提醒未納入，見 `docs/specs/DRAFT.md` 待討論 |
| 2026-08-12 | FR-72 | APP 設定（`0067` 偏好欄位、深／淺色模式、字體大小、隱私數字遮罩與 `SensitiveValue` 元件） | Codex | 完成 | codex.md；FR-69／FR-70／FR-71 本輪依指示跳過 |
| 2026-08-12 | FR-65 | 使用者 ID 失焦驗證造成登入按鈕無回應修復 | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
| 2026-08-12 | FR-72 | 個人選單間距與深色模式可讀性修正（行事曆深色主題、重複字級倍率移除） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-72 | 今日紀錄視窗深色配色補強（六種紀錄視窗、內嵌行事曆、時間選擇欄位） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 中華民國行事曆、待辦件數與導覽順序（`0068` 快取表、`taiwan_calendar` Service、左側選單固定排序） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 重要日子設定：行事曆統一與通知對象狀態改善 | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 待辦事項與重要日子日期區間（`0070` 結束日欄位、區間重疊查詢、`GENERATE_SERIES` 逐日計數） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 分析頁日期選擇器行事曆統一（`holidayOnly` 模式，只顯示政府節日） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 飲食照片與 Gemini 流程實機驗收完成（拍照／相簿選擇、辨識與後續流程可正常使用） | Robin／Codex | 完成 | Robin 已於實體手機確認兩種照片來源皆可使用 |
| 2026-08-12 | | 收藏清單／探索地圖／成果展示前置 POC（Leaflet 1.9.4＋OpenStreetMap，不採 Expo Maps） | Codex | 完成 | codex.md；技術選型見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-12 | FR-64 | 首頁心情趨勢卡片高度修正 | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
| 2026-08-14 | FR-64 | 飲食／運動雙輸入模式、AI／人工來源圖例、心情 Emoji 與窄螢幕按鈕完成實作 | Codex | 完成 | 新增 `0078` migration、輸入防呆、照片確認流程、來源拆分圖表與 Tooltip；147 項相關測試通過，完整回歸 1676 通過／3 項因本機缺 `ffmpeg` 未執行，Mobile typecheck 與 Web export 通過 |
| 2026-08-14 | FR-65 | Expo 本機預覽登入 API 路由修正 | Codex | 完成 | localhost 改用 `EXPO_PUBLIC_API_BASE_URL`，正式 Web 維持同網域 API；瀏覽器已驗證 `user01` 可完成身分辨識 |
| 2026-08-12 | FR-65 | Web 預覽登入無法連線修正（API Base URL 改 `window.location.origin`、React Hook 順序、快取標頭） | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
> 「開發者」欄固定填 `Claude`、`Codex` 或實際負責人姓名，方便回溯是哪個工具／人做的。

## Commit 紀錄

> 本表只代表本地 Git commit，不等同於已 push 或已部署。資料來源為 `git log --format="%h|%ad|%s" --date=short`；最近紀錄已於 2026-08-24 比對。git author 全部是 Robin 本人，因此「開發者」欄依 commit 內容與工作階段判斷。

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-09-05 | `85923bc` | 放寬待辦提醒視窗至 40 分鐘，避免 /healthz 飄移漏推 | Claude |
| 2026-09-05 | `9b3a20b` | 補回 e6a9fff／18bac52／88c31a4 commit hash 至 PROGRESS.md | Claude |
| 2026-09-05 | `e6a9fff` | 補記 Render 方向 A 被推翻，改採升級付費方案（方向 C） | Claude |
| 2026-09-01 | `18bac52` | 補記 Render 不休眠與不超額互斥、定案接受方向 A | Claude |
| 2026-09-01 | `88c31a4` | 補記 Render instance hours 逼近上限與 cronjob 自動停用事件 | Claude |
| 2026-08-24 | `b51c71d` | Mobile App 逾期待辦補抓已自動過期事項 | Claude |
| 2026-08-24 | `965755f` | Mobile App 逾期待辦日期判斷遺漏＋按鈕觸控熱區修正 | Claude |
| 2026-08-25 | `387eb66` | TOEIC 聽力題目庫改版——解答照片統一驅動、cutoff 切割、聽力題禁止顯示文字 | Claude |
| 2026-08-26 | `0a9719b` | 修正預定時間早於 08:00 的待辦收不到每日摘要推播 | Claude |
| 2026-08-26 | `3c95665` | 補記 0a9719b commit hash | Claude |
| 2026-08-26 | `58c0827` | 補記 Neon CU-hours 根因修正與決策紀錄 | Claude |
| 2026-08-26 | `79c0512` | 補記 58c0827 commit hash 並更新 30 分鐘決策 | Claude |
| 2026-08-26 | `77e221d` | 補記 31 天用量估算與家人加入使用的不確定性考量 | Claude |
| 2026-08-24 | `7c648a1` | 公司背景 CSV 涵蓋歷史缺漏、寄信失敗不拖累評分、職缺清單加空行 | Claude |
| 2026-08-24 | `126b9dd` | 補回職缺清單空行排版修改（7c648a1 漏掉的變更） | Claude |
| 2026-08-24 | `b6be6a4` | 記錄 126b9dd 修正過程與根因 | Claude |
| 2026-08-24 | `dc1e50c` | /healthz 排程檢查改共用單一資料庫連線（FR-21a） | Claude |
| 2026-08-24 | `44faef1` | 體態摘要綜合評估（限體重目標）＋職缺清單縣市篩選與排版改版 | Claude |
| 2026-08-24 | `179e068` | 職缺清單分頁、推薦門檻、爬蟲容錯、寄信改走 SendGrid、TOEIC 節流退避 | Claude |
| 2026-08-23 | `d83ce00` | 補回 FR-65a commit hash（PROGRESS.md 文件修正） | Claude |
| 2026-08-23 | `cb65652` | 新增 Mobile App 帳密登入連續錯誤鎖定與鎖定通知 | Claude |
| 2026-08-20 | `7d60368` | 補回 FR-41c commit hash（PROGRESS.md 文件修正） | Claude |
| 2026-08-20 | `07adf1f` | 職缺關鍵字設定支援多地區、清單顯示地區薪資與編輯功能 | Claude |
| 2026-08-19 | `c9f7611` | 補記 README 收尾版本（PROGRESS.md 文件修正） | Codex |
| 2026-08-19 | `37b3345` | 完成根目錄 README、最終跨頁回歸及文件現況收尾 | Codex |
| 2026-08-19 | `83db1ec` | 完成七個分析頁載入修正、收藏目標摘要及跨端成果置頂 | Codex |
| 2026-08-19 | `2f7de66` | 完成求職與考試分析頁及獨立頁載入修正 | Codex |
| 2026-08-19 | `e667a11` | 完成 Mobile 生活分析頁第二階段與實機回饋修正 | Codex |
| 2026-08-19 | `28ad29a` | 完成 Mobile 分析頁共用目標、紀錄與圖表基礎及逾期待辦處理 | Codex |
| 2026-08-19 | `c2b3d50` | 新增全目標手動完成、二次確認、權限防護、里程碑類型與一致完成狀態 | Codex |
| 2026-08-18 | `0fad51f` | 定案 Mobile 分析頁、共用目標摘要、成果置頂及求職／考試頁改版規格 | Codex |
| 2026-08-18 | `fb8c616` | 修正 Telegram 重構後 Mobile 功能開關、取消功能殘留、考試備註與關閉職缺分析規則 | Codex |
| 2026-08-18 | `005752b` | 跨平台系統錯誤管理選單化，納入 Mobile 5xx 事故、去重、受影響者與康復通知 | Codex |
| 2026-08-18 | `759fbf5` | 移除最後五個舊版 Slash Command、過時狀態機與相關測試，保留選單及陪聊自然語言入口 | Codex |
| 2026-08-18 | `b67cce0` | 補記 0084 Migration 修復 commit、測試與待部署狀態 | Codex |
| 2026-08-18 | `07e986a` | 修正 0084 重複新增 `exercise_logs.note`，補回歸測試並同步 migration 實際狀態 | Codex |
| 2026-08-18 | `1601f34` | 完成 FR-6c 草稿保護、固定別名入口與 FR-77 取消功能清理，新增經核准的 `0094` 刪表 migration | Codex |
| 2026-08-18 | `f7cd89c` | 定案 FR-6c 草稿保護細節，取消 NFR-14～NFR-15 架構遷移並保留 FR-77 清理範圍 | Codex |
| 2026-08-18 | `e78b01c` | 補記一般對話功能 commit 與排程設定推版驗收狀態 | Codex |
| 2026-08-18 | `5c0c093` | 限縮一般對話並完善圖片、語音、音檔與不支援格式防呆 | Codex |
| 2026-08-18 | `fe5f828` | 補記功能開關與排程設定提交紀錄 | Codex |
| 2026-08-18 | `669accc` | 功能開關與排程設定選單化，並統一目標與行程日期通知 | Codex |
| 2026-08-18 | `92dc623` | 補記康復通知 commit 與 push／實機驗收狀態 | Codex |
| 2026-08-18 | `e761deb` | 康復通知改為可選事故與收件人，並落地 Telegram／Email 送達狀態 | Codex |
| 2026-08-18 | `bde3731` | 補記考試設定選單化 commit 與驗收狀態 | Codex |
| 2026-08-18 | `20fd6c7` | 考試設定選單化：證照名冊、目標、每日／區間題數與正式考試紀錄 | Codex |
| 2026-08-18 | `6284e1c` | 補記求職設定選單化 commit 與推版狀態 | Codex |
| 2026-08-18 | `2c5da38` | 求職設定選單化與人工關閉覆寫 | Codex |
| 2026-08-18 | `1bba185` | 補記 Youtube 技術分享設定 commit 紀錄 | Claude |
| 2026-08-18 | `21f5131` | 批次4：新增「🔍 資料查詢」選單，複用 AppAnalyticsService 唯讀查詢（FR-9c／FR-9d） | Claude |
| 2026-08-17 | `27c8476` | 批次3＋批次3補做：六模組目標泛化＋🎯目標追蹤新選單，含記帳/收藏清單 Calendar 同步、飲食目標自動達成判斷、考試成績自動達成判斷 | Claude |
| 2026-08-17 | `a6fd474` | Phase 6 第二批 2h：運動紀錄改版（批次2，FR-47／FR-47a），新增全域運動類別表與兩段式同義詞合併，Telegram Bot／Mobile App 同步改版 | Claude |
| 2026-08-16 | `eabed3b` | Phase 6 第二批 2f：Telegram 待辦事項選單化（新增按鈕入口與摘要→二次確認、清單改按鈕標記完成/取消） | Claude |
| 2026-08-16 | `57619bb` | 文件治理：AGENTS.md／AGENTS-TEMPLATE.md 新增「Commit → 推版 → 部署後續」Workflow | Claude |
| 2026-08-16 | `a400f36` | Phase 6 第二批 2e：Telegram 成果展示選單流程（新增 `src/bot/achievements.py`） | Claude |
| 2026-08-16 | `f0f7349` | 修復 2c 遺留、與心情運動相關的既有測試（函式簽章/已移除函式未同步） | Claude |
| 2026-08-16 | `9932732` | Phase 6 第二批 2d 補修：Telegram 收藏補上標記已造訪入口，修復探索地圖無法顯示標記 | Claude |
| 2026-08-16 | `bf715ff` | Phase 6 第二批 2d：Telegram 收藏與旅遊選單流程（新增/bot/collections.py、trips.py） | Claude |
| 2026-08-16 | `8d0ba92` | Phase 6 第二批 2c：Telegram 日常紀錄心情、運動全面改選單觸發 | Claude |
| 2026-08-16 | `f921230` | Phase 6 第二批 2b：Telegram 重要日子選單流程（新增／編輯／刪除／清單） | Claude |
| 2026-08-15 | `f623566` | Phase 6 第二批 2a：Telegram 按鈕選單與 /start 認證流程 | Claude |
| 2026-08-15 | `996c603` | 修正 /set_invite_codes 因 0083 NOT NULL 迴歸 | Claude |
| 2026-08-15 | `4740d00` | Phase 6 第一批：通關密碼到期與鎖定、使用者停用機制 | Claude |
| 2026-08-15 | `d13c390` | 定案 Telegram 重構、權限管理與功能取消，同步 8/15 部署驗收 | Claude |
| 2026-08-14 | `67ef251` | 修正重要日子家庭成員查詢與求職分析載入 | Codex |
| 2026-08-14 | `b3f165a` | 同步目標日期並修正 Mobile App 重要日子相關問題 | Codex |
| 2026-08-14 | `4760689` | 完善 Mobile 收藏地點選擇、固定捲動、旅遊行程與重要日子同步 | Codex |
| 2026-08-14 | `bff8679` | 改善收藏地址定位並修復已造訪與刪除操作 | Codex |
| 2026-08-14 | `b2e3362` | 完成 Mobile App 探索地址定位、快取與重新定位 | Codex |
| 2026-08-14 | `c514b17` | 完成 Mobile App 收藏、旅遊行程、探索地圖與成果展示 Phase 5 | Codex |
| 2026-08-14 | `84960d2` | 擴充 Mobile App 飲食與運動紀錄模式 | Codex |
| 2026-08-14 | `d84222f` | 正式取消 App 三項設定功能 | Codex |
| 2026-08-14 | `fb62163` | 統一開發與文件治理規則 | Codex |
| 2026-08-14 | `ec36062` | 補齊待討論、已取消與擱置項目 | Codex |
| 2026-08-14 | `b991323` | 補齊正式技術棧資訊 | Codex |
| 2026-08-14 | `55177ad` | 整併規格與文件架構 | Codex |
| 2026-08-13 | `3160b14` | 記錄 PWA icon/縮放/SPA 路由修正過程，補充 FR-65c 保持登入在 Web 版的已知限制 | Claude |
| 2026-08-12 | `4f7bfd3` | 修正 web.output 改為 static，讓 +html.tsx 的 icon/manifest/viewport 設定真正生效 | Claude |
| 2026-08-12 | `ed644f3` | Web 版加入 App icon、manifest，加入主畫面時使用真正的羅賓森頭像並支援全螢幕模式 | Claude |
| 2026-08-12 | `341df03` | 修正 Vercel SPA 路由：直接開啟 /login 等網址時 fallback 回 index.html | Claude |
| 2026-08-12 | `0e8ccd3` | Vercel 設定相關紀錄 | Claude |
| 2026-08-12 | `167624f` | 修正 .gitignore：補回被誤擋的 mobile/tsconfig.json，新增 Vercel 部署設定 | Claude |
| 2026-08-12 | `b8beff4` | Step 4.4/4.5：Mobile App「羅賓森」登入/選單/個人資訊/APP設定/唯讀分析/體態飲食記錄完工 | Codex |
| 2026-08-10 | `3d6b313` | Mobile App 剩餘待確認事項定案（純規格文件，尚未開工） | Claude |
| 2026-08-10 | `b3e3b61` | 規劃首頁新增「體重紀錄」卡片（純規格文件，尚未開工） | Claude |
| 2026-08-10 | `7b2ec5d` | 實作 FR-53f（重要通知邏輯修正）與 FR-19j（系統錯誤記錄與解法追蹤） | Claude |
| 2026-08-10 | `e890a77` | 每日技術分享改回深入摘要、拆成三則獨立訊息，修正 IThome RSS 解析 bug（ADR-29） | Claude |
| 2026-08-09 | `c84d037` | Step 4.3：應徵成效追蹤＋外部管道職缺（FR-39、FR-40，ADR-27） | Claude |
| 2026-08-09 | `76f449b` | docs: Step 4.3 外部職缺資料結構改用 source 欄位共用同一張表（ADR-27 決策 5/6 修正） | Claude |
| 2026-08-09 | `6570a99` | docs: Step 4.3（應徵成效追蹤）開工前規格定案，新增 ADR-27 | Claude |
| 2026-08-09 | `223f617` | Step 4.2：Gemini 契合度評分＋技能缺口分析＋雙重排名 Excel 交付（FR-37、FR-38，ADR-26） | Claude |
| 2026-08-09 | `c860275` | docs: Step 4.1 收尾、Step 4.2 開工前置依賴解除 | Claude |
| 2026-08-09 | `22ec966` | feat(job104): 新增 job_postings.is_closed 自動判斷欄位 | Claude |
| 2026-08-09 | `ae92792` | fix(job104): 依 Robin 回饋移除產業篩選、地區篩選改為子字串比對 | Claude |
| 2026-08-09 | `64eb691` | fix(job104): 依真實 API 驗證修正欄位對照與端點路徑 | Claude |
| 2026-08-09 | `1774e06` | Step 4.1 Phase C-F：完成 FR-34 爬蟲＋FR-35 公司背景協作＋週排程掛載，Step 4.1 全數完工 | Claude |
| 2026-08-09 | `a40560e` | Step 4.1 Phase B：新增求職模組 FR-33/FR-36 對話式收集流程 | Claude |
| 2026-08-09 | `eda9054` | Step 4.1 Phase A：新增求職模組 DB schema（users 欄位＋job_search_criteria／job_companies／job_postings 三張新表，見 ADR-24） | Claude |
| 2026-08-09 | `981d41c` | Step 4.2 開工前規格定案：新增 ADR-26，修正 FR-36 歸屬、重寫 FR-37/FR-38 | Claude |
| 2026-08-09 | `1ddf9d2` | 修正每日技術成長摘要：改為一天多筆、一筆一個來源管道（source 正規化，ADR-25） | Claude |
| 2026-08-08 | `61c4514` | Step 3.5 完成：好友模式陪伴聊天（FR-51、FR-52、ADR-22） | Claude |
| 2026-08-08 | `521280b` | Step 3.4 完成：YouTube 技術情報模組（FR-57～FR-59、ADR-21） | Claude |
| 2026-08-08 | `74e2b93` | Step 3.3 剩餘範圍全數完成：FR-29 成效彈性文字問答、FR-24 目標設定與方向建議、FR-30 正式成績記錄 | Claude |
| 2026-08-08 | `b83cf33` | Step 3.3: 證照題庫作答與批改流程 + 20:00 提醒 + 彈性排程對話流程（FR-27/FR-28） | Claude |
| 2026-08-08 | `1986550` | 體態管理新增腰圍設定（FR-46）+ Phase 4 藍牙體重計規格（FR-64a） | Claude |
| 2026-08-08 | `93e0e93` | SPEC.md：彈性排程新增第四種語意「平攤到鄰近幾天」（ADR-20 決策 5/6） | Claude |
| 2026-08-08 | `be180b9` | Step 3.3：每日 08:00 推播出題機制（FR-26，ADR-20） | Claude |
| 2026-08-08 | `20fbce6` | PROGRESS.md：記錄 production 事故已確認解決（migration 全套用 + healthz 修復上線） | Claude |
| 2026-08-08 | `e799198` | 修復 production 事故根因：CloudSQLClient.execute() 的 IndexError | Claude |
| 2026-08-08 | `8b093ed` | 修復 production 事故：/healthz 逾時（改背景執行緒跑排程檢查） | Claude |
| 2026-08-07 | `fd63b96` | Step 3.3 第一階段：答案照片比對機制（FR-27 部分）+ 新資料表 | Claude |
| 2026-08-07 | `3737562` | 證照題庫泛用化：exam_type 不寫死清單，toeic_questions 改名 certificate_questions | Claude |
| 2026-08-07 | `ed48543` | Step 3.2 修正：整包 MP3 切割自動判斷開頭有無作答說明語音 | Claude |
| 2026-08-07 | `75ffcfb` | Phase 3 Step 3.2 完成：TOEIC 雙軌題庫 Pipeline（FR-24、FR-25a～FR-25f） | Claude |
| 2026-08-07 | `7a128fe` | 功能開關拆分：skill_growth 拆成 tech_intel／certificate／language | Claude |
| 2026-08-07 | `b2114b3` | docs: 更新 PROGRESS.md，GEMINI_API_SKILL_GROWTH_KEY 已由 Robin 設定完成 | Claude |
| 2026-08-07 | `d618493` | Step 3.1 修正：每日技術分享拆成 23:00 收集／08:00 推播兩階段 | Claude |
| 2026-08-07 | `a783d5c` | feat: 每日重點技術分享（FR-22、FR-23，Step 3.1） | Claude |
| 2026-08-07 | `4a82136` | feat: 例外分級降級與決策執行狀態閉環回饋（FR-19f~FR-19h，Step 2.6） | Claude |
| 2026-08-07 | `31747f8` | feat: 外部 API 重試機制（FR-19i，Step 2.5） | Claude |
| 2026-08-07 | `9478dc8` | feat: Telegram 故障 email 備援通知 + Google Calendar 整合（ADR-16、Step 2.7） | Claude |
| 2026-08-05 | `2077991` | feat: 重要通知模組（FR-53，Step 2.3） | Claude |
| 2026-08-04 | `8870b21` | docs: 移除 Notion 後台規劃，改採 Mobile App（React Native + Expo） | Claude |
| 2026-08-04 | `9410113` | feat: 體態管理模組（FR-45~FR-48，Step 2.2） | Claude |
| 2026-08-04 | `23b291e` | feat: 記帳月底自動月報推播（FR-44a） | Claude |
| 2026-08-04 | `488511f` | fix: 個資遮蔽語意層暫時性外部錯誤導致整則訊息完全無回覆 | Claude |
| 2026-08-04 | `71ab515` | feat: 記帳模組擴充（FR-41a 預算特殊月份覆蓋、FR-42a 每日記帳提醒） | Claude |
| 2026-08-04 | `5be3360` | feat: 記帳模組（FR-41～FR-44） | Claude |
| 2026-08-02 | `68e88cb` | feat: 心情小記支援補記/更新/刪除（FR-49 擴充） | Claude |
| 2026-08-02 | `73b7e12` | feat: 待辦事項支援時間區間（FR-31b） | Claude |
| 2026-08-02 | `9045697` | fix: 修正話題轉移誤判為拒絕 + 待辦時間擅自猜測 + 8點提醒承諾邏輯錯誤 | Claude |
| 2026-08-02 | `4855bb6` | fix: webhook 空字串回覆防呆，修正「完全不理我」bug | Claude |
| 2026-08-02 | `47693e3` | Phase 1 Step 1.9：客訴收集模組（FR-60~63），Phase 1（MVP）全數完成 | Claude |
| 2026-08-02 | `837e8c1` | Phase 1 Step 1.8：心情小記模組（FR-49/FR-50） | Claude |
| 2026-08-02 | `0168774` | Phase 1 Step 1.7：待辦事項模組（FR-31/FR-31a/FR-32） | Claude |
| 2026-08-02 | `c192cef` | 保留 GDRIVE_KEY_FILE_PATH 於 .env.example（Robin 指示保留） | Claude |
| 2026-08-02 | `da9efa0` | Phase 1 Step 1.6：基礎錯誤處理層（FR-19a/FR-20/FR-21） | Claude |
| 2026-08-02 | `9dcf656` | gdrive 改用 OAuth 2.0（真人帳號身分），修正 storageQuotaExceeded | Claude |
| 2026-08-02 | `88d36af` | Phase 1 Step 1.5：個資偵測與遮蔽機制（FR-13） | Claude |
| 2026-08-02 | `5680aa1` | 修正 Telegram send_text 400 錯誤，排查語音功能 gdrive 金鑰路徑問題 | Claude |
| 2026-08-02 | `74ea671` | 語音成功轉出文字後附註 FR-15 修正窗口提醒 | Claude |
| 2026-08-02 | `af30855` | feat(voice): 補上 FR-14 規則 1，單次語音超時觸發 15 分鐘全面鎖定 | Claude |
| 2026-08-02 | `77bc0d9` | fix(chat-core): 最終確認狀態的語音一律短路，避免浪費 Drive/Groq 額度 | Claude |
| 2026-08-02 | `0cc39bb` | feat(chat-core): 新增語音最終執行確認關卡，防聽錯誤觸不可逆操作（FR-16a） | Claude |
| 2026-08-01 | `81b821d` | fix(voice): 補上 message.audio（上傳音檔）支援，修正 Step 1.4 範圍缺口 | Claude |
| 2026-08-01 | `60efdb3` | Phase 1 Step 1.4：語音轉文字流程（FR-14、FR-15） | Claude |
| 2026-08-01 | `6c254b7` | 新增主動記知識功能（FR-11）與 /clean-target-dialog（FR-12），見 ADR-8 | Claude |
| 2026-08-01 | `bde5d5f` | 修正四個測試回報問題：刪除確認、誠實性、寵物資料、反問誤觸發 | Claude |
| 2026-08-01 | `afacabc` | 修正代名詞指涉優先順序 bug：跳回更早提過的人而非最近點名的人 | Claude |
| 2026-08-01 | `f249571` | 新增打字誤植先確認機制、回答精簡規則、/clean-all-dialog 指令 | Claude |
| 2026-07-31 | `89f4386` | 修正 pending_user_knowledge 三個邏輯漏洞（ADR-6，部分 supersede ADR-5） | Claude |
| 2026-07-31 | `12c4afa` | 新增家庭成員知識庫：范焞琪（母親范麗芳的親妹妹，Robin 的阿姨） | Claude |
| 2026-07-31 | `59d04b2` | 修正代名詞指涉錯誤：問小布丁幾歲被誤答成爺爺年齡 | Claude |
| 2026-07-31 | `577894e` | 修正家人知識庫民國年換算錯誤（小布丁生日年答錯 2013 應為 2024） | Claude |
| 2026-07-31 | `6830307` | 修正日期幻覺：prompt 注入伺服器真實日期，加強禁止捏造事實規則 | Claude |
| 2026-07-31 | `a5aa56a` | 移除 Google Search grounding，查無答案改誠實回報不知道（ADR-5/ADR-8） | Claude |
| 2026-07-31 | `ef50dbe` | 修正 ADR-7：_SEARCH_MODEL 改為 gemini-2.5-flash | Claude |
| 2026-07-31 | `0db2196` | generate_with_search 固定改用 gemini-2.5-flash-lite（ADR-7） | Claude |
| 2026-07-31 | `2386e2d` | LLMClient 預設模型改為 gemini-3.5-flash-lite（ADR-6） | Claude |
| 2026-07-31 | `4b039ef` | Step 1.3b: 影像辨識基礎流程（FR-17、ADR-13） | Claude |
| 2026-07-31 | `659d2ff` | db: 新增 media_uploads 表（Step 1.3b 影像辨識前置作業） | Claude |
| 2026-07-31 | `853e0ed` | feat: 加強額度防呆 — update_id 去重 + LLMClient 本地端節流保護 | Claude |
| 2026-07-31 | `987b689` | fix: webhook 加最小安全網，防止 Telegram 重試風暴燒 Gemini 額度 | Claude |
| 2026-07-31 | `84521d6` | feat: Step 1.3a /function 改版 — 總覽 + 按需深入 + 情境範例（FR-9/ADR-4） | Claude |
| 2026-07-31 | `e16d685` | spec: 補上待辦事項/求職/體態管理/心情小記情境範例（FR-56e~h） | Claude |
| 2026-07-31 | `60e9e6a` | 長記憶（滾動式摘要）：對話核心新增 ADR-3，記憶架構補齊四部分 | Claude |
| 2026-07-31 | `27ae0b1` | 新增 conversation_summaries 表（長記憶滾動摘要，Robin 核准 ADR-3 建表 SQL） | Claude |
| 2026-07-31 | `5e8c347` | Phase 1 Step 1.3 完成：Gemini 對話核心（知識庫問答、資安隔離、人格化語氣） | Claude |
| 2026-07-30 | `75c4bf3` | Phase 1 Step 1.2 完成：功能開關系統（/my_toggles、/set_toggle） | Claude |
| 2026-07-30 | `ad246d2` | 新增 FR-2a：Step 1.2 功能開關權限模型（使用者可自管、Owner 可代管） | Claude |
| 2026-07-30 | `1119a9b` | 更新 PROGRESS.md：紀錄 0006 migration 已套用成功 | Claude |
| 2026-07-30 | `cf48e16` | 多模態與人格化語氣大改版：新增 ADR-12/ADR-13、FR-17/FR-56 改版、三週時程延長 | Claude |
| 2026-07-30 | `573c1c6` | Phase 1 Step 1.1: passcode auth, owner setup flow, /rule /function | Claude |
| 2026-07-30 | `2d98bbe` | Mark Phase 0 fully complete: all 5 migrations confirmed applied on Render | Claude |
| 2026-07-30 | `2e461da` | Record Step 0.5 first-batch migration push in SPEC.md/PROGRESS.md | Claude |
| 2026-07-30 | `e440b7c` | Add Phase 0 Step 0.5 first-batch DB migrations (ADR-10/ADR-11) | Claude |
| 2026-07-30 | `776802f` | Add Robinson product spec, submodules, schema docs, and Phase 0 infra | Claude |
| 2026-07-29 | `5f60602` | Chore: Remove all .DS_Store files recursively | Robin |
| 2026-07-27 | `fdc55a9` | fix: add flask to requirements.txt | Robin |
| 2026-07-27 | `d92b391` | fix: rename DockerFile to Dockerfile | Robin |
| 2026-07-27 | `9041aab` | chore: add initial project skeleton for deployment setup | Robin |
| 2026-07-27 | `91eff3b` | Initial commit | Robin |

## Push 紀錄

> Push 必須由 Robin 親自執行；本表只記錄已有明確證據的結果，不依本地 commit 狀態推測遠端狀態。

| 日期 | Branch／版本 | 遠端 | 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | `main`／`2f7de66`＋`99fc3a5` | GitHub | 完成 | 08/19 Robin 已推版並完成 Mobile 全部實機驗收；部署狀態未單獨回報 |
| 2026-08-19 | `main`／`e667a11`＋`557ec10` | GitHub | 完成 | 08/19 Robin 已推版並完成 Mobile 實機驗收；部署狀態未單獨回報 |
| 2026-08-18 | `main`／`759fbf5`＋`6ceed9d` | GitHub | 完成 | 08/18 Robin 已推版，並完成全部實機驗收 |
| 2026-08-18 | `main`／`07e986a`＋`b67cce0` | GitHub | 完成 | 08/18 Robin 已推版，Render 隨後成功套用 0084～0094 |
| 2026-08-18 | `main`／`1601f34`＋`0a857cc` | GitHub | 完成 | 08/18 Robin 已推版，並完成 Telegram 實機驗收；`origin/main` 已確認 |
| 2026-08-18 | `main`／`5c0c093`＋`e78b01c` | GitHub | 完成 | 08/18 Robin 已推版，並完成 Telegram 實機驗收 |
| 2026-08-18 | `main`／`669accc`＋`fe5f828` | GitHub | 完成 | 08/18 Robin 已推版，並完成 Telegram 實機驗收 |
| 2026-08-17 | `main`／`85db061` | GitHub | 完成 | 08/17 Robin已推版（含 `27c8476`／`85db061` 兩筆，六模組目標泛化＋批次3補做） |
| 2026-08-17 | `main`／`a6fd474` | GitHub | 完成 | 08/17 Robin 已推版；2026-08-18 DB 查核確認 migration 0084 當時未成功套用，先前紀錄已更正 |
| 2026-08-17 | `main`／`30c5303` | GitHub | 完成 | 08/17 Robin 已推版（隨 `a6fd474` 一併確認，`30c5303` 為其祖先 commit） |
| 2026-08-16 | `main`／`eabed3b` | GitHub | 完成 | 08/16 Robin 已推版 |
| 2026-08-16 | `main`／`57619bb` | GitHub | 完成 | 已由後續 `origin/main` 歷史確認為已推版 |
| 2026-08-16 | `main`／`a400f36` | GitHub | 完成 | 08/16 Robin已推版 |
| 2026-08-16 | `main`／`f0f7349` | GitHub | 完成 | 08/16 Robin已推版 |
| 2026-08-16 | `main`／`9932732` | GitHub | 完成 | 08/16 Robin已推版 |
| 2026-08-16 | `main`／`bf715ff` | GitHub | 完成 | 0816 Robin已推版 |
| 2026-08-16 | `main`／`8d0ba92` | GitHub | 完成 | 8/16 Robin 已推版（`git log origin/main` 已確認）；同日完成 Telegram 實機驗收 |
| 2026-08-16 | `main`／`479fae6` | GitHub | 完成 | 8/16 Robin 已推版（含 `f921230`／`479fae6` 兩筆，`git log origin/main` 已確認）；同日完成 Telegram 實機驗收 |
| 2026-08-15 | `main`／`f623566` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-15 | `main`／`996c603` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-15 | `main`／`4740d00` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-15 | `main`／`d13c390` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-14 | `main`／`67ef251` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`b3f165a` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`4760689` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`bff8679` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`b2e3362` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`c514b17` | GitHub | 完成 | Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`84960d2`＋`18a4ef7` | GitHub | 完成 | Robin 已確認功能 commit 與 PROGRESS 同步 commit 均已 push |
| 2026-08-14 | `main`／`fbb905a` | GitHub | 完成 | Robin 已確認 Push 紀錄同步 commit 已 push |
| 2026-08-14 | `main`／`1c8e836` | GitHub | 完成 | Robin 已確認本次兩筆 commit 均已 push |
| 2026-08-14 | `main`／`fb62163` | GitHub | 完成 | Robin 已確認 push |
| 2026-08-12 | `main`／Step 4.4～4.5 | GitHub | 完成 | 依當日正式上線里程碑紀錄 |

## 部署紀錄

| 日期 | 版本／範圍 | 環境 | 狀態 | 驗證 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 全目標手動完成（commit `c2b3d50`，migration `0096`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 push、部署並完成實機驗收；六類目標完成操作與二次確認正常 |
| 2026-08-18 | 舊 Slash Command 清理（commit `759fbf5`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 push 並完成全部實機測試；五個舊指令失效，替代選單與「陪我聊聊」入口正常 |
| 2026-08-18 | Migration 0084～0094 修復（commit `07e986a`） | Render 正式環境／Neon | 完成 | 12:25 Render 啟動紀錄確認 11 筆 migration 依序完成，服務正常啟動；0094 已執行取消功能資料表清理 |
| 2026-08-18 | FR-6c／FR-77（commit `1601f34`，migration `0094`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已完成程式流程實機驗收；0094 已於 12:25 成功套用 |
| 2026-08-18 | 功能開關與排程、康復通知、考試設定、一般對話 | Render 正式環境／Telegram 實機 | 完成 | Robin 已分批完成程式流程實機驗收；`0091`～`0094` 已於 12:25 成功套用 |
| 2026-08-17 | FR-47／FR-47a（運動紀錄改版批次2，commit `a6fd474`） | Render＋Vercel 正式環境／Telegram 實機＋Mobile 實體手機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-17 | FR-45／FR-46（日常紀錄－體態批次1，commit `30c5303`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-16 | FR-31／FR-31a／FR-31b／FR-32／FR-56e／FR-66a（Phase 6 第二批 2f，commit `eabed3b`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收（選單新增、自然語言入口、摘要確認按鈕、清單按鈕標記完成/取消、舊指令失效皆正常） |
| 2026-08-16 | FR-47／FR-49／FR-50（Phase 6 第二批 2c，commit `8d0ba92`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-15 | FR-3／FR-4／FR-4a～FR-4d／FR-5／FR-6a～FR-6e（Phase 6 第二批 2a，commit `f623566`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 `/start` 首綁與重複顯示主選單、Owner／非 Owner 按鈕差異、開發中項目回主選單按鈕、權限管理建立／停用／恢復／重發密碼四項操作、`/set_invite_codes` 已失效 |
| 2026-08-15 | FR-2～FR-4a～FR-4d（Phase 6 第一批，Migration 0083） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 `/set_invite_codes` 寫入正常、家人 Telegram 帳號輸入通關密碼綁定成功 |
| 2026-08-15 | FR-64／FR-65／FR-72a／FR-73～FR-76a | Render＋Vercel 正式環境／Mobile 實體手機 | 完成 | Robin 已確認重要日子與求職分析載入、收藏／旅遊／探索／成果、Nominatim 定位、相關 migration 與 Mobile 實機操作正常 |
| 2026-08-12 | Step 4.4～4.5 Mobile App 與後端 API | Render＋Vercel 正式環境 | 完成 | 依當日正式上線里程碑紀錄 |
