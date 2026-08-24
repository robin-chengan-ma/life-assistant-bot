---
title: API Schema
updated: 2026-08-23
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
> （重要日子設定）已上線並納入 FR-72a／FR-74b。通用 Telegram 發送器已由
> `src/bot/scheduled_notifications.py` 實作，每日 08:00 處理自訂重要日子、已同步目標與旅遊行程。

## 平台核心入口

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `POST /telegram/webhook` | 已實作（`src/bot/webhook.py`） | FR-1、FR-2、FR-5～FR-8、FR-17 | 所有使用者文字/圖片/語音/按鈕點擊更新的統一入口，依 Update 類型分流（`callback_query` 獨立路由／不支援格式直接拒絕／圖片轉圖片訊息路由／語音轉文字後併入文字路由／其餘文字依內容路由）；`handle_message()`／`handle_photo_message()`／`handle_voice_message()` 拋出未預期例外一律記錄 Traceback＋安全用語回覆＋仍回 HTTP 200，避免 Telegram 重試風暴（見 `docs/ADR/discuss/service-resilience.md`）；`callback_query` 走獨立精簡安全網，見下方說明 |
| `/start` | 已實作（`src/bot/router.py::handle_message`） | FR-3、FR-4c、FR-6a | 唯一保留的 Slash Command（2026-08-15 起取代 `/set_invite_codes` 等舊指令）；未綁定使用者按下後才進入「等待通關密碼」狀態、下一則文字才驗證密碼；已綁定使用者（含 Owner）按下顯示主選單（`src/bot/menu.py`） |
| `callback_query`（Inline Keyboard 按鈕） | 已實作（`src/bot/router.py::handle_callback_query`、`src/bot/webhook.py::_handle_callback_query_update`） | FR-4、FR-6c、FR-6e | 按下主選單／權限管理選單按鈕觸發；每個分支重新驗證 `auth.is_owner()`（FR-6c，不信任前端選單是否顯示過這顆按鈕）；一律先呼叫 `answerCallbackQuery` 避免 Telegram 客戶端卡在轉圈狀態 |
| `menu:rule` | 已實作（`src/bot/commands.py::handle_rule`） | FR-6d、FR-55 | 主選單「📋 使用規則」回傳固定使用規則全文（附錄 A），不經 LLM |
| ~~`/set_invite_codes`~~ | 2026-08-15 已移除 | FR-6a | 已由 `/start`＋主選單「權限管理」（`src/bot/commands.py::start_permission_menu`／`handle_permission_callback`／`handle_permission_step`）取代；舊指令使用者會收到 Telegram 預設的「指令不存在」提示，不提供相容期，見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2a 實作計畫」 |

> Slash Command 只保留 `/start`。`/rule`、`/my_toggles`、`/set_toggle`、`/set_family_birthday`、
> `/friend_chat` 已於 2026-08-18 移除，不保留相容期。

