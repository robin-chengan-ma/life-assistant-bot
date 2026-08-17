---
title: API Schema
updated: 2026-08-15
---

# API Schema

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格（放
> `docs/specs/SPEC.md`）。內容力求簡述：一行講得完就不要展開成段落，需要脈絡時用連結指回
> `docs/ADR/discuss/<功能>.md` 或 `docs/specs/PROGRESS.md` 的推版紀錄，不要把歷史敘事寫在這裡。
>
> 本文件記錄 Robinson 對外／內部使用的所有 API 路由，包含 Telegram webhook 入口與內建指令路由。
> 依 `docs/specs/SPEC.md`「平台架構與治理」區塊 NFR-12，隨開發進度更新；狀態欄位標記
> `計畫中` / `已實作`，實作完成後記得回來更新狀態。絕大多數路由是「內部路由」——不是對外 HTTP
> 端點，而是 Telegram 對話中的觸發字串／指令／`pending_*` 對話狀態機節點。
>
> 本文件已涵蓋 `docs/specs/SPEC.md` 目前收錄的所有功能區塊（Phase 1～4）。已知現況：① 除了
> 「羅賓森 Mobile App」區塊，其餘功能全部透過 Telegram 對話觸發，不是真正的 HTTP REST 端點；
> 只有 Mobile App 對應的 `src/api/` 底下 Flask Blueprint 是對外 HTTP API。② Mobile App 的
> `app_collections.py`／`app_life_exploration.py` 對應 FR-73～FR-76a；`app_important_days.py`
> （重要日子設定）已上線並納入 FR-72a／FR-74b。自訂重要日子的通用 Telegram 發送器尚未實作，現行 API 只負責管理資料與通知設定。

## 平台核心入口

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `POST /telegram/webhook` | 已實作（`src/bot/webhook.py`） | FR-1、FR-2、FR-5～FR-8、FR-17 | 所有使用者文字/圖片/語音/按鈕點擊更新的統一入口，依 Update 類型分流（`callback_query` 獨立路由／不支援格式直接拒絕／圖片轉圖片訊息路由／語音轉文字後併入文字路由／其餘文字依內容路由）；`handle_message()`／`handle_photo_message()`／`handle_voice_message()` 拋出未預期例外一律記錄 Traceback＋安全用語回覆＋仍回 HTTP 200，避免 Telegram 重試風暴（見 `docs/ADR/discuss/service-resilience.md`）；`callback_query` 走獨立精簡安全網，見下方說明 |
| `/start` | 已實作（`src/bot/router.py::handle_message`） | FR-3、FR-4c、FR-6a | 唯一保留的 Slash Command（2026-08-15 起取代 `/set_invite_codes` 等舊指令）；未綁定使用者按下後才進入「等待通關密碼」狀態、下一則文字才驗證密碼；已綁定使用者（含 Owner）按下顯示主選單（`src/bot/menu.py`） |
| `callback_query`（Inline Keyboard 按鈕） | 已實作（`src/bot/router.py::handle_callback_query`、`src/bot/webhook.py::_handle_callback_query_update`） | FR-4、FR-6c、FR-6e | 按下主選單／權限管理選單按鈕觸發；每個分支重新驗證 `auth.is_owner()`（FR-6c，不信任前端選單是否顯示過這顆按鈕）；一律先呼叫 `answerCallbackQuery` 避免 Telegram 客戶端卡在轉圈狀態 |
| `/rule` | 已實作（`src/bot/commands.py::handle_rule`） | FR-6d、FR-55 | 回傳固定使用規則全文（附錄 A），不經 LLM；亦可由主選單「使用規則」按鈕觸發 |
| ~~`/set_invite_codes`~~ | 2026-08-15 已移除 | FR-6a | 已由 `/start`＋主選單「權限管理」（`src/bot/commands.py::start_permission_menu`／`handle_permission_callback`／`handle_permission_step`）取代；舊指令使用者會收到 Telegram 預設的「指令不存在」提示，不提供相容期，見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2a 實作計畫」 |

