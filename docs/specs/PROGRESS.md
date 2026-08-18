---
updated: 2026-08-18
---


# 開發進度

> 本檔案整併自兩份舊紀錄：`docs/specs/_archive/robinson/PROGRESS.md`（Claude Code 協作的產品階段里程碑）與 `docs/specs/_archive/codex.md`（Codex 開發異動紀錄，內容集中在 Mobile App）。
> 「開發者」欄依內容來源判斷：Claude Code 協作里程碑標 `Claude`、codex.md 工作階段標 `Codex`、Claude Code 協作開始前由 Robin 自行完成的項目標 `Robin`。
> 除錯敘事（現象／根因／修復／驗證）已拆到 `docs/ADR/debug/`，決策脈絡已拆到 `docs/ADR/discuss/`，本檔只保留「哪一天、做了什麼、誰做的、狀態」。

## 時程與任務狀態

| 日期 | 對應 FR | 任務內容 | 開發者 | 狀態 | 備註 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-18 | FR-1～FR-4a／FR-6e～FR-6g／FR-20a／FR-72a／FR-74b | 功能開關與排程設定選單化：角色分流、三項 Owner 功能開關、個人通知開關、唯讀系統工作、統一重要日子／目標／旅遊日期發送器，並移除未記帳與未完成考題催促 | Codex | 已 commit（待 push／部署／實機驗收） | commit `669accc`（2026-08-18）。新增 `schedule_settings.py`、`scheduled_notifications.py`、migration `0093` 與對應測試；關閉通知不停止背景工作，關閉功能則停止整個功能。Codex `pytest -q`：1918 passed（1 項第三方 warning）；`ruff check .` 與 `git diff --check` 全數通過。 |
| 2026-08-18 | FR-19k／FR-20 | 系統事故收件與康復通知選單化：事故及 Robin Telegram→Email 備援送達狀態落地，Owner 先選事故、再勾選實際收過事故通知的家人，預覽後二次確認發送 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `e761deb`、文件 commit `92dc623`（2026-08-18）。Robin 已回報 push 並完成 Telegram 實機測試，結果正常；未另行回報 Render 部署狀態。 |
| 2026-08-18 | FR-24／FR-26／FR-30a～FR-30b／FR-6e | 考試設定選單化：主選單改名、證照名冊、目標／每日題數／正式考試紀錄四個子選單；TOEIC 固定三軌題數、非 TOEIC 尚無題庫提示、區間覆蓋不可重疊、正式成績補充內容 | Codex | 完成（已 push／實機驗收；部署狀態未單獨回報） | commit `20fd6c7`（2026-08-18）；文件 commit `bde3731`。Robin 已回報 push 並完成 Telegram 實機測試，結果正常。見 `docs/ADR/discuss/skill-growth.md` 2026-08-18 ADR-31。全專案 `pytest -q`：1921 passed（1 項第三方 `pydub` deprecation warning）；`ruff check .` 與 `git diff --check` 全數通過。 |
| 2026-08-18 | 求職 FR-41／FR-41a | 「💼 求職分析」改為「💼 求職設定」並接上 `job_search:*` 選單：履歷／期望工作內容獨立編輯與二次確認清空、必要條件三欄位分段設定、職缺關鍵字新增與二次確認刪除、依分數排序的唯讀職缺清單、已應徵／面試／Offer 清單與四種狀態切換、全部職缺的人工關閉／重新開啟，以及既有其他平台職缺流程改由按鈕進入；移除舊 Slash Command、文字觸發詞與 `ID=...職缺...` 文字狀態更新。新增 migration `0090_add_job_posting_manual_closed_override.sql`，人工關閉覆寫旗標為 TRUE 時，週爬蟲不覆寫 `is_closed` | Codex | 完成（已推版／實機驗收） | commit `2c5da38`（2026-08-18）；Robin 已完成 push，Render 已隨 push 部署，並完成 Telegram 實機驗收且結果正常。Robin 於 2026-08-18 本機執行 `pytest -q`：1922 passed（僅 1 項第三方 `pydub` deprecation warning）；`ruff check .`：全數通過。求職相關測試：250 passed。DB Schema Reference 已同步；完整互動決策見 `docs/ADR/discuss/job-search.md` 2026-08-18 補充段落。 |
| 2026-08-18 | FR-5／FR-6e／FR-57a | 兩項 Robin 直接核准的變更：①「使用規則」文字改為 Robin 逐字核准的最終版本（`src/bot/templates.py` `APPENDIX_A_TEXT`，隱私承諾「聊天記錄」改「日常紀錄」）②主選單「💡 Youtube 技術分享設定」（原「💡 技術分享」）從 `_NOT_YET_IMPLEMENTED_KEYS` 移除，接上新的 `youtube_settings:*` 子選單（`src/bot/commands.py`／`src/bot/router.py`），比照 `collections.py`／`achievements.py` 單層選單＋按鈕式二次確認刪除模式；主題數量上限 `youtube.MAX_TOPICS`＝5（達上限隱藏「➕ 新增主題」按鈕＋`add_topic()` 內同步擋下雙重保護），移除改「選主題→✅ 確認移除／❌ 取消」二次確認才真正刪除；舊文字觸發詞（`/my_youtube_topics`／`/add_youtube_topic`／`/remove_youtube_topic` 及中文別名）與對應舊處理函式全數移除 | Claude | 完成（已 commit，尚未推版） | commit `aa240e9`；push／部署狀態待 Robin 執行；完整設計內容見 `docs/ADR/discuss/youtube-intel.md` 2026-08-18「`tech_intel` 主選單按鈕接上 YouTube 主題設定子選單」條目、`docs/ADR/discuss/robinson.md` 2026-08-18「「使用規則」文字模板由 Robin 逐字稿核准＋「技術分享」選單更名接上 YouTube 主題訂閱設定」條目；改寫／新增 `tests/bot/test_templates.py`（逐字比對新版 `APPENDIX_A_TEXT`）、`tests/bot/test_youtube.py`（`add_topic()` 新增 `limit_reached` 欄位斷言、新增 `test_add_topic_limit_reached`）、`tests/bot/test_youtube_topic_commands.py`（整份改寫測新函式）、`tests/bot/test_router.py`（移除 3 項測舊文字觸發詞的過時測試，新增 3 項測 `menu:tech_intel`／`youtube_settings:*` callback 流程的整合測試）；Robin 本機執行 `ruff check .`（本次異動檔案）全過、`pytest -q` 首輪 18 failed（3 項為測試舊文字觸發詞的過時測試，因該行為本批已刻意移除而觸發下游 fallback 邏輯噴錯、非既有回歸；其餘 15 項為 `test_templates.py`／`test_youtube.py`／`test_youtube_topic_commands.py` 未同步本次文字與函式異動），改寫測試後第二輪 2 failed（`test_router.py` 2 項新增測試自身斷言誤把 tuple 回傳值當字串比對、誤判移除清單文字在訊息本文而非按鈕文字），修正後**全數通過**；`docs/reference/` 未異動（本批未變更 DB Schema／API，`youtube_topics` 資料表結構不變）|
| 2026-08-18 | FR-9c／FR-9d | 批次4「🔍 資料查詢」實作完成：新增 `src/bot/query.py`，直接複用 Mobile App 既有 `AppAnalyticsService` 各模組唯讀查詢方法，不重寫查詢邏輯；可查範圍限定 7 個有日期區間概念的模組（待辦／體態分析／記帳／心情／技術分享／求職分析／考試成績），重要日子／收藏與旅遊／成果展示／目標追蹤維持只能從各自主選單查看；流程為選最終日期（快速按鈕「今天」「昨天」，或打字走 LLM 判斷 CLEAR／UNCLEAR，明確允許未來日期）→ 系統自動往前推 6 天組出最多 7 個曆日區間 → 模組複選 →「🔍 開始查詢」；查詢結果逐日列出區間內全部日期，沒有紀錄的日子顯示「查無紀錄」，每筆紀錄的欄位不寫死固定樣板改依實際欄位動態呈現；多模組查詢依模組分則 Telegram 訊息送出（避開 4096 字元上限），沒有 `telegram_client` 時優雅降級成合併一則訊息；`privacy_mask_enabled=True` 時把數字欄位逐位替換成 `*`；`menu.py` 把 `query` 移出 `_NOT_YET_IMPLEMENTED_KEYS`，新增 `QUERY_MODULES`；`router.py` 新增 `menu:query`／`query:*` 分派與 `pending_query_date` 文字流程分派 | Claude | 完成（已 commit，尚未推版） | 完整設計內容與使用者確認脈絡見 `docs/ADR/discuss/robinson.md` 2026-08-18「批次4『🔍 資料查詢』開工前 SDD 計畫確認」；沿用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路）；完整 `python3 -m pytest -q`：**1912 個測試全過**（原 1897 個 baseline 全過，新增 15 個：`tests/bot/test_query.py` 全新 15 項；另 `tests/bot/test_menu.py` 新增 1 項、`tests/bot/test_router.py` 既有 2 項斷言隨規格變動改寫）；`ruff check .` 對本次異動檔案全過（既有 `tests/services/test_app_life_exploration.py` 14 項 E701/E702 是本批之前就存在的既有技術債，非本次異動範圍）；`docs/reference/` 未異動（本批未變更 DB Schema／API，純複用既有 `AppAnalyticsService`）；commit `21f5131`，push／部署狀態待 Robin 執行 |
| 2026-08-18 | FR-41～FR-44 | 批次5「💰 記帳」按鈕化＋摘要確認實作完成：日常紀錄五個子項目（心情／運動／飲食／體態／記帳）至此全數改版完畢，`_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS` 清空。子選單 `commands.start_finance_menu()`（設定預算／新增記帳／補記記帳／我的記帳紀錄／我的記帳摘要／🎯 目標／🔙 返回）；新增／補記記帳的 type→category→amount→note 四輪反問後改為先組摘要（類型／分類／金額／備註／日期）＋「✅ 確認送出」／「❌ 取消」按鈕，`finance:confirm_save` 才真正寫入 `transactions`（取代原本 note 步驟直接寫入）；「我的記帳紀錄」改按鈕式清單（每筆「✏️ 編輯」`finance:edit:<id>`／「🗑 刪除」`finance:delete:<id>`，刪除走二次確認按鈕重新驗證擁有者），取代原本「輸入編號→LLM 分類更新或刪除→LLM CONFIRM/CANCEL」三段式文字流程；預算月份覆蓋確認（全局預設／某幾個月覆蓋值）從自由文字 LLM CONFIRM/CANCEL 改成 ✅ 確認覆蓋／❌ 取消按鈕（`finance:budget_confirm_save`／`finance:budget_override_confirm_save`）；移除全部 7 組舊文字觸發詞常數（`_FINANCE_SET_BUDGET_TRIGGERS` 等），目標入口併入子選單「🎯 目標」按鈕沿用批次3既有 `_dispatch_module_goal_callback()`；記帳分類／類型／幣別與 `finance.py` 純邏輯層本批未異動 | Claude | 完成（已 commit，尚未推版） | 完整設計內容與使用者確認脈絡見 `docs/ADR/discuss/robinson.md` 2026-08-18「批次5『💰 記帳』按鈕化＋摘要確認開工前 SDD 計畫確認」；沿用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路）；完整 `python3 -m pytest -q`：**1913 個測試全過**（原 1912 個 baseline，`tests/bot/test_commands.py`／`tests/bot/test_router.py`／`tests/bot/test_menu.py` 既有記帳相關測試改寫成按鈕/確認流程斷言，`tests/bot/test_goal_tracking_router.py` 三項記帳目標文字觸發詞測試改成 `finance:goal:new` callback 觸發，淨增 1 項新選單快照測試）；`ruff check .` 對本次異動檔案全過（既有 `tests/services/test_app_life_exploration.py` 14 項 E701/E702 是既有技術債，非本次異動範圍）；`docs/reference/` 未異動（本批未變更 DB Schema／API）；commit `3a5d54a`（10 files changed, 522 insertions/383 deletions），push／部署狀態待 Robin 執行 |
| 2026-08-17 | FR-41b／FR-73a／FR-48／FR-24a | 批次3補做「不得漏做的三項功能」：①記帳／收藏清單目標補上 Google Calendar 同步問句——`module_goals` 新增 `sync_to_calendar`／`google_calendar_event_id` 欄位（migration 0088），`goals.py` 新增 `set_calendar_event_id()`，`commands.py` 新增 `handle_module_goal_calendar_sync_step()`（比照 `body.py` 既有 `handle_goal_calendar_sync_step()`），`router.py` 新增 `pending_module_goal_calendar_sync` 流程分派並把 `calendar_client` 一路串到 `finance:`／`collections:` 分支；②飲食目標補上自動達成判斷——解決「以上/以下方向不明確」問題：`body_goals` 新增 `target_direction` 欄位（migration 0089），`goal_parser.py` 的 `_parse_diet()` 讓 LLM 一併判斷 MIN／MAX 方向，`body.py` 新增 `_diet_cumulative_value()`／`check_and_push_diet_goal_achievements()`，`main.py` `/healthz` 串接；③考試成績自動判斷——`certificate_goals.py` 新增 `check_score_achievement()`，`commands.handle_exam_score_value_step()` 記錄實際成績後立即比對 `target_score`，達標附加恭喜文字 | Claude | 完成（已推版，尚未部署） | 起因：Robin 對批次3原始交付的「已知的刻意簡化」三項明確表達不接受，要求全部補做，見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3補做：不得漏做的三項功能」；沿用雲端沙箱跑滿整套測試流程；完整 `python3 -m pytest -q`：**1897 個測試全過**（原 1878 baseline 全過，新增 19 個：`tests/bot/test_goals.py` 新增 2 項 Calendar 同步、`tests/bot/test_body.py` 新增 4 項飲食目標達成判斷、`tests/bot/test_certificate_goals.py` 新增 7 項成績比對、`tests/bot/test_certificate_exam_scores_commands.py` 新增 2 項整合、`tests/bot/test_goal_tracking_router.py` 新增 1 項記帳目標 Calendar 同步全流程整合，另有既有測試調整為新的預設值斷言）；`ruff check .` 全過；MAX 方向飲食目標若沒有設定期限，數學上沒有「結束邊界」可判斷是否超標，暫時無法自動判斷（設計上的真實限制，非偷懶簡化，已在 SPEC.md FR-48 明確寫出）；`docs/reference/db_schema.md`／SPEC.md 已同步新欄位；commit／push／部署狀態待 Robin 執行 |
| 2026-08-17 | FR-45a／FR-41b／FR-73a／FR-24a／FR-48 | 批次3「六模組目標泛化＋🎯 目標追蹤新選單」實作完成：新增 3 支 migration（0085 `module_goals` 通用目標表／0086 `goal_summaries` 每日摘要快取表／0087 `body_goals.target_unit` 欄位）；新增 `src/services/goal_parser.py`（方案A LLM 輔助解析目標值/單位）、`src/services/goal_summary_job.py`（每日 01:00 排程，掃描 `body_goals`／`module_goals`／`certificate_goals` 三來源生成快取摘要）、`src/bot/goals.py`（`module_goals` 通用 CRUD＋記帳/收藏清單達成判斷）；`goal_important_day_sync.py` 新增 `sync_module_goal()`；`menu.py` 新增「🎯 目標追蹤」主選單項目與 `GOAL_TRACKING_MODULES`；`commands.py` 新增 `start_module_goal_*`／`handle_module_goal_*`／`start_goal_tracking_*` 系列函式；`router.py` 新增 `finance:goal:*`／`collections:goal:*`／`goal_tracking:*` 分派與共用的 `_dispatch_module_goal_callback()`；`finance.py` 新增指令觸發詞 `/finance_goal`／`/my_finance_goals`，`handle_transaction_note_step()` 寫入交易後檢查目標達成；`collections.py` 子選單新增「🎯 目標」按鈕，標記造訪後檢查目標達成；`body.py` 的 `create_goal()`／`update_goal()` 支援 `target_unit`，飲食目標新增流程接上方案A解析；`main.py` `/healthz` 新增 `_check_module_goal_deadline_reminders()`／`_check_goal_summaries()` 兩個排程檢查（共 16 個） | Claude | 完成（已推版，尚未部署） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3：六模組目標泛化＋🎯 目標追蹤新選單 實作完成」；沿用批次1／批次2「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路，見 `docs/ADR/debug/robinson.md`「Sandbox network limits」），**不是只做語法驗證**；完整 `python3 -m pytest -q`：**1878 個測試全過**（原 1844 baseline 全過，新增 34 個：`tests/services/test_goal_parser.py` 9 項、`tests/services/test_goal_summary_job.py` 7 項、`tests/bot/test_goals.py` 13 項、`tests/bot/test_goal_tracking_router.py` 7 項路由整合測試，另擴充 `tests/bot/conftest.py`／`tests/bot/test_collections.py` 支援新表）；`ruff check .` 全過；**已知的刻意簡化**：①記帳/收藏清單目標新增流程省略 Google Calendar 同步問句（body.py 才有，理由見設計文件）②飲食目標（FR-48 方案A）本批只做結構化欄位解析與儲存，暫不新增自動達成判斷（語意是「以上」還是「以下」不明確，例如熱量控制在X以內是上限、蔬菜攝取X次是下限，需要更明確規則才能安全自動判斷）③考試目標（FR-24a）整合進🎯目標追蹤但不新增自動達成判斷（無應考結果資料可供判斷）；`docs/reference/db_schema.md` 已同步新表／新欄位；commit／push／部署狀態待 Robin 執行 |
| 2026-08-17 | FR-47／FR-47a | 運動紀錄改版（批次2）實作完成：新增 `exercise_categories` 全域類別表（migration 0084，同批清空舊 `exercise_logs` 並改結構）；`body.py` 新增 `list_exercise_categories()`／`find_or_create_exercise_category()`（正規化比對＋LLM 語意判斷兩段式同義詞合併），改寫 `create_exercise_log()`／`update_exercise_log()`／`format_exercise_log_list()`；`commands.py`／`router.py` 運動流程全面改版為選類別→時長→心率（可跳過）→補充內容（可跳過）→AI／人工熱量二選一→摘要確認；`app_records.py` 同步改寫 exercise 驗證邏輯（`category_id`／`custom_category`／`use_ai_calorie`），新增 `GET /api/app/exercise-categories`（`app_analytics.py`）；Mobile `RecordModal.tsx` 改用 `SearchableSelect` 動態載入類別，移除雙頁籤與重訓特殊分支 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「運動紀錄改版（批次2）實作完成」；沿用批次1「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程（本機 `device_bash` 仍無網路），**不是只做語法驗證**；完整 `python3 -m pytest -q`：1844 passed（原 1842 baseline 全過，新增 2 項運動類別測試，改寫既有運動相關測試約 15 項）；`ruff check .` 全過；Mobile 端 `npx tsc --noEmit` 型別檢查通過（前端未設定 lint／單元測試 script）；`docs/reference/db_schema.md`／`api_schema.md` 已同步；commit（`a6fd474`）與 push 皆已完成，Render 已自動部署，migration 0084 已於開機時自動套用；Robin 已完成 Telegram Bot 與 Mobile App 實機測試 |
| 2026-08-17 | FR-45／FR-46 | Phase 6 第二批 2h（日常紀錄－體態）批次1實作完成：`body.py` 合理範圍收斂（身高 140～200 公分、腰圍 50～150 公分、體重新增上限 150 公斤）並新增動態範圍文案函式、`get_body_summary()`／`format_body_summary()`、`update_goal()`／`get_goal()`；`commands.py` 刪除六個舊指令（`/set_height`／`/set_waist`／`/log_weight`／`/backfill_weight`／`/my_weight_logs`／`/set_body_goal`），全面改選單按鈕＋摘要→二次確認，體重歷史清單改按鈕式編輯/刪除；目標子流程重寫成 `body:goal:*` 運動/飲食/體態三入口共用，支援多筆並存＋編輯/刪除；`menu.py` 把 `body` 移出開發中名單；`router.py` 新增 `body:*`／`_dispatch_body_goal_callback()` 分派，`_FINAL_CONFIRM_FLOWS` 新增 6 個新摘要確認 flow（涵蓋全站語音確認機制） | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-17「日常紀錄－體態（Phase 6 第二批 2h）實作完成」；本批因 Cowork 沙箱本機無網路裝不了套件，改用「打包整個 repo 進雲端沙箱、安裝完整依賴、跑滿整套測試」流程，**不是只做語法驗證**；完整 `python3 -m pytest -q`：1842 passed（原 1809 baseline 全過，新增/改寫 33 項體態相關測試）；`ruff check .` 全過；改寫 `tests/bot/test_body.py`／`test_body_commands.py`（大幅重寫）／`test_body_router.py`（大幅重寫）／`test_menu.py`／`test_router.py`；`docs/reference/` 未異動（本批未變更 DB Schema／API）；commit `30c5303`（11 files changed, 1400 insertions/614 deletions），Robin 已推版並完成 Telegram 實機驗收 |
| 2026-08-16 | FR-48 | 修復飲食補記日期解析 NameError（2g 部署後實機驗收發現）：`handle_diet_backfill_date_step()` 呼叫了不存在的 `_parse_date_description()`，輸入「昨天」等補記日期時直接噴錯 | Claude | 完成（已部署／實機驗收） | 根因與修復細節見 `docs/ADR/debug/robinson.md` 2026-08-16「飲食補記日期解析 NameError」；改用既有 `_parse_key_value_block`＋`_parse_date_only` 解析流程；新增 `tests/bot/test_body_commands.py` 回歸測試；順帶用 `pyflakes` 掃過 `src/bot/`／`src/services/` 全部模組確認無同類「呼叫未定義名稱」問題；commit `fb5e4e2`，Robin 已推版並完成 Telegram 實機驗收（新增今天飲食紀錄→補記昨天→輸入「昨天」正常） |
| 2026-08-17 | — | 純程式品質治理：清除 `ruff check .` 檢出的 99 個既有警告，並把「commit 前跑 `ruff check .`」記錄為固定開發慣例 | Claude | 完成（已部署） | 起因是上一筆飲食補記 NameError（`ast.parse` 語法檢查抓不到「呼叫未定義名稱」，靜態 Lint 才抓得到），Robin 要求記錄慣例並開獨立任務清掉既有警告；新增 `ruff.toml` 明確鎖定 isort `known-first-party = ["src", "submodules"]`（過程中發現同一 ruff 版本在 Robin 本機與 Claude 沙箱因無設定檔而判斷不一致，導致排序建議兩邊對不上，加了設定檔後才穩定一致）；`requirements-dev.txt` 新增 `ruff`；`AGENTS.md`／`docs/templates/AGENTS-TEMPLATE.md` 新增對應開發慣例段落；修正內容含 import 排序、7 處 `date.today()` 改時區感知寫法（DTZ011，均改用專案既有 `_TAIWAN_TZ`／`commands._now()` 模式）、2 處 DTZ007 經人工覆核確認為誤判改加 `# noqa` 註解說明（`important_days.py::_parse_hhmm()` 只取鐘面時刻與時區無關、`newsfeed/client.py::_parse_pub_date()` 下一行即補時區），其餘 RUF059／F841／RUF012／FLY002／FURB157／PIE810／ISC004／SIM117／SIM118 等規則修正，共 35+ 檔案；驗證：`ast.parse`／`pyflakes`／`ruff check .` 全過，Robin 本機 `pytest tests/ -q` 1806 passed／3 failed（僅既有 `test_toeic.py` 缺 `ffmpeg` 環境問題，與本次異動無關）；commit `6bd7540`，Robin 已推版（純程式品質改動，無對外行為變化，不需個別實機驗收） |
| 2026-08-17 | FR-45～FR-48 | Phase 6 第二批 2h（日常紀錄－體態）前置：拆批決策定案，分成①體態選單化②運動紀錄改版③六模組目標泛化三批，並定案體態範圍與運動改版細節 | Claude | 已定案／待開發 | 決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-17「日常紀錄－體態（Phase 6 第二批 2h）前置討論：範圍拆分與三批決策」；本篇純盤點與定案，尚未開工，各批仍需個別提出 SDD 實作計畫並等待確認 |
| 2026-08-17 | FR-45／FR-45a／FR-46／FR-47a／FR-48 | 依 Robin 要求，SPEC.md 提前改寫為體態/運動改版/目標追蹤的定案目標版本（尚未實作，條文內已標註「已定案、尚未實作」並附 ADR 連結） | Claude | 已定案／待開發 | 純文件同步，未動程式碼；DRAFT.md 無對應項目（已定案不屬於待討論範圍）、reference/ 未異動（尚無 Schema／API 變更） |
| 2026-08-16 | FR-48／FR-16b | Phase 6 第二批 2g（日常紀錄－飲食）＋全站語音確認機制程式碼撰寫完成：`menu.py` 把 `diet` 移出開發中名單；`commands.py` 全面改寫飲食（含飲水）區塊，single-daily 規則（一天各一筆，已有紀錄導向編輯）、新增流程先問飲水再問食物（各自可跳過）、食物文字/照片雙輸入（照片複用 `src/services/app_diet_photo.py`）、AI/人工營養素選擇（`nutrition_source`）、摘要→二次確認、按鈕式編輯/刪除；`body.py` 的 `create_diet_log()`／`format_diet_macro_note()` 補上 `nutrition_source` 參數，移除已無用的 `format_diet_entry_type_prompt()`／`resolve_diet_entry_type()`；`router.py` 新增 `diet:*` callback 分派、對應 pending flow 文字分支、`handle_photo_message()` 攔截 `pending_diet_photo` 走飲食辨識而非一般圖片分析，並移除 `/log_diet`／`/backfill_diet`／`/my_diet_logs` 舊觸發詞（不提供相容期）；同批一併完成全站語音確認機制：`handle_voice_message()` 轉錄成功後改成先貼出轉錄文字＋「✅ 正確，繼續」按鈕（`pending_voice_confirm`），確認或改用文字修正後才接回原本卡在的流程（`handle_callback_query()` 新增 `voice_confirm:accept`、`_dispatch_active_flow()` 新增 `pending_voice_confirm` 分支），影響範圍涵蓋既有所有語音入口（不限 2g 飲食）；`webhook.py` 同步更新語音/callback_query 分支的回傳值拆解與 Client 注入，並新增 `_build_bot_llm_clients_optional()` 優雅降級輔助函式取代 callback_query 分支原本無條件讀取環境變數的寫法 | Claude | 完成（已 commit，尚未推版／尚未部署） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2g」與 `docs/ADR/discuss/voice-safety.md` 2026-08-16「全站語音轉文字確認機制」；Claude 沙箱這次連 `ast.parse` 語法驗證都做了但**完全沒有跑 `pytest`**（沙箱本機 VM `device_bash` 沒有網路裝不了套件，雲端沙箱又缺完整依賴鏈，比照 2d／2e／2f 既有情況），改寫測試（`test_body.py`／`test_body_commands.py`／`test_body_router.py`／`test_menu.py`／`test_router.py`／`test_webhook.py`）同樣只做語法驗證與人工比對既有慣例；Robin 本機執行完整 `python3 -m pytest tests/ -q` 首輪回報 18 failed／1791 passed，15 項為本批異動（`webhook.py` 一個 `GEMINI_API_BOT_KEY` KeyError＋14 項測試斷言未同步新函式簽章／新語音兩段式確認流程），3 項為既有 `test_toeic.py` `ffmpeg` 環境問題（與本批無關）；Claude 修正 `webhook.py` 並改寫上述 6 個測試檔後，Robin 重跑 `python3 -m pytest tests/ -q` 回報 1805 passed／3 failed（僅剩既有 `ffmpeg` 環境問題），15 項迴歸全數修復；commit `a6b49ba`（15 files changed, 752 insertions/247 deletions），push／部署狀態待 Robin 執行 `git push` 與實際部署後回補 |：`menu.py` 移出開發中名單，`commands.py` 新增選單「➕ 新增」入口與摘要→二次確認關卡（`pending_todo_confirm_save`），查詢清單改按鈕式標記完成/取消；`router.py` 新增 `menu:todo`／`todo:*` callback 分派與對應 flow 分支，`handle_callback_query()` 補上 `calendar_client` 參數；`webhook.py` 同步補上呼叫端注入；自然語言偵測入口（chat.py）維持不變，跟選單按鈕共用同一套狀態機 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2f（待辦事項）實作計畫」及「開工完成」補述；改寫 `tests/bot/test_commands.py` 待辦事項區塊、`tests/bot/test_router.py` 待辦事項整合測試，更新 `tests/bot/test_menu.py` 一項斷言，並修正 `tests/bot/test_webhook.py` 一項因 `handle_callback_query()` 新增 `calendar_client` 參數造成的迴歸斷言；移除舊版 `pending_todo_list_action`／`pending_todo_action_confirm` flow 與 `_TODO_ACTION_CLASSIFY_PROMPT`、`/my_todos`／「我的待辦事項」文字觸發詞（不提供相容期）。**比照 2d／2e，本批 Claude 沙箱未執行 `pytest`**（`commands.py` 依賴鏈過深，沙箱未還原完整依賴，只驗證 `ast.parse` 語法與人工比對既有慣例）；Robin 本機執行完整 `python3 -m pytest tests/ -q` 1806 passed／3 failed（僅剩既有 `test_toeic.py` `ffmpeg` 環境問題，與本批無關）；commit `eabed3b`（10 files changed, 540 insertions/269 deletions），08/16 Robin 已推版並完成部署與 Telegram 實機驗收（選單新增／自然語言入口／摘要確認按鈕／清單按鈕標記完成取消／舊指令失效皆正常） |
| 2026-08-16 | — | 純文件治理：AGENTS.md 與 `docs/templates/AGENTS-TEMPLATE.md` 新增「Workflow: Commit → 推版 → 部署後續」，把「commit 指令→版號回報→PROGRESS.md 記錄（push 狀態固定寫『MM/DD Robin已推版』）→第二次 commit 指令→部署後主動提供實機測試步驟」的既有慣例固化成規則 | Claude | 完成 | 使用者要求不用每次重複交代這套流程；兩份檔案同步修改（`Git 與文件同步規則` 補一條指向新 Workflow 的連結、新增完整 Workflow 段落），範本版把「Robin已推版」改成 `<使用者>` 佔位字，保持可攜性；不涉及產品功能，無對應 FR；commit `57619bb`（3 files changed, 52 insertions） |
| 2026-08-16 | FR-6e／FR-6h／FR-45／FR-76／FR-76a | Phase 6 第二批 2e（成果展示）實作完成：新檔 `src/bot/achievements.py` 複用既有 `AppLifeExplorationService`，`menu.py` 移出開發中名單，`router.py` 新增 `achievements:*` callback 分派與 `achievement` flow 分支；同步修正 SPEC.md FR-45／FR-76 條文，改為描述「開啟成果展示清單才被動掃描候選」的實際機制，Telegram 端刪除改為直接執行、不提供二次確認與復原（與 Mobile App 既有 5 秒復原不同） | Claude | 完成（已 commit，待推版與實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2e（成果展示）實作計畫」及「開工完成」補述；新增 `tests/bot/test_achievements.py`（10 項），更新 `tests/bot/test_menu.py` 一項斷言；Claude 沙箱還原 `achievements.py`／`menu.py`／`app_life_exploration.py`／`app_important_days.py`／`geocoding.py` 最小依賴環境後執行 `test_achievements.py`＋`test_menu.py` 共 19 項全過，`router.py` 因依賴鏈過深未在沙箱執行、也未擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試（比照 2d 縮小範圍）。**2026-08-16 Robin 本機驗證**：`test_achievements.py`＋`test_menu.py` 19 項全過；完整 `pytest tests/ -q` 首輪回報 4 項失敗，3 項為既有 `test_toeic.py` `ffmpeg` 環境問題（與本批無關），1 項為 `test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set` 舊斷言未同步 `achievements` 移出開發中名單（比照 2d 曾發生的同類迴歸），修正該斷言後重跑全套 1796 passed／3 failed（僅剩既有 `ffmpeg` 環境問題）；commit `a400f36`（9 files changed, 536 insertions/12 deletions） |
| 2026-08-15 | FR-6h／NFR-19 | 補正 Mobile 日期特例並定案 Telegram 重構採漸進式資料遷移，不整庫刪除重建 | Codex | 已定案／待開發 | Mobile 不限今日範圍包含待辦、重要日子、收藏、旅遊、探索、成果；先做唯讀 Schema／引用盤點，必要時採 V2 表回填切換，未執行 Migration 或刪表 |
| 2026-08-15 | FR-3～FR-6h／FR-9c～FR-9d／FR-20a／FR-72b／NFR-18 | 定案 Telegram 角色選單、帳號安全、歷史 CRUD、統一功能流程、七日查詢、排程通知與 Phase 6 執行順序 | Codex | 已定案／待開發 | 查詢由最終日期往前推 6 天且可跨多模組；Mobile 仍只異動今日生活紀錄，Telegram 負責歷史回補；隱私遮罩改帳號層雙端共用；草稿保留 30 分鐘、功能模式 10 分鐘 |
| 2026-08-15 | FR-3～FR-6h | Phase 6 第二批（Telegram 選單與狀態機）開工前盤點：確認現況無 `/start`、無按鈕基礎設施、`state.flow` 約 85 種、`/set_invite_codes` 移除範圍，並拆出子批次 2a／2b... | Claude | 完成（純盤點與拆批決策，未開工） | 決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批拆批盤點」；2a＝按鈕基礎設施＋選單骨架＋認證選單化（含移除 `/set_invite_codes`），2b 起才逐批遷移既有 85 個 flow |
| 2026-08-15 | FR-3／FR-4／FR-4a～FR-4d／FR-5／FR-6a～FR-6e | Phase 6 第二批 2a 實作完成：Telegram 按鈕基礎設施（`reply_markup`／`answer_callback_query`）、`webhook.py` callback_query 解析與分派、`menu.py` 選單骨架、`/start` 正式實作、Owner 權限管理選單化並移除 `/set_invite_codes` | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2a 實作計畫」及「開工完成」補述；主選單其餘 7 項（日常紀錄／資料查詢／待辦事項／重要日子／收藏與旅遊／成果展示／排程設定）2a 先回覆「功能開發中」，實際邏輯留給 2b 起逐批接上；新增 `tests/bot/test_menu.py`、擴充 `test_router.py`／`test_commands.py`／`test_webhook.py`／`tests/submodules/telegram/test_client.py`，Claude 沙箱 1716 項全過，Robin 本機 1750 項通過／3 項失敗（`test_toeic.py` 因本機未裝 `ffmpeg`，屬既有環境問題，與本批無關）；commit `f623566`，8/15 Robin 已推版；8/15 Robin 已完成實機驗收（/start 首綁流程、主選單 Owner／非 Owner 差異、開發中項目返回按鈕、權限管理建立／停用／恢復／重發密碼、舊指令 /set_invite_codes 已失效） |
| 2026-08-15 | FR-3～FR-6h | 定案 Phase 6 第二批 2b 起子批次分組順序（風險由低到高，資料查詢與排程設定殿後） | Claude | 已定案／待開發 | 順序：①重要日子②日常紀錄－心情、運動③收藏與旅遊④成果展示⑤待辦事項⑥日常紀錄－飲食⑦日常紀錄－體態⑧日常紀錄－記帳⑨資料查詢（FR-9c/9d）⑩排程設定；決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2b 起子批次分組順序」；僅定案順序，未定案各批次實作細節與起始日期，各批仍需個別提出 SDD 實作計畫並等待確認 |
| 2026-08-15 | FR-6e／FR-6h／FR-72a | Phase 6 第二批 2b（重要日子）實作完成：新檔 `src/bot/important_days.py` 複用既有 `AppImportantDayService`，`router.py` 新增 `menu:important_days`／`important_days:*` callback 分派與對應 flow 分支，`menu.py` 移出開發中名單 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2b（重要日子）實作計畫」及「開工完成」補述；範圍為 CRUD＋清單顯示，FR-72a 主動提醒發送器留給後續「排程設定」批次；新增 `tests/bot/test_important_days.py`（13 項，獨立 FakeDatabase）；擴充 `tests/bot/conftest.py` 共用假 DB 與 `tests/bot/test_router.py`（4 項整合測試）；`webhook.py` 未異動（2a 的通用 callback 機制可直接沿用）；8/16 Robin 本機執行完整 `python3 -m pytest` 全數通過，並完成 Telegram 實機驗收（新增／清單／編輯／刪除／非 Owner 一般使用者皆正常）；commit `f921230` |
| 2026-08-16 | FR-47／FR-49／FR-50 | Phase 6 第二批 2c（日常紀錄－心情、運動）實作完成：`menu.py` 新增「日常紀錄」子選單並移出開發中名單，`router.py`／`commands.py` 心情、運動全面改選單觸發（移除舊 Slash Command／文字觸發詞），兩模組皆補上「摘要→二次確認」關卡，查詢清單改按鈕式編輯／刪除 | Claude | 完成（已部署／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c（日常紀錄－心情、運動）實作計畫」及「開工完成」補述；同步移除 `_MOOD_ACTION_CLASSIFY_PROMPT`／`_MOOD_DELETE_CONFIRM_PROMPT`／`_EXERCISE_ACTION_CLASSIFY_PROMPT`／`_EXERCISE_DELETE_CONFIRM_PROMPT` 等 LLM 分類 Prompt，改用明確按鈕；改寫 `tests/bot/test_router.py` 心情 4 項整合測試為按鈕驅動，新增運動 5 項與 `daily_log` 子選單 2 項整合測試，更新 `tests/bot/test_menu.py` 對應斷言；Claude 沙箱還原完整依賴後執行 `tests/` 全數 155 項通過；文件複查發現 FR-47／FR-49 條文原寫死舊指令名稱，已同步更新 `docs/specs/SPEC.md` 對應段落（詳見 ADR「開工完成（2026-08-16 補正）」）；`docs/specs/DRAFT.md`／`docs/reference/` 確認不需異動；commit `8d0ba92`，8/16 Robin 已推版（`git log origin/main` 已確認），並完成 Telegram 實機驗收 |
| 2026-08-16 | FR-6e／FR-6h／FR-73～FR-74a | Phase 6 第二批 2d（收藏與旅遊）實作完成：新檔 `src/bot/collections.py`／`src/bot/trips.py` 複用既有 `AppCollectionService`／`AppLifeExplorationService`，收藏與旅遊一次做完（比照 2c 決策，不拆兩個子批次）；地址定位比照 Mobile 規則，改成「📍 定位地址／⏭ 略過定位」按鈕才呼叫 Nominatim；行程新增支援交通／住宿／飲食／門票／購物／其他六類逐一輸入預估支出；`menu.py` 移出開發中名單，`router.py` 新增 `collections:*`／`trips:*` callback 分派與 `collection`／`collection_delete_confirm`／`trip`／`trip_delete_confirm`／`trip_complete_select` 五個 flow 分支 | Claude | 完成（已 commit／推版，**實機驗收發現 1 個問題，見下一筆補修紀錄**） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2d（收藏與旅遊）實作計畫」及「開工完成」補述；新增 `tests/bot/test_collections.py`（10 項）、`tests/bot/test_trips.py`（8 項），更新 `tests/bot/test_menu.py` 一項斷言，皆用獨立 `FakeDatabase`（服務層驗證邏輯已在 `tests/services/test_app_collections.py`／`test_app_life_exploration.py` 覆蓋，這裡只測 Telegram 流程）；**本批 Claude 沙箱未執行 `pytest`**（與 2b／2c 不同，這次連輕量測試都還沒在沙箱跑過），Robin push 前本機執行測試通過；也**未擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試**；`docs/specs/SPEC.md`（FR-6e／FR-73～FR-74a 為既有已定案規格，本批純實作）／`docs/reference/api_schema.md`／`db_schema.md`（沒有新增 HTTP 路由或資料表異動）／`docs/specs/DRAFT.md`（無相關項目）確認不需更新；commit `bf715ff`（9 files changed, 1486 insertions），8/16 Robin 已推版 |
| 2026-08-16 | FR-73／FR-6h | Phase 6 第二批 2d 補修：Telegram 收藏清單新增「🧭 標記已造訪」動作，直接呼叫既有 `AppLifeExplorationService.visit_collection()`，補上「收藏可不經行程、直接標記已造訪」入口 | Claude | 完成（已 commit／推版／實機驗收） | 根因與修復細節見 `docs/ADR/debug/robinson.md` 2026-08-16「Telegram 新增的收藏不會出現在探索地圖」；`src/bot/collections.py` 新增 `start_visit()`／`handle_visit_step()`，`src/bot/router.py` 新增 `collections:visit:<id>` callback 與 `collection_visit` flow 分支；新增 `tests/bot/test_collections.py` 3 項測試，Robin 本機 `pytest tests/bot/test_collections.py` 13 項全過；順帶修正 `tests/bot/test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set` 斷言（2d 主批次移出 `collections` 開發中名單時漏改這個舊斷言，屬於迴歸修正，Robin 本機確認 PASSED）；Robin 執行完整 `pytest tests/` 另回報 19 項與本次無關的既有失敗（16 項心情／運動測試與 2c 遺留的函式簽章／已移除函式不符，3 項因本機缺 `ffmpeg`），詳見 `docs/ADR/debug/robinson.md` 補述段落，根因已排查完成（見下一筆）；`docs/specs/SPEC.md` 不動（FR-73 既有規格已涵蓋「狀態依行程關聯與造訪紀錄自動推導」，本次是補齊 Telegram 端遺漏的入口，非規格變更）；commit `9932732`（7 files changed, 208 insertions），08/16 Robin 已推版並完成 Telegram 實機驗收（新增收藏成功定位→標記已造訪→探索地圖出現圓形標記皆正常） |
| 2026-08-16 | FR-47／FR-49 | 修復 2c 遺留、與心情／運動相關的 16 項既有測試失敗（非本次 2d 功能異動，純測試同步）：`handle_mood_content_step`／`handle_exercise_heart_rate_step` 已在 2c 改為「摘要→二次確認」關卡不再直接寫入，`start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 已在 2c 移除，但 `tests/bot/test_commands.py`／`tests/bot/test_body_commands.py`／`tests/bot/test_body_router.py` 從未同步更新 | Claude | 完成（已 commit／推版） | 根因與修復方式見 `docs/ADR/debug/robinson.md` 2026-08-16「補述之二」段落；`tests/bot/test_commands.py`：改寫 4 項 `handle_mood_content_step` 測試為「內容步驟只組摘要」＋「`handle_mood_confirm_save` 才寫入」兩段式斷言，刪除呼叫已移除函式的 11 項測試（清單／更新/刪除流程的端對端覆蓋已存在於 `tests/bot/test_router.py`，見 `test_mood_list_update_and_delete_full_flow()`／`test_mood_delete_only_owner_can_target_own_journal()`，確認無覆蓋率缺口）；`tests/bot/test_body_commands.py`：修正 `test_exercise_full_log_flow_with_calorie_estimate` 呼叫 `handle_exercise_heart_rate_step` 的參數與二段式寫入流程；`tests/bot/test_body_router.py`：改寫 `test_log_exercise_full_flow`／`test_my_exercise_logs_full_flow_delete` 改用現行按鈕入口（`daily_log:exercise`→`exercise:new`／`exercise:list`→`exercise:delete:<id>`→`exercise:confirm_delete:<id>`），取代已移除的舊文字觸發詞；Robin 本機執行 `pytest tests/bot/test_commands.py tests/bot/test_body_commands.py tests/bot/test_body_router.py -v` 201 項全過，完整 `pytest tests/` 1787 passed／3 failed（僅剩既有 `ffmpeg` 環境問題，與本次無關），16 項迴歸已全數修復；`docs/specs/DRAFT.md` 2026-08-16 待討論項目已移除（見下方 DRAFT 同步）；commit `f0f7349`（6 files changed, 83 insertions/168 deletions），08/16 Robin 已推版 |
| 2026-08-15 | FR-77／NFR-14～NFR-15 | 定案取消功能的路由／資料表清理，以及 backend／mobile／data／submodules 責任分工 | Codex | 已定案／待開發 | 第一批淘汰 complaints、knowledge_base、conversation_logs、conversation_summaries；Mobile 維持根目錄，Telegram 與 LLM 歸後端，獨立爬蟲歸 data，第一階段不開 schemas；AGENTS 已分列實際現況與 Phase 6 目標 |
| 2026-08-15 | FR-19k | 定案 Owner 錯誤通知的 Telegram／Email／未送達狀態追蹤與系統錯誤管理呈現 | Codex | 部分完成 | 本次已實作送達管道與時間落地；Owner 系統錯誤管理選單的展示仍待後續批次。Email 成功不重複通知，且不適用一般使用者推播。 |
| 2026-08-15 | FR-1～FR-4（功能開關） | 將技術分享、求職分析、考試成績改為 Robin／Owner 永久專屬，取消非管理者授權與個別排程設計 | Codex | 已定案／待開發 | 一般使用者 Telegram／Mobile 不顯示入口且後端拒絕存取；Mobile 另需同步角色顯示、移除客訴入口、成果候選跨端狀態及系統錯誤送達狀態；既有資料保留 |
| 2026-08-15 | FR-19h～FR-20／FR-45／FR-72a／FR-74b／FR-76 | 定案 Telegram 主動推播邊界、重要日子統一提醒、成果候選雙端確認，以及 Owner 異常／康復通知規則 | Codex | 已定案／待開發 | 保留待辦、重要日子、月底月報、預算 50%／80%、低頻非同步結果與三項授權功能推播；取消日常紀錄催促及重複操作成功通知 |
| 2026-08-15 | FR-6c | 定案 Telegram 功能模式切換、10 分鐘逾時、草稿保護與功能名稱確認入口 | Codex | 已定案／待開發 | 權限檢查套用選單、Callback、文字／語音名稱偵測與模式切換 |
| 2026-08-15 | FR-4～FR-8／FR-10～FR-12 | 停用持久化家庭／個人知識庫、逐則對話與長記憶，改用靜態人格 Prompt 及 10 分鐘記憶體上下文 | Codex | 已定案／待開發 | 對應路由、流程與三張資料表已納入 FR-77 Phase 6 清理；DROP 前仍須完成依賴、備份與回滾審核 |
| 2026-08-15 | FR-2／FR-9a／FR-9b | 縮限 Telegram 一般對話為個人資料彈性查詢、內容整理分析及功能導引；正式資料異動一律走選單 | Codex | 已定案／待開發 | 持久化知識庫與對話記憶已另行定案停用，只保留 10 分鐘記憶體上下文 |
| 2026-08-15 | FR-6a／FR-6b | Telegram 除 `/start` 外全面取消 Slash Commands，所有一般與 Owner 操作改由權限化選單及引導式對話 | Codex | 已定案／待開發 | 不保留舊指令相容期；自然語言／語音功能名稱確認入口仍保留 |
| 2026-08-15 | FR-5／FR-6／FR-56 | Telegram「使用規則」改為固定模板選單並精簡文案；取消 `/function` 與功能總覽／細節追問 | Codex | 已定案／待開發 | 精簡模板沿用於首次綁定歡迎，刪除條目後重新連號 |
| 2026-08-15 | | 建立新專案與未來新功能的資料模型準則，並明定本專案既有表不因整理目的刪除重建 | Codex | 完成 | 同步 AGENTS、通用 Template 與 DB Schema Reference；純文件治理，未執行 Migration |
| 2026-08-15 | FR-2～FR-4／FR-4a～FR-4d | Phase 6 第一批（認證／使用者綁定）：新增 `nickname`／`family_title`／`is_active`、通關密碼 24 小時到期與 5 次錯誤鎖定 30 分鐘、`create_user_and_invite()`／`resend_passcode()`／`set_user_active()` | Claude | 完成（已部署／實機驗收） | 範圍刻意只做後端資料模型與核心驗證邏輯，Owner「權限管理」選單化流程延後到下一批（Telegram 選單與狀態機）一起做，避免與選單重構混在同一不可回退批次；`try_bind_invite_code()` 對外行為相容，`router.py` 呼叫端未變動；鎖定計數存 process 記憶體不落地（理由見 db_schema.md 0083 條目）；新增 `tests/bot/test_auth.py` 27 項測試全數通過，Robin 本機亦已覆核通過。**2026-08-15 追加修正**：`0083` 把 `invite_codes.expires_at` 改 NOT NULL 後，發現既有 `/set_invite_codes` 指令流程（`src/bot/commands.py`）未帶該欄位會直接寫入失敗，已補上 `expires_at`／`family_title`／`is_active`，屬本批次內部迴歸修正，未變更該指令對外行為。**2026-08-15 Robin 實機確認**：Render 部署後 Migration `0083` 已自動套用，`/set_invite_codes` 寫入正常、家人帳號輸入密碼綁定成功 |
| 2026-08-15 | FR-60～FR-63 | 原「使用者建檔與移除客訴」條目拆分：客訴入口、API、流程與資料表清理保留在 FR-77 Phase 6 統一清理範圍，不併入本批 | Claude | 待開發 | 見 FR-77 那筆任務 |
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

> 本表只代表本地 Git commit，不等同於已 push 或已部署。資料來源為 `git log --format="%h|%ad|%s" --date=short`；最近紀錄已於 2026-08-18 比對。git author 全部是 Robin 本人，因此「開發者」欄依 commit 內容與工作階段判斷。

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
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
| 2026-08-18 | `main`／`669accc` | GitHub | 待推版 | 功能 commit 已建立；待 Robin 連同本次 PROGRESS 同步 commit 一併 push |
| 2026-08-17 | `main`／`85db061` | GitHub | 完成 | 08/17 Robin已推版（含 `27c8476`／`85db061` 兩筆，六模組目標泛化＋批次3補做） |
| 2026-08-17 | `main`／`a6fd474` | GitHub | 完成 | 08/17 Robin 已推版；Render 已自動部署，migration 0084 已於開機時自動套用成功 |
| 2026-08-17 | `main`／`30c5303` | GitHub | 完成 | 08/17 Robin 已推版（隨 `a6fd474` 一併確認，`30c5303` 為其祖先 commit） |
| 2026-08-16 | `main`／`eabed3b` | GitHub | 完成 | 08/16 Robin 已推版 |
| 2026-08-16 | `main`／`57619bb` | GitHub | 待推版 | 尚待 Robin 推版 |
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
| 2026-08-17 | FR-47／FR-47a（運動紀錄改版批次2，commit `a6fd474`） | Render＋Vercel 正式環境／Telegram 實機＋Mobile 實體手機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-17 | FR-45／FR-46（日常紀錄－體態批次1，commit `30c5303`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-16 | FR-31／FR-31a／FR-31b／FR-32／FR-56e／FR-66a（Phase 6 第二批 2f，commit `eabed3b`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收（選單新增、自然語言入口、摘要確認按鈕、清單按鈕標記完成/取消、舊指令失效皆正常） |
| 2026-08-16 | FR-47／FR-49／FR-50（Phase 6 第二批 2c，commit `8d0ba92`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認並完成實機驗收 |
| 2026-08-15 | FR-3／FR-4／FR-4a～FR-4d／FR-5／FR-6a～FR-6e（Phase 6 第二批 2a，commit `f623566`） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 `/start` 首綁與重複顯示主選單、Owner／非 Owner 按鈕差異、開發中項目回主選單按鈕、權限管理建立／停用／恢復／重發密碼四項操作、`/set_invite_codes` 已失效 |
| 2026-08-15 | FR-2～FR-4a～FR-4d（Phase 6 第一批，Migration 0083） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 `/set_invite_codes` 寫入正常、家人 Telegram 帳號輸入通關密碼綁定成功 |
| 2026-08-15 | FR-64／FR-65／FR-72a／FR-73～FR-76a | Render＋Vercel 正式環境／Mobile 實體手機 | 完成 | Robin 已確認重要日子與求職分析載入、收藏／旅遊／探索／成果、Nominatim 定位、相關 migration 與 Mobile 實機操作正常 |
| 2026-08-12 | Step 4.4～4.5 Mobile App 與後端 API | Render＋Vercel 正式環境 | 完成 | 依當日正式上線里程碑紀錄 |