## 服務健康與治理

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /healthz` | 已實作，已部署上線 | FR-3（平台）／FR-21（Neon 容量監控）／FR-31a、FR-32（待辦推播） | cron-job.org 每 10 分鐘呼叫的 keep-alive 端點；順便借用同一頻率觸發 `NeonCapacityMonitor`（容量達 80% 私訊 Robin）與待辦到期標記／30 分鐘前提醒／每日 08:00 摘要，皆包 try/except 不影響本端點回應 |
| `menu:recovered` → `recovery:*` | 已實作（`src/bot/recovery_notifications.py`） | FR-20 | Telegram 事故候選人為曾成功收到事故通知的家人；Mobile 事故優先列受影響使用者，無法辨識時列全部已綁定 Telegram 的家人。Owner 勾選、預覽對應平台文案並二次確認；部分失敗保留事故供重試 |
| `menu:system_errors` → `system_errors:*` | 已實作（`src/bot/system_error_management.py`） | FR-19j～FR-19l | Owner 專屬 Telegram 錯誤管理；可查看待處理／最近已處理、來源平台、累計次數、受影響者與 Telegram／Email／未送達狀態；輸入處理說明後預覽並二次確認結案 |
| `menu:schedule` → `schedule:*` | 已實作（`src/bot/schedule_settings.py`） | FR-1～FR-4a／FR-6f～FR-6g | 一般使用者管理自己的通知接收；Owner 額外管理技術分享／求職設定／考試設定功能開關並唯讀查看系統工作。關閉通知不停止背景工作，關閉功能則停止對應收集、生成與推播 |
| 統一重要日子提醒（借用 `/healthz`） | 已實作（`src/bot/scheduled_notifications.py`） | FR-20a／FR-72a／FR-74b | 每日 08:00 依 `important_days.reminder_days_before` 與通知對象推播；涵蓋自訂重要日子、所有已同步目標及旅遊行程，逐收件人去重並尊重通知開關 |
| `錯誤ID=N 已處理：{解法}` | 已移除 | FR-19j | 改由 `menu:system_errors` 選單引導、草稿保護與二次確認結案 |

<details>
<summary>`GET /healthz` Response 範例</summary>

```json
{"status": "ok"}
```
</details>

## 功能開關系統

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `menu:schedule` → `schedule:*` | 已實作（`src/bot/schedule_settings.py`） | FR-2、FR-2a、FR-6f～FR-6g | 一般使用者設定自己的通知；Owner 額外操作三項 Owner 功能開關。舊版本人編號切換與代管家人開關流程已移除 |

## Gemini 對話核心

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/function` | 已移除 | 已取消 | 功能探索改由 Telegram 可見選單與固定功能別名導引提供 |
| 一般聊天核心 | 已完成縮限（`src/bot/chat.py::handle_chat_message`） | 一般對話 FR-1～FR-13 | 僅含本人結構化資料唯讀查詢、使用者內容整理分析及功能導引；只保留依 Telegram 使用者隔離的 10 分鐘記憶體上下文，逾時或切換選單清除，不直接異動正式資料、即時上網、讀寫知識庫或落地聊天紀錄 |
| 已取消的知識／對話流程 | 已移除 | FR-77 | `pending_user_knowledge`、`pending_name_confirm`、`/clean-all-dialog`、`pending_save_knowledge_confirm`、`/clean-target-dialog` 及相關狀態、處理函式與測試均不再存在 |

## 個資偵測與遮蔽機制

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 個資偵測與遮蔽（橫切關注點，非獨立端點） | 已實作（`src/bot/privacy.py`） | FR-13、FR-13a～FR-13d | 掛在一般聊天核心／圖片說明文字前置處理上；Regex 硬規則（8 類台灣個資格式）＋ LLM 語意辨識（獨立 `GEMINI_API_PRIVACY_KEY`，讀不到則優雅降級成只跑 Regex）雙層遮蔽；生日／LINE ID 排除；`/clean-target-dialog` 的搜尋主題與純控制流程文字刻意不套用 |

## 語音訊息安全機制

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| Telegram 長按語音（內部路由） | 已實作 | FR-14、FR-16b | 最長 10 分鐘，超過後拒絕並鎖定語音功能 5 分鐘；成功轉錄後先顯示文字與「✅ 正確，繼續」，確認後才接回原流程。已取消 15 分鐘修正限制，聽錯可立即重新傳語音 |
| 上傳音檔（內部路由） | 已實作 | FR-13、FR-16b、FR-17 | 與 Telegram 長按語音分流，不套用 10 分鐘上限或 5 分鐘鎖定；轉錄成功後同樣先要求確認文字 |
| 圖片與不支援檔案（內部路由） | 已實作 | FR-2、FR-13、FR-17 | 圖片無說明時預設辨識並整理重點，有說明時依說明處理；影片、Video Note、PDF、Office 文件、壓縮檔及其他格式固定回覆「我只能處理對話框文字、語音、圖片和音檔喔！」 |