## 服務健康與治理

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /healthz` | 已實作，已部署上線 | FR-3（平台）／FR-21（Neon 容量監控）／FR-31a、FR-32（待辦推播） | cron-job.org 每 10 分鐘呼叫的 keep-alive 端點；順便借用同一頻率觸發 `NeonCapacityMonitor`（容量達 80% 私訊 Robin）與待辦到期標記／30 分鐘前提醒／每日 08:00 摘要，皆包 try/except 不影響本端點回應 |
| `/recovered` | 已實作（`src/bot/commands.py::handle_recovered`） | FR-20 | 僅 Owner；問題修復後廣播「我康復了」給所有已綁定家人（不含 Robin 自己），單一失敗不影響其他人 |
| `錯誤ID=N 已處理：{解法}` | 已實作（`src/bot/router.py::_ERROR_RESOLUTION_PATTERN` → `src/bot/system_errors.py::update_resolution`） | FR-19j | Telegram 單行指令，直接 regex 解析（刻意用「錯誤ID=」而非「ID=」開頭，避免跟求職模組的應徵狀態更新語句撞在一起）寫入 `system_error_reports.resolution`，不走多輪對話狀態機；跟 Mobile App `PATCH /api/app/system-errors/<id>/resolution` 共用同一支 `update_resolution()` |

<details>
<summary>`GET /healthz` Response 範例</summary>

```json
{"status": "ok"}
```
</details>

## 功能開關系統

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/my_toggles` | 已實作（`src/bot/commands.py::start_my_toggles`） | FR-2、FR-2a | 列出自己的功能開/關狀態，輸入編號切換；首次觸發先補齊全部功能開關預設值 |
| `/set_toggle` | 已實作（`src/bot/commands.py::start_set_toggle`） | FR-2a | 僅 Owner；先選要調整的使用者，再進入與 `/my_toggles` 相同的編號切換畫面 |

## Gemini 對話核心

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/function` | 已實作（`src/bot/commands.py::handle_function`） | FR-9（chat-core）／FR-56、FR-56a～c | 功能總覽（獨立小型 LLM 呼叫，僅列名稱＋一句話簡述＋權限）；細節追問併入一般聊天核心 context，不走此路由 |
| 一般聊天核心 | 已實作（`src/bot/chat.py::handle_chat_message`） | FR-9～FR-12、FR-56c | 路由層最終 fallback；組 context（人格／家人背景／個人知識庫／最近 10 則對話）呼叫 Gemini，查無答案附 `【NOT_FOUND】` 標記進入 `pending_user_knowledge`，主動要求記住則附 `【REQUEST_SAVE】` 進入 `pending_save_knowledge_confirm` |
| `pending_user_knowledge` | 已實作 | FR-4 | 同一次 LLM 呼叫判斷下一則訊息是「提供答案」（`【SAVE_ANSWER】`，寫入 `knowledge_base`）、「拒絕記錄」（`【DECLINE_SAVE】`）或「無關新問題」（正常回答並清狀態） |
| `pending_name_confirm` | 已實作 | FR-3(e) | 偵測到人名疑似打字誤植（同音/形似字）時反問確認，下一則回覆判斷確認或否認 |
| `/clean-all-dialog` | 已實作（`src/bot/commands.py::start_clean_all_dialog_confirm`） | FR-10 | 觸發後先反問確認筆數才執行清除（不會動知識庫），2026-08-01 起改為先確認再執行，見 `docs/ADR/discuss/chat-core.md` |
| `pending_clean_all_dialog_confirm` | 已實作 | FR-10 | 單次 LLM 判斷 CONFIRM/CANCEL，非 CONFIRM 一律視為取消 |
| `pending_save_knowledge_confirm` | 已實作 | FR-11、ADR-8 | 反問確認主動新增知識的內容與分類；伺服器端依 `auth.is_owner()` 現場強制決定可寫入共用或僅個人範圍，不信任模型判斷 |
| `/clean-target-dialog` | 已實作（`src/bot/commands.py::start_clean_target_dialog_confirm`） | FR-12、ADR-8 | 依主題撈候選（對話紀錄＋知識庫），LLM 判斷相關性後反問確認；共用知識庫僅 Owner 觸發才納入候選 |
| `pending_clean_target_dialog_confirm` | 已實作 | FR-12、ADR-8 | 確認後 `conversation_logs` 軟刪除、`knowledge_base` 硬刪除 |

## 個資偵測與遮蔽機制

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 個資偵測與遮蔽（橫切關注點，非獨立端點） | 已實作（`src/bot/privacy.py`） | FR-13、FR-13a～FR-13d | 掛在一般聊天核心／圖片說明文字前置處理上；Regex 硬規則（8 類台灣個資格式）＋ LLM 語意辨識（獨立 `GEMINI_API_PRIVACY_KEY`，讀不到則優雅降級成只跑 Regex）雙層遮蔽；生日／LINE ID 排除；`/clean-target-dialog` 的搜尋主題與純控制流程文字刻意不套用 |

## 語音訊息安全機制

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 語音訊息（內部路由） | 已實作（`src/bot/router.py::handle_voice_message`、`src/bot/voice.py`） | FR-14、FR-15、FR-16a、FR-17 | 檢查順序：最終執行確認短路（FR-16a）→ 10 分鐘上限鎖定中 → 本則超時（觸發鎖定 15 分鐘）→ 15 分鐘修正窗口；通過後下載並轉出文字，直接當成打字輸入復用 `handle_message()` 既有邏輯，不另建流程；細節與各次修正見 `docs/ADR/discuss/chat-core.md` ADR-9、`docs/ADR/discuss/submodules-core.md` |

## 影像辨識

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 圖片訊息（內部路由） | 已實作（`src/bot/router.py::handle_photo_message`、`src/bot/image.py`） | FR-17、FR-17a～FR-17c | 上傳 Google Drive → `Pillow` 壓縮至 1024×1024／JPEG 80%（僅記憶體內處理）→ 雙 Key 隨機辨識；不確定內容標記 `[NEED_CONFIRM]` 進入 `pending_image_confirm` |
| `pending_image_confirm` | 已實作（`src/bot/image.py::handle_image_confirm_step`） | FR-17b | 帶著澄清文字，重新呼叫同一把 LLM Key、用同一份已壓縮圖片 bytes 分析，要求給出最終答案 |

## 待辦事項

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/my_todos` | 已實作（`src/bot/commands.py::start_todo_list`） | FR-31b、FR-32 | 列出 `pending` 待辦（依時間排序），支援單一時間點與區間（FR-31b）兩種顯示；輸入編號可標記完成/取消；新增待辦本身走一般聊天的三輪反問流程，不是這支路由觸發 |