## 影像辨識

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 圖片訊息（內部路由） | 已實作（`src/bot/router.py::handle_photo_message`、`src/bot/image.py`） | FR-17、FR-17a～FR-17c | 上傳 Google Drive → `Pillow` 壓縮至 1024×1024／JPEG 80%（僅記憶體內處理）→ 雙 Key 隨機辨識；不確定內容標記 `[NEED_CONFIRM]` 進入 `pending_image_confirm` |
| `pending_image_confirm` | 已實作（`src/bot/image.py::handle_image_confirm_step`） | FR-17b | 帶著澄清文字，重新呼叫同一把 LLM Key、用同一份已壓縮圖片 bytes 分析，要求給出最終答案 |

## 待辦事項

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/my_todos` | 2026-08 已移除 | FR-31b、FR-32 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |

## 心情小記

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/mood_journal` | 2026-08 已移除 | FR-49、FR-50、FR-56h | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/backfill_mood` | 2026-08 已移除 | FR-49 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_mood_journals` | 2026-08 已移除 | FR-49 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |

## 記帳

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_budget` | 2026-08 已移除 | FR-41、FR-41a | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/add_transaction` | 2026-08 已移除 | FR-42 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/backfill_transaction` | 2026-08 已移除 | FR-42 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_transactions` | 2026-08 已移除 | FR-42 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_finance_summary` | 2026-08 已移除 | FR-44 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| FR-43 記帳預算門檻預警（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/finance.py::check_and_push_budget_alerts`） | FR-43 | 50% 門檻僅每月 15 日前檢查、80% 門檻整月檢查，各自每月最多推播一次 |
| FR-44a 月底自動月報推播（借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/finance.py::check_and_push_monthly_report`） | FR-44a | 每月最後一天 21:00，對「有生效預算或當月有交易」的使用者推播月度摘要 |

## 體態管理

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_height` | 2026-08 已移除 | FR-46 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/set_waist` | 2026-08 已移除 | FR-46 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/log_weight` | 2026-08 已移除 | FR-46 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/backfill_weight` | 2026-08 已移除 | FR-46 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_weight_logs` | 2026-08 已移除 | FR-46 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/log_exercise` | 2026-08 已移除 | FR-47 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/backfill_exercise` | 2026-08 已移除 | FR-47 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_exercise_logs` | 2026-08 已移除 | FR-47 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/log_diet` | 2026-08 已移除 | FR-48 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/backfill_diet` | 2026-08 已移除 | FR-48 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_diet_logs` | 2026-08 已移除 | FR-48 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/set_body_goal` | 2026-08 已移除 | FR-45～FR-48／FR-72a | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_body_goals` | 2026-08 已移除 | FR-45～FR-48 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| FR-45 目標達成通知（體重記錄當下即時檢查／運動借用 `/healthz` 頻率排程檢查，非獨立路由） | 已實作（`src/bot/body.py::check_weight_goal_achieved`／`check_and_push_exercise_goal_achievements`） | FR-45 | 體重目標於每次記錄體重時即時判斷方向（要瘦/要增）並達成即標記；運動目標是累積分鐘數，需跨多筆紀錄加總，改借用 `/healthz` 頻率排程檢查 |
| FR-45 BMI 異常提醒（記錄體重當下就地計算，非獨立路由/排程） | 已實作（`src/bot/body.py::format_bmi_note`） | FR-45 | 記錄體重時就地算出 BMI 並附衛福部國健署標準的健康提醒文字，不經排程 |

## 重要通知

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `menu:important_days` | 已實作（`src/bot/important_days.py`） | FR-53、FR-72a | 新增生日或其他日期提醒一律走重要日子設定；舊 `/set_family_birthday` 與寫入 `users.birthday` 的對話流程已移除 |
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
| `menu:certificate`／`certificate_settings:*` | 已實作（`src/bot/certificate_settings.py`） | FR-24／FR-26／FR-30a～FR-30b | Owner 專屬考試設定選單；提供證照名冊、目標、每日題數、不可重疊日期區間及正式成績新增／查詢，所有寫入均先摘要再按鈕確認 |
| `certificate_settings:quiz:start` | 已實作（轉接 `src/bot/commands.py::start_quiz_answer`） | FR-27 | 依序作答目前所有待作答題目；舊 `/start_quiz` 與文字觸發詞已移除 |
| 每日技術分享收集（固定 23:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/skill_growth.py::collect_and_store_daily_digest`） | FR-22、FR-23 | 收集 TLDR 電子報＋IThome／TechCrunch 當天新聞，各來源各自經 Gemini 產出摘要，寫入 `skill_growth_digests`（一天最多三筆，一筆一來源） |
| 每日技術分享推播（隔天固定 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/skill_growth.py::check_and_push_daily_digest`） | FR-22、FR-23 | 讀取前一晚 23:00 收集結果，拆成最多三則獨立訊息推播；任一來源失敗只記 log，三個來源皆無內容才推播固定訊息 |
| TOEIC 每日出題推播（固定 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/certificate_quiz.py::check_and_push_daily_quiz`） | FR-26 | 依當日生效的固定聽力／讀寫／單字題數（全局或日期區間覆蓋）寫入當日題目指派並推播；舊比例欄位僅作相容 fallback |

## YouTube 技術情報模組

僅 Robin 可用（與每日技術分享共用 `tech_intel` 功能開關）。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/my_youtube_topics` | 2026-08 已移除 | FR-57a | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/add_youtube_topic` | 2026-08 已移除 | FR-57a | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/remove_youtube_topic` | 2026-08 已移除 | FR-57a | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| 每週技術情報推播（固定每週四 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/youtube.py::check_and_push_weekly_youtube`） | FR-58、FR-59 | 用 YouTube Data API 取候選影片，LLM 語意判讀標題/說明欄/統計數字排序（取代 Rule-based Weight）；多主題採「保底＋輪替」公平曝光機制，30 天內已推播 `video_id` 過濾 |

## 好友模式

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| 自然語言「陪我聊聊」 | 已實作（`src/bot/commands.py::start_friend_chat`） | FR-51、FR-52 | `friend_mode` 開關非 owner_only，所有使用者皆可用；動態讀取這位使用者已開啟且近 7 天有資料的所有功能模組近況，交給 LLM 生成陪伴式回覆；舊 `/friend_chat` 已移除 |

## 求職模組

僅 Robin 可用（`job_search` 開關為 `owner_only`）。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `/set_job_search` | 2026-08 已移除 | FR-33、FR-34、FR-36 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/add_external_job` | 2026-08 已移除 | FR-40 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| `/my_applications` | 2026-08 已移除 | FR-39 | 既有處理邏輯已改由權限化選單與 Callback 進入；舊 Slash Command／文字觸發詞不保留相容期。 |
| 應徵狀態更新語句（舊 regex 入口） | 2026-08-18 已移除 | FR-39 | 已改由「求職設定」職缺清單按鈕選擇狀態，不再接受 `ID=...` 文字指令。 |
| 公司背景 CSV 回填（regex「已上傳 {檔名}」分流，非獨立路由） | 已實作（`src/bot/router.py::_UPLOADED_FILE_PATTERN` → `src/bot/commands.py::handle_company_csv_uploaded`） | FR-35 | 檔名以「104職缺公司.csv」結尾時觸發；Robin 查填公司背景後上傳 Drive 回填，`gdrive_client` 未設定時優雅降級提示稍後再試 |
| 職缺推薦 Excel 回填（regex「已上傳 {檔名}」分流，非獨立路由） | 已實作（`src/bot/router.py::_UPLOADED_FILE_PATTERN` → `src/bot/commands.py::handle_job_recommendation_excel_uploaded`） | FR-38 | 檔名以「104職缺推薦.xlsx」結尾時觸發；Robin 標記喜好後上傳 Drive 回填 `is_unliked`，與公司背景 CSV 是各自獨立、設計對稱的分流 |
| 每週爬取＋評分本體（固定每週一 08:00，借用 `/healthz` 頻率，非獨立路由） | 已實作（`src/bot/job_search.py::check_and_run_weekly_job_search`） | FR-33、FR-37、FR-38 | 爬取職缺→新公司背景 CSV 寄送→Gemini 批次契合度評分（僅計算公司背景已回填的職缺）＋雙重排名（全庫／本週新職缺）→技能缺口分析 Excel（三工作表）寄送 |