## 心情小記

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/mood_journal` | 已實作（`src/bot/commands.py::start_mood_journal`） | FR-49、FR-50、FR-56h | 心情分類（固定 6 選一）→ 日記內容 → 個人成就三選一提示（可跳過）三輪反問；全程不需 LLM；日記/成就內容套用個資遮蔽 |
| `/backfill_mood` | 已實作（`src/bot/commands.py::start_mood_backfill`） | FR-49 | 先問補記日期（LLM 解析，僅接受今天或過去），確定後接入 `/mood_journal` 既有三輪流程 |
| `/my_mood_journals` | 已實作（`src/bot/commands.py::start_mood_list`） | FR-49 | 列出最近 10 筆，輸入編號可更新（重走分類/內容兩輪）或刪除（簡單一輪 CONFIRM/CANCEL，不套用 FR-16a） |

## 客訴收集

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/complaint` | 已實作（`src/bot/commands.py::start_complaint`） | FR-60～FR-63 | 固定提問（不經 LLM）→ 下一則訊息視為客訴內容，寫入（含個資遮蔽）後立即呼叫 Gemini 分析私訊 Robin（不回傳給客訴本人）；分析/私訊失敗只記 log，不影響已成功記錄 |

## 記帳

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_budget` | 已實作（`src/bot/commands.py::start_finance_budget`） | FR-41、FR-41a | 多輪設定：全局預設或特定月份覆蓋（`budget_overrides`），已有舊值先反問確認 |
| `/add_transaction` | 已實作（`src/bot/commands.py::start_finance_add`） | FR-42 | 交易類型→分類→金額→備註四輪反問；僅補記日期/更新刪除選擇/刪除確認需要 LLM |
| `/backfill_transaction` | 已實作（`src/bot/commands.py::start_finance_backfill`） | FR-42 | 先問補記日期（僅接受今天或過去），確定後接入 `/add_transaction` 同一組四輪反問 |
| `/my_transactions` | 已實作（`src/bot/commands.py::start_finance_list`） | FR-42 | 列出最近 10 筆，輸入編號可更新或刪除 |
| `/my_finance_summary` | 已實作（`src/bot/commands.py::handle_finance_summary`） | FR-44 | 單次查詢：當月支出/收入、預算使用率、分類佔比、與上月比較 |
| FR-43 記帳預算門檻預警（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/finance.py::check_and_push_budget_alerts`） | FR-43 | 50% 門檻僅每月 15 日前檢查、80% 門檻整月檢查，各自每月最多推播一次 |
| FR-42a 每日記帳提醒（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/finance.py::check_and_push_finance_reminders`） | FR-42a | 台灣時間 23:00，對「有生效預算且今天無支出紀錄」的使用者各推播一次提醒 |
| FR-44a 月底自動月報推播（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/finance.py::check_and_push_monthly_report`） | FR-44a | 每月最後一天 21:00，對「有生效預算或當月有交易」的使用者推播月度摘要 |