## 羅賓森 Mobile App

對應 `src/api/` 底下的 Flask Blueprint，是本文件唯一一組真正對外的 HTTP REST 端點（其餘功能皆為 Telegram 內部路由）。所有端點皆需 `Authorization: Bearer <access_token>`（除登入/忘記密碼/刷新 token 本身），由 `require_access_token` 裝飾器驗證。

Mobile API 的輸入驗證、權限與認證過期等預期 4xx 只回傳安全業務訊息；未預期
5xx 另透過 `src/api/error_reporting.py` 建立 Mobile 事故並通知 Owner，不保存 Request
payload、帳號、密碼或 Token。

### 帳密登入（`src/api/app_auth.py`，url_prefix `/api/app`）

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `POST /api/app/auth/login` | 已實作（`login()`） | FR-65／FR-65a | 帳密登入（`user_id`＋`password`＋`keep_logged_in`），密碼單向雜湊比對，成功回傳 access/refresh token；使用者不存在或密碼錯誤回傳明確錯誤碼（`UNKNOWN_USER`／`INVALID_PASSWORD`）；連續密碼錯誤達 2 次鎖定帳號，之後一律回 401 `ACCOUNT_LOCKED`（訊息「帳號已被鎖定，請聯絡管理者解鎖」），需 Owner 於 Telegram 手動解鎖才能再次嘗試；鎖定觸發當下同步以 Telegram 私訊通知 Owner（`ROBIN_TELEGRAM_TOKEN` 未設定時略過，不影響登入回應） |
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
| `GET /api/app/analytics/<module_key>` | 已實作（`analytics()`） | FR-64／FR-64b～FR-64d | 唯讀分析頁面資料，`module_key` 對應 todos/body/finance/mood/jobs/exams/skills；todos 查詢 1～7 天且額外支援月曆月份，其餘一般分析查詢 1～30 天，skills 維持單日。一般生活模組不讀舊功能開關；Owner 專屬 skills/jobs/exams 關閉回 409，越權存取回 403。jobs 回傳應徵漏斗、契合度分布、含公司／地區／來源／網址的推薦職缺與應徵歷程；exams 回傳啟用證照名冊、題庫可用狀態、標準化目標進度、區間練習與正式成績 |
| `PATCH /api/app/system-errors/<id>/resolution` | 已移除 | FR-19j | Mobile App 只作為事故來源；Owner 統一從 Telegram 系統錯誤管理結案 |
| `POST /api/app/body/weight-logs` | 已實作（`create_weight_log()`） | FR-64a | App 端手動輸入體重（取代已移除的藍牙體重計整合方案），40～150 公斤範圍檢查，複用 `src/bot/body.py::create_weight_log()` |
| `POST /api/app/diet/recognize-photo` | 已實作（`recognize_diet_image()`） | FR-64 | 飲食照片辨識（LLM Vision），App 端專屬能力，Telegram 端沒有對應路由 |
| `POST /api/app/diet/calculate-nutrition` | 已實作（`calculate_diet_image_nutrition()`） | FR-64 | 依確認後的飲食描述計算三大營養素，App 端專屬能力 |
| `POST /api/app/records/<kind>` | 已實作（`create_record()`） | FR-64、FR-68～FR-74a | 泛用記錄新增；`diet` 支援 `nutrition_source=ai/manual` 與人工營養數值，`exercise`（2026-08-17，FR-47a，批次2）支援 `category_id`（既有類別）或 `custom_category`（新增全域類別，同義詞合併見 `body.find_or_create_exercise_category()`）＋ `use_ai_calorie` 布林值決定熱量來源，`finance` 可選填本人有效的 `trip_id`；重複紀錄預設擋下，可帶 `allow_duplicate` 略過檢查 |
| `PATCH /api/app/records/<kind>/<id>` | 已實作（`update_record()`） | FR-64、FR-68～FR-74a | 泛用記錄更新，沿用飲食／運動輸入來源欄位及記帳行程關聯；歷史（過去）紀錄的異動限制見 `HistoricalRecordError` |
| `DELETE /api/app/records/<kind>/<id>` | 已實作（`delete_record()`） | FR-68～FR-72 | 泛用記錄刪除 |
| `GET /api/app/exercise-categories` | 已實作（`list_exercise_categories()`） | FR-47a | 全域共用運動類別清單，供 Mobile App 表單類別下拉選單使用 |