## 體態管理

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_height` | 已實作（`src/bot/commands.py::start_set_height`） | FR-46 | 設定身高，單輪；「設定一次、變動才修正」，合理範圍檢查見 `src/bot/body.py::is_height_reasonable` |
| `/set_waist` | 已實作（`src/bot/commands.py::start_set_waist`） | FR-46 | 2026-08-08 新增；設定腰圍，40～200 公分（`body.py::is_waist_reasonable`），設計與身高完全對稱；純參考指標，不影響 BMI 計算 |
| `/log_weight` | 已實作（`src/bot/commands.py::start_weight_log`） | FR-46 | 記錄體重，合理範圍檢查見 `body.py::is_weight_reasonable`；記錄後自動算出 BMI 並附健康提醒文字（`body.py::format_bmi_note`），同時即時檢查體重目標是否達成 |
| `/backfill_weight` | 已實作（`src/bot/commands.py::start_weight_backfill`） | FR-46 | 先問補記日期，確定後接入 `/log_weight` 同一組流程 |
| `/my_weight_logs` | 已實作（`src/bot/commands.py::start_weight_list`） | FR-46 | 列出體重紀錄，輸入編號可更新或刪除 |
| `/log_exercise` | 已實作（`src/bot/commands.py::start_exercise_log`） | FR-47 | 記錄運動，先問項目；卡路里消耗改用 LLM 估算（`body.py::estimate_exercise_calories`），非 MET 公式 |
| `/backfill_exercise` | 已實作（`src/bot/commands.py::start_exercise_backfill`） | FR-47 | 先問補記日期，確定後接入 `/log_exercise` 同一組流程 |
| `/my_exercise_logs` | 已實作（`src/bot/commands.py::start_exercise_list`） | FR-47 | 列出運動紀錄，輸入編號可更新或刪除 |
| `/log_diet` | 已實作（`src/bot/commands.py::start_diet_log`） | FR-48 | 記錄飲食，先問類型；三大營養素改用 LLM 拆算（`body.py::estimate_diet_macros`），附誤差聲明 |
| `/backfill_diet` | 已實作（`src/bot/commands.py::start_diet_backfill`） | FR-48 | 先問補記日期，確定後接入 `/log_diet` 同一組流程 |
| `/my_diet_logs` | 已實作（`src/bot/commands.py::start_diet_list`） | FR-48 | 列出飲食紀錄，輸入編號可更新或刪除；飲食目標不做自動達成判斷，只能手動取消 |
| `/set_body_goal` | 已實作（`src/bot/commands.py::start_body_goal`） | FR-45～FR-48／FR-72a | 設定體態管理目標，先問類型；體重/運動/飲食三種目標共用 `body_goals` 表；有明確期限時預設同步至重要日子 |
| `/my_body_goals` | 已實作（`src/bot/commands.py::start_body_goal_list`） | FR-45～FR-48 | 列出進行中目標，輸入編號可取消 |
| FR-45 目標達成通知（體重記錄當下即時檢查／運動借用 `/healthz` 頻率排程檢查，非獨立路由） | 已實作（`src/bot/body.py::check_weight_goal_achieved`／`check_and_push_exercise_goal_achievements`） | FR-45 | 體重目標於每次記錄體重時即時判斷方向（要瘦/要增）並達成即標記；運動目標是累積分鐘數，需跨多筆紀錄加總，改借用 `/healthz` 頻率排程檢查 |
| FR-45 目標期限前 7 天提醒（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/body.py::check_and_push_goal_deadline_reminders`） | FR-45 | 適用所有有設定 `target_date` 的進行中目標，`deadline_reminder_sent` 去重，每個目標僅提醒一次 |
| FR-45 BMI 異常提醒（記錄體重當下就地計算，非獨立路由/排程） | 已實作（`src/bot/body.py::format_bmi_note`） | FR-45 | 記錄體重時就地算出 BMI 並附衛福部國健署標準的健康提醒文字，不經排程 |

## 重要通知

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_family_birthday` | 已實作（`src/bot/commands.py::start_set_family_birthday`） | FR-53 | 僅 Owner；設計比照 `/set_toggle`，補齊尚未知道生日的家人資料（寫入 `users.birthday`） |
| FR-53／FR-53f 固定節日與生日推播（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/notifications.py::check_and_push_important_notifications`） | FR-53、FR-53f | 台灣時間 08:00 檢查固定節日清單（元旦/除夕初一/掃墓/中秋/端午/父親節/母親節，農曆用 `lunarcalendar` 即時計算）與家人生日；生日/父親節/母親節全員皆收到但主角本人/其他人文案差異化，掃墓提醒限固定名單（Robin/爸爸/媽媽/弟弟/弟媳/阿姨）；年度推播去重靠 `important_notifications_log` |

## Google Calendar 整合

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 待辦事項建立同步詢問（內嵌於新增待辦流程，非獨立路由） | 已實作（`src/bot/todo.py::create_todo` `sync_to_calendar` 參數） | FR-66a | 建立流程新增一題「要不要同步」，每次明確詢問不預設；MVP 不支援事後補同步 |
| 體態目標同步詢問與達成/取消刪除（內嵌於目標設定流程，非獨立路由） | 已實作（`src/bot/body.py::create_goal`、`check_weight_goal_achieved`、`_delete_calendar_event_if_synced`） | FR-66c | 設定流程比照待辦事項逐筆詢問是否同步；目標達成或取消時同步刪除對應 Calendar 事件；`calendar_client` 為 `None` 或 API 例外時優雅降級，不影響目標狀態本身更新 |
| 固定節日/生日全自動同步（借用 FR-53 推播流程，非獨立路由） | 已實作（`src/bot/notifications.py::_create_all_day_calendar_event`） | FR-66b | 固定節日/生日全自動同步全天事件，不逐筆詢問；建立失敗優雅降級只記警告 log，不影響 Telegram 推播本身 |

## 個人技能成長

僅 Robin 可用（`tech_intel`／`certificate` 功能開關皆為 `owner_only`）。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/start_quiz` | 已實作（`src/bot/commands.py::start_quiz_answer`） | FR-27 | 依序作答目前所有待作答的證照題庫題目，正解來自 Robin 拍照上傳的 `_ans` 答案照，不用 AI 推論 |
| `/adjust_quiz_schedule` | 已實作（`src/bot/commands.py::start_quiz_schedule_adjust`） | FR-26 | 彈性排程調整流程，支援 MOVE（挪到別天）/CANCEL（取消不補不挪）/RANGE（區間覆蓋）/SPREAD（平攤到接下來幾天，需提案確認才寫入）四種語意 |
| `/log_exam_score` | 已實作（`src/bot/commands.py::start_log_exam_score`） | FR-30 | 記錄正式應考成績，獨立建表僅查詢不修改 |
| `/my_exam_scores` | 已實作（`src/bot/commands.py::handle_my_exam_scores`） | FR-30 | 單次查詢正式成績列表，不經對話狀態機 |
| `/set_certificate_goal` | 已實作（`src/bot/commands.py::start_set_certificate_goal`） | FR-24／FR-72a | 設定證照準備目標；有明確考試日期時預設同步至重要日子，覆寫日期時同步更新 |
| `/my_certificate_goals` | 已實作（`src/bot/commands.py::handle_my_certificate_goals`） | FR-24 | 單次查詢證照準備目標列表，不經對話狀態機 |
| `/certificate_advice` | 已實作（`src/bot/commands.py::start_certificate_advice`） | FR-24 | 依近 30 天作答成效與目標，用 LLM 生成客製化讀書建議方向 |
| `/my_quiz_stats` | 已實作（`src/bot/commands.py::start_quiz_stats_query`） | FR-29 | 彈性自然語言問答查詢作答成效，不做圖表，排除未作答日子並支援跨區間比較 |
| 每日技術分享收集（固定 23:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/skill_growth.py::collect_and_store_daily_digest`） | FR-22、FR-23 | 收集 TLDR 電子報＋IThome／TechCrunch 當天新聞，各來源各自經 Gemini 產出摘要，寫入 `skill_growth_digests`（一天最多三筆，一筆一來源） |
| 每日技術分享推播（隔天固定 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/skill_growth.py::check_and_push_daily_digest`） | FR-22、FR-23 | 讀取前一晚 23:00 收集結果，拆成最多三則獨立訊息推播；任一來源失敗只記 log，三個來源皆無內容才推播固定訊息 |
| TOEIC 每日出題推播（固定 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/certificate_quiz.py::check_and_push_daily_quiz`） | FR-26 | 依當日生效的出題數量/比例設定（`certificate_daily_settings`／`certificate_daily_schedule_overrides`，見 `src/bot/certificate_schedule.py`）寫入當日題目指派並推播通知 |
| TOEIC 作答提醒（固定 20:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/certificate_answer.py::check_and_push_answer_reminders`） | FR-28 | 若還有題目沒作答，提醒一次；23:00 靜默視為跳過（不主動通知，但仍可跨日晚補答） |

## YouTube 技術情報模組

僅 Robin 可用（與每日技術分享共用 `tech_intel` 功能開關）。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/my_youtube_topics` | 已實作（`src/bot/commands.py::handle_my_youtube_topics`） | FR-57a | 單次列出目前設定的 YouTube 技術情報主題 |
| `/add_youtube_topic` | 已實作（`src/bot/commands.py::start_add_youtube_topic`） | FR-57a | 開始新增一組主題流程 |
| `/remove_youtube_topic` | 已實作（`src/bot/commands.py::start_remove_youtube_topic`） | FR-57a | 列出目前主題，輸入編號刪除 |
| 每週技術情報推播（固定每週四 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/youtube.py::check_and_push_weekly_youtube`） | FR-58、FR-59 | 用 YouTube Data API 取候選影片，LLM 語意判讀標題/說明欄/統計數字排序（取代 Rule-based Weight）；多主題採「保底＋輪替」公平曝光機制，30 天內已推播 `video_id` 過濾 |

## 好友模式

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/friend_chat` | 已實作（`src/bot/commands.py::start_friend_chat`） | FR-51、FR-52 | 「陪我聊聊」；`friend_mode` 開關非 owner_only，所有使用者皆可用；動態讀取這位使用者已開啟且近 7 天有資料的所有功能模組近況（`friend_chat.py::_DATA_PROVIDERS` 登記表），交給 LLM 生成陪伴式回覆，內容自然涵蓋心情趨勢文字/emoji 摘要（不做圖表），僅被動觸發、不含主動關懷推播 |