#### 分析 API 共用契約（2026-08-19）

- 認證：`Authorization: Bearer <access_token>`；範例 Token 僅為假資料。
- Query：todos 使用 `start`、`end`、`calendar_month=YYYY-MM`；body／finance／mood／jobs／exams 使用 `start`、`end`；skills 使用 `date`。
- 日期驗證：todos 為 1～7 天且允許未來；一般分析為 1～30 天且結束日不可晚於今天；skills 僅單日且不可為未來。
- body／finance 的 `goals` 為完整唯讀目標清單，`goal_summary` 為進行中目標依「最近期限、同日最近更新、全無期限最近更新」挑出的單筆摘要。共同欄位包含 `status`、`target_date`、`current_value`、`target_value`、`progress_percent`、`progress_unavailable`、`is_exceeded`。
- body 的 `latest_records.weight|diet|exercise` 與 finance／mood 的 `latest_record` 不受查詢日期區間影響；區間內紀錄仍由各模組的 `weight_records`／`diet_records`／`exercise_records`／`records`／`items` 回傳。
- todos 的 `items` 只含查詢區間內、尚未逾期且狀態為 `pending` 的資料；`overdue_items` 只含台灣日期已逾期且仍為 `pending` 的資料，`overdue_count` 為其件數。逾期待辦沿用 `PATCH /api/app/records/todo/<id>` 完成、延期或取消，不提供刪除入口。
- jobs 的 `recommendations` 只列出查詢區間內未關閉、且 `match_score` 已評分並達門檻（＝60，FR-41e）的前 10 筆職缺；未達門檻或尚未評分（`score` 為 NULL）一律不列入，找不到符合項目時回傳空陣列；`score_distribution` 仍依本期全部已評分職缺統計；`timeline` 為 append-only 應徵狀態歷程。
- exams 的 `certificates[]` 含 `key`、`display_name`、`has_question_bank`；`goals[]` 使用共用目標欄位，`goal_summaries` 以證照 key 對應該證照進行中摘要。可量化分數進度依全部正式成績最高分除以目標分數；非數字分數不猜測進度。`practice` 與 `official_scores` 只回傳查詢區間內資料。
- 求職範例：`GET /api/app/analytics/jobs?start=2026-08-01&end=2026-08-07` 回傳 `{"funnel":{"applied":1},"score_distribution":{"high":2},"recommendations":[{"title":"後端工程師","company_name":"範例公司","match_score":88,"url":"https://example.com/job"}],"timeline":[]}`。
- 考試範例：`GET /api/app/analytics/exams?start=2026-08-01&end=2026-08-07` 回傳 `{"certificates":[{"key":"toeic","display_name":"TOEIC","has_question_bank":true}],"goals":[],"goal_summaries":{"toeic":null},"practice":[],"official_scores":[]}`。
- 錯誤：日期格式或範圍不合法回 400、Owner 功能未開啟回 409、無權存取 Owner 模組回 403、未預期錯誤回安全化 503 文案。