## 求職模組

僅 Robin 可用（`job_search` 開關為 `owner_only`）。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_job_search` | 已實作（`src/bot/commands.py::start_job_search_setup`） | FR-33、FR-34、FR-36 | 開始求職模組設定流程，先問搜尋條件；支援多組搜尋條件、兩階段爬取（列表→詳情頁），並收集履歷/期望工作內容（含結構化年資、期望薪資） |
| `/add_external_job` | 已實作（`src/bot/commands.py::start_add_external_job`） | FR-40 | 記錄 LinkedIn／Cake 等外部管道職缺，先問管道；外部職缺與 104 職缺共用同一張表（`source` 欄位區分），合成識別碼，一起參與每週評分排名 |
| `/my_applications` | 已實作（`src/bot/commands.py::handle_my_applications`） | FR-39 | 單次查詢目前各職缺的最新應徵狀態 |
| 應徵狀態更新語句（regex 直接解析，非多輪對話，非獨立路由） | 已實作（`src/bot/router.py::_APPLICATION_STATUS_PATTERN` → `src/bot/job_search.py::record_application_status`） | FR-39 | 「ID=xxx 職缺 已應徵/已獲得面試/已拿到Offer/已婉拒/未錄取」單行指令直接解析並寫入獨立歷程表 |
| 公司背景 CSV 回填（regex「已上傳 {檔名}」分流，非獨立路由） | 已實作（`src/bot/router.py::_UPLOADED_FILE_PATTERN` → `src/bot/commands.py::handle_company_csv_uploaded`） | FR-35 | 檔名以「104職缺公司.csv」結尾時觸發；Robin 查填公司背景後上傳 Drive 回填，`gdrive_client` 未設定時優雅降級提示稍後再試 |
| 職缺推薦 Excel 回填（regex「已上傳 {檔名}」分流，非獨立路由） | 已實作（`src/bot/router.py::_UPLOADED_FILE_PATTERN` → `src/bot/commands.py::handle_job_recommendation_excel_uploaded`） | FR-38 | 檔名以「104職缺推薦.xlsx」結尾時觸發；Robin 標記喜好後上傳 Drive 回填 `is_unliked`，與公司背景 CSV 是各自獨立、設計對稱的分流 |
| 每週爬取＋評分本體（固定每週一 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/job_search.py::check_and_run_weekly_job_search`） | FR-33、FR-37、FR-38 | 爬取職缺→新公司背景 CSV 寄送→Gemini 批次契合度評分（僅計算公司背景已回填的職缺）＋雙重排名（全庫／本週新職缺）→技能缺口分析 Excel（三工作表）寄送 |

## 羅賓森 Mobile App

對應 `src/api/` 底下的 Flask Blueprint，是本文件唯一一組真正對外的 HTTP REST 端點（其餘功能皆為 Telegram 內部路由）。所有端點皆需 `Authorization: Bearer <access_token>`（除登入/忘記密碼/刷新 token 本身），由 `require_access_token` 裝飾器驗證。

### 帳密登入（`src/api/app_auth.py`，url_prefix `/api/app`）

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `POST /api/app/auth/login` | 已實作（`login()`） | FR-65 | 帳密登入（`user_id`＋`password`＋`keep_logged_in`），密碼單向雜湊比對，成功回傳 access/refresh token；使用者不存在或密碼錯誤回傳明確錯誤碼（`UNKNOWN_USER`／`INVALID_PASSWORD`） |
| `POST /api/app/auth/identify` | 已實作（`identify()`） | FR-65 | 依 `user_id` 確認身份是否存在，供忘記密碼流程前置步驟使用 |
| `POST /api/app/auth/forgot-password` | 已實作（`forgot_password()`） | FR-65 | 重設新密碼並透過 Telegram 私訊發送（複用 `TelegramClient`，不寄 Email）；Telegram 傳送失敗回傳 503 並提示聯絡 Robin |
| `POST /api/app/auth/refresh` | 已實作（`refresh()`） | FR-65 | 用 `refresh_token` 換發新 access token，保持登入 30 天效期 |
| `GET /api/app/auth/me` | 已實作（`me()`） | FR-65 | 回傳目前登入使用者資料 |
| `POST /api/app/auth/change-password` | 已實作（`change_password()`） | FR-65 | 修改密碼，需驗證目前密碼；新密碼需 8～15 碼含大小寫英文字母、數字、特殊符號且不可含空白，且不可與目前或曾使用過的密碼重複 |
| `POST /api/app/auth/logout` | 已實作（`logout()`） | FR-65 | 登出，清除該使用者的登入狀態 |
| `POST /api/app/auth/preferences` | 已實作（`update_preferences()`） | FR-67、FR-72 | 更新 APP 設定（主題偏好、字體大小偏好、個資遮蔽開關） |

### 唯讀分析與設定頁（`src/api/app_analytics.py`，url_prefix `/api/app`）

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /api/app/dashboard` | 已實作（`dashboard()`） | FR-64 | 首頁摘要卡片資料，複用 `AppAnalyticsService.dashboard()` |
| `GET /api/app/analytics/<module_key>` | 已實作（`analytics()`） | FR-64 | 唯讀分析頁面資料，`module_key` 對應 todos/body/finance/mood/jobs/exams/skills/complaints；依模組解析查詢日期區間（todos 額外支援月曆區間）；功能開關關閉回 409、越權存取回 403 |
| `PATCH /api/app/system-errors/<id>/resolution` | 已實作（`update_error_resolution()`） | FR-19j | 僅 Owner；App 端補記系統錯誤解法，與 Telegram「錯誤ID=N 已處理：{解法}」共用同一支 `src/bot/system_errors.py::update_resolution()` |
| `POST /api/app/body/weight-logs` | 已實作（`create_weight_log()`） | FR-64a | App 端手動輸入體重（取代已移除的藍牙體重計整合方案），40～150 公斤範圍檢查，複用 `src/bot/body.py::create_weight_log()` |
| `POST /api/app/diet/recognize-photo` | 已實作（`recognize_diet_image()`） | FR-64 | 飲食照片辨識（LLM Vision），App 端專屬能力，Telegram 端沒有對應路由 |
| `POST /api/app/diet/calculate-nutrition` | 已實作（`calculate_diet_image_nutrition()`） | FR-64 | 依確認後的飲食描述計算三大營養素，App 端專屬能力 |
| `POST /api/app/records/<kind>` | 已實作（`create_record()`） | FR-64、FR-68～FR-74a | 泛用記錄新增；`diet` 支援 `nutrition_source=ai/manual` 與人工營養數值，`exercise`（2026-08-17，FR-47a，批次2）支援 `category_id`（既有類別）或 `custom_category`（新增全域類別，同義詞合併見 `body.find_or_create_exercise_category()`）＋ `use_ai_calorie` 布林值決定熱量來源，`finance` 可選填本人有效的 `trip_id`；重複紀錄預設擋下，可帶 `allow_duplicate` 略過檢查 |
| `PATCH /api/app/records/<kind>/<id>` | 已實作（`update_record()`） | FR-64、FR-68～FR-74a | 泛用記錄更新，沿用飲食／運動輸入來源欄位及記帳行程關聯；歷史（過去）紀錄的異動限制見 `HistoricalRecordError` |
| `DELETE /api/app/records/<kind>/<id>` | 已實作（`delete_record()`） | FR-68～FR-72 | 泛用記錄刪除 |
| `GET /api/app/exercise-categories` | 已實作（`list_exercise_categories()`） | FR-47a | 全域共用運動類別清單，供 Mobile App 表單類別下拉選單使用 |

### 收藏清單（`src/api/app_collections.py`，url_prefix `/api/app/collections`）

> 對應 SPEC FR-73。
> 收藏寫入欄位為 `item_type`、`title`、`country_name`、`city_name`、選填 `country_code`、`address`、
> `latitude`／`longitude`、`source_url`、`estimated_cost`、`notes`。國家及區域／城市必填，地址對所有
> 類型皆為選填；未填地址時可用國家與區域／城市取得近似座標。`currency_code` 固定為 `TWD`；不接受用戶端直接設定
> `priority`、`desired_date`、`administrative_area`、`trip_id`、`status` 或 `visited_at`。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /api/app/collections` | 已實作（`list_collection_items()`） | FR-73 | 依國家／區域城市／類型／推導狀態篩選個人收藏，按最近更新時間排序 |
| `POST /api/app/collections` | 已實作（`create_collection_item()`） | FR-73 | 新增收藏；初始狀態固定為 `saved`，不接受用戶端手動指定狀態 |
| `PATCH /api/app/collections/<id>` | 已實作（`update_collection_item()`） | FR-73 | 更新收藏內容，不覆寫由行程／造訪流程推導的狀態 |
| `DELETE /api/app/collections/<id>` | 已實作（`delete_collection_item()`） | FR-73 | 軟刪除收藏並移除規劃中／已確認行程關聯；既有探索快照保留，回傳 5 秒復原資訊 |
| `POST /api/app/collections/<id>/restore` | 已實作（`restore_collection_item()`） | FR-73 | 復原已軟刪除收藏 |
| `POST /api/app/collections/geocode` | 已實作（`geocode_collection_address()`） | FR-75 | 由使用者明確觸發定位；區域／城市及國家必填、地址選填；有地址依精確門牌→道路→城市放寬，無地址直接查城市，回傳 `precision／precision_label`；成功結果寫入 `geocoding_cache`，全部找不到回 404、服務不可用回 503 |