```json
{
  "range": { "start": "2026-08-19", "end": "2026-08-19" },
  "goal_summary": {
    "id": 12,
    "description": "存下 10000 元",
    "status": "active",
    "target_date": "2026-12-31",
    "current_value": 2500,
    "target_value": 10000,
    "progress_percent": 25,
    "progress_unavailable": false,
    "is_exceeded": false
  },
  "latest_record": { "id": 88, "date": "2026-08-19", "can_edit": true }
}
```

### 收藏清單（`src/api/app_collections.py`，url_prefix `/api/app/collections`）

> 對應 SPEC FR-73。
> 收藏寫入欄位為 `item_type`、`title`、`country_name`、`city_name`、選填 `country_code`、`address`、
> `latitude`／`longitude`、`source_url`、`estimated_cost`、`notes`。國家及區域／城市必填，地址對所有
> 類型皆為選填；未填地址時可用國家與區域／城市取得近似座標。`currency_code` 固定為 `TWD`；不接受用戶端直接設定
> `priority`、`desired_date`、`administrative_area`、`trip_id`、`status` 或 `visited_at`。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /api/app/collections` | 已實作（`list_collection_items()`） | FR-73／FR-73a | 依國家／區域城市／類型／推導狀態篩選個人收藏，按最近更新時間排序；同時回傳 `goals` 與最近到期的 `goal_summary`，進度為目前已造訪數減設定目標時基準值 |
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
| `PATCH /api/app/life/achievements/<id>/pin` | 已實作 | FR-76b | Request 為 `{ "pinned": true／false }`；只允許本人置頂或取消置頂，回傳共用的 `pinned_at` 狀態 |
| `POST /api/app/life/achievement-candidates/<id>/decision` | 已實作 | FR-76 | `accept=true／false` 接受或拒絕成果候選；拒絕後相同 `candidate_key` 不重複提示 |

`PATCH /api/app/life/achievements/<id>/pin` 使用 Bearer Access Token；成功回傳
`{ "id": 8, "pinned": true, "pinned_at": "2026-08-19T10:30:00+08:00", "message": "成果已置頂" }`。
`pinned` 非布林值回 400；成果不存在或不屬於本人回 404；未預期錯誤回安全的 503 訊息。

> FR-75 Nominatim 呼叫由後端代理，需設定 `NOMINATIM_USER_AGENT`；未設定時回 503，不會以匿名預設值呼叫公開服務。

### 重要日子設定（`src/api/app_important_days.py`，url_prefix `/api/app/important-days`）

> App 端管理介面與資料結構已完成；Telegram 提醒由統一重要日子發送器處理，
> 依通知對象、提前天數與個人通知開關發送，並以送達紀錄去重。

| 項目 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `GET /api/app/important-days` | 已實作（`list_important_days()`） | FR-72a／FR-74b | 查詢個人設定的重要日子清單，並附家人使用者名單供選擇對象；名單的 `user_id` 不存於 `users` 表，而是依 FR-65 由 `users.id` 動態格式化為 `user01`、`user10` |
| `POST /api/app/important-days` | 已實作（`create_important_day()`） | FR-72a／FR-74b | 新增一筆重要日子設定 |
| `PATCH /api/app/important-days/<id>` | 已實作（`update_important_day()`） | FR-72a／FR-74b | 更新一筆重要日子設定 |
| `DELETE /api/app/important-days/<id>` | 已實作（`delete_important_day()`） | FR-72a／FR-74b | 刪除一筆重要日子設定 |

## 未分類

（無——目前文件列出的 104 個項目皆可依內容明確對應到上述功能分組。）