### 生活探索與成果（`src/api/app_life_exploration.py`，url_prefix `/api/app/life`）

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET／POST /api/app/life/trips` | 已實作 | FR-74／FR-74b | 列出／建立本人旅遊行程；回傳預估、實際與差額，建立時只能關聯相同國家及區域／城市的收藏；`sync_to_important_day` 預設 `true`，並可傳提醒天數、通知對象、指定對象與待辦行事曆顯示設定 |
| `PATCH／DELETE /api/app/life/trips/<id>` | 已實作 | FR-74 | 更新／軟刪除本人行程 |
| `POST /api/app/life/trips/<id>/restore` | 已實作 | FR-74 | 復原已刪除行程 |
| `POST /api/app/life/trips/<id>/complete` | 已實作 | FR-74、FR-75 | 依 `visited_collection_ids` 完成行程，只為實際造訪收藏建立探索快照 |
| `POST /api/app/life/collections/<id>/visit` | 已實作 | FR-73、FR-75 | 未透過行程時直接將收藏標記為已造訪；必填 `visited_on` |
| `GET /api/app/life/exploration` | 已實作 | FR-75 | 依 `country`／`city` 篩選；有座標資料按同座標聚合標記，無座標資料放入 `unlocated` |
| `PATCH／DELETE /api/app/life/exploration/<id>` | 已實作 | FR-75 | 更新單次造訪日期／備註／地址，或軟刪除探索紀錄 |
| `POST /api/app/life/exploration/<id>/restore` | 已實作 | FR-75 | 復原已刪除探索紀錄 |
| `POST /api/app/life/exploration/<id>/relocate` | 已實作 | FR-75 | 依本人探索快照的地址、區域／城市與國家重新取得座標；更新地址但未重定位時會先清除舊座標 |
| `GET／POST /api/app/life/achievements` | 已實作 | FR-76 | 列出成果與待確認候選；手動新增成果可帶類別、完成日、說明與 HTTPS 封面照片網址 |
| `DELETE /api/app/life/achievements/<id>` | 已實作 | FR-76 | 軟刪除成果，不異動來源資料 |
| `POST /api/app/life/achievements/<id>/restore` | 已實作 | FR-76 | 復原已刪除成果 |
| `POST /api/app/life/achievement-candidates/<id>/decision` | 已實作 | FR-76 | `accept=true／false` 接受或拒絕成果候選；拒絕後相同 `candidate_key` 不重複提示 |

> FR-75 Nominatim 呼叫由後端代理，需設定 `NOMINATIM_USER_AGENT`；未設定時回 503，不會以匿名預設值呼叫公開服務。

### 重要日子設定（`src/api/app_important_days.py`，url_prefix `/api/app/important-days`）

> App 端管理介面與資料結構已完成；Telegram 提醒已正式納入 FR-72a／FR-74b，但通用發送器仍屬待開發，不能因事件已寫入 `important_days` 就視為通知已送達。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /api/app/important-days` | 已實作（`list_important_days()`） | FR-72a／FR-74b | 查詢個人設定的重要日子清單，並附家人使用者名單供選擇對象；名單的 `user_id` 不存於 `users` 表，而是依 FR-65 由 `users.id` 動態格式化為 `user01`、`user10` |
| `POST /api/app/important-days` | 已實作（`create_important_day()`） | FR-72a／FR-74b | 新增一筆重要日子設定 |
| `PATCH /api/app/important-days/<id>` | 已實作（`update_important_day()`） | FR-72a／FR-74b | 更新一筆重要日子設定 |
| `DELETE /api/app/important-days/<id>` | 已實作（`delete_important_day()`） | FR-72a／FR-74b | 刪除一筆重要日子設定 |

## 未分類

（無——目前文件列出的 104 個項目皆可依內容明確對應到上述功能分組。）
