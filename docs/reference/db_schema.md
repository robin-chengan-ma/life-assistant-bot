---
title: DB Schema
updated: 2026-11-26
---

# DB Schema

## 後續資料模型準則

- 本專案既有正式資料表不因正規化整理而刪除重建；新需求確有需要時，經 SQL 審核後以向前相容 Migration 新增獨立資料表或必要欄位。
- 每個功能領域使用自己的資料表；可依正規化拆成多張表並使用 Primary Key／Foreign Key 串接，不再把其他功能設定、排程狀態或紀錄塞入 `users`。
- 新表必須具備直覺且精簡的名稱，並依商業語意採用資料庫層 `NOT NULL`／`CHECK`／`UNIQUE`／Foreign Key 約束；只有真正必填欄位使用 `NOT NULL`，選填、尚未產生或未知值應保留 `NULL`，不得以占位值冒充。每張表仍須具備完整 `COMMENT ON TABLE` 與逐欄 `COMMENT ON COLUMN`。
- 時間預設與更新優先由 SQL `DEFAULT now()`／Trigger 維護；可推導的年度、月份與彙總資訊優先在查詢時計算，必要時才使用 Generated Column、Expression Index 或 Materialized View。
- 本節是未來 Schema 的強制規則，不追溯要求破壞既有資料；完整通用規則見根目錄 `AGENTS.md`「Database Schema Design」。

> 技術參考文件，跟著程式碼異動更新，不是決策紀錄（決策放 `docs/ADR/discuss/`）也不是產品規格（放
> `docs/specs/SPEC.md`）。內容力求簡述：一行講得完就不要展開成段落，需要脈絡時用連結指回
> `docs/ADR/discuss/<功能>.md` 或 `docs/specs/PROGRESS.md` 的推版紀錄，不要把歷史敘事寫在這裡。
>
> 本文件記錄 Neon PostgreSQL 上所有資料表的建表 SQL 與設計理由。依 `docs/specs/SPEC.md`
> 「平台架構與治理」區塊 NFR-12／`src/migrations/README.md`，任何建表／改表操作都必須「先給 Robin
> 看 SQL 語法＋說明設計理由→取得同意」，才會存成 `src/migrations/` 底下的檔案，經 commit/push 由
> Render 自動部署套用（實際套用時間以資料庫 `schema_migrations` 追蹤表為準）。
>
> 本文件已涵蓋至 migration `0106`。2026-11（Robin 明確決策）功能大幅精簡：Telegram 選單只保留
> 運動/飲食/體態、記帳、待辦事項（簡化為純一次性提醒）、生日設定（簡化為純週期性生日）、權限管理；
> `0101`～`0103` 移除心情小記、收藏與旅遊、成果展示、跨模組目標追蹤、功能開關、YouTube 技術情報、
> 求職模組、TOEIC／證照題庫、個人技能成長電子報、系統錯誤管理與告警等已刪除功能的資料表，並清空
> 運動/飲食/體態與記帳的既有資料、簡化 `todos`／`important_days` 欄位結構（詳見下方對應章節與
> `src/migrations/0101_drop_cancelled_feature_tables.sql`／`0102_wipe_and_simplify_todos_and_logs.sql`／
> `0103_simplify_important_days_to_birthdays.sql`）。CREATE TABLE 語法只保留欄位定義本身，
> `COMMENT ON` 逐欄註解請直接看對應 migration 檔案，不在此重複。

## 平台核心入口

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `users` | 已建立 | FR-5～FR-8 | 每一位使用者（含 Robin），`telegram_user_id` 綁定前為 NULL；後續多個模組陸續在此表加欄位存個人化設定值（見下方展開） |
| `invite_codes` | 已建立 | FR-6～FR-6d | Robin 為每位家人設定的一次性通關密碼，`user_id` 必填（設密碼當下就先建立對應 `users` 記錄） |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE,
    role TEXT NOT NULL,
    is_owner BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finance_reminder_sent_date DATE,                                 -- 0021 追加
    height_cm NUMERIC(5,1) CHECK (height_cm BETWEEN 140 AND 220),    -- 0023 追加
    waist_cm NUMERIC(5,1) CHECK (waist_cm BETWEEN 40 AND 200),       -- 0046 追加
    -- 0083 追加：
    nickname TEXT,                                                   -- FR-4a 暱稱，與家庭稱謂、授權身分分開保存
    family_title TEXT,                                               -- FR-4a 家庭稱謂（例如「爸爸」），只作顯示用途
    is_active BOOLEAN NOT NULL DEFAULT TRUE,                         -- FR-4d 帳號是否啟用（停用不刪除帳號與資料）
    -- 0098 追加：
    mobile_login_failed_attempts INT NOT NULL DEFAULT 0,             -- FR-65a 連續密碼錯誤次數，登入成功歸零
    mobile_login_locked_at TIMESTAMPTZ,                              -- FR-65a NULL＝未鎖定；有值＝鎖定時間，僅 Owner 手動解鎖
    full_name TEXT                                                   -- 0108 追加：全名，區分同稱謂但不同人的家人
);
```
`src/migrations/0001_create_users_table.sql`（後續多個 migration 陸續 `ALTER TABLE` 新增，見上方註解編號；完整清單見各 migration 檔案）

- `telegram_user_id` 允許 NULL：家人設定通關密碼當下就先建立記錄，綁定成功才補上；Postgres `UNIQUE` 允許多筆 NULL 並存
- `is_owner` 由程式依 `telegram_user_id` 是否等於 `ROBIN_TELEGRAM_TOKEN` 判斷寫入
- 後續各模組陸續在此表新增個人化設定欄位，皆以「新增可選欄位、不動既有結構」為原則；記帳（monthly_budget／三個去重欄位）對應 FR-41～FR-44a，體態（height_cm／waist_cm）對應 FR-46，生日對應 FR-53；逐欄 `COMMENT ON` 與核准脈絡見對應 migration 檔案
- **2026-11（`0101`，功能大幅精簡）**：TOEIC／證照、YouTube、求職模組隨對應功能整批移除，拿掉 `toeic_weekly_question_count`／`toeic_pipeline_last_run_on`／`certificate_answer_reminder_sent_on`／`youtube_last_run_on`／`job_resume`／`job_expectation`／`years_of_experience`／`expected_salary_min`／`expected_salary_max`／`job_search_last_run_on` 共 10 個欄位
- **2026-11-26（`0104`，ADR 再修正，見 `docs/ADR/discuss/robinson.md`）**：確認「設定記帳預算」「設定體態目標」兩項功能從頭到尾沒有任何設定入口（純死碼，`finance.py`／`body.py` 對應函式與 `budget_overrides`／`body_goals` 資料表一併移除），拿掉 `monthly_budget`／`budget_alert_50_sent_month`／`budget_alert_80_sent_month`／`finance_monthly_report_sent_month` 共 4 個欄位；同一批修正也發現 `birthday` 欄位（0028 追加）早已沒有任何寫入路徑、且首頁查詢會把所有人的生日混進每個人的清單（隱私外洩），一併移除，改用 `important_days` 表（生日設定）取代
- **2026-08-15（0083，Phase 6 第一批，FR-4a／FR-4d）**：`role` 欄位過去混用「Robin 標記」與「家人稱謂」兩種語意，新增 `nickname`／`family_title` 分開保存，`role` 保留不刪除（向前相容，尚未有 DROP 排程）；新增 `is_active` 供 Owner 停用／恢復使用者，預設 `TRUE`，停用時程式一併清空 `refresh_token_hash`／`refresh_token_expires_at`（沿用 0062 既有欄位）撤銷 Mobile 存取
- **2026-08-23（0098，FR-65a，見 `docs/ADR/discuss/mobile-app.md` 條目）**：Mobile App 帳密登入新增連續錯誤鎖定，`mobile_login_failed_attempts` 每次密碼錯誤累加、登入成功歸零；累加達 2 次時寫入 `mobile_login_locked_at`（鎖定時間），之後 `AppAuthService.login()` 直接拋 `AccountLockedError` 擋下，不再比對密碼；解鎖只能由 Owner 在 Telegram「權限管理→🔓 解鎖 Mobile App 帳號」按鈕操作（`auth.unlock_mobile_login()`），清空兩欄，不會自動過期。與 `invite_codes` 通關密碼鎖定不同，這裡刻意落地 DB（理由：需要 Owner 手動解鎖、且必須撐過 Render 服務重啟）
- **2026-11-26（0108，見 `docs/ADR/discuss/robinson.md`）**：Robin 反饋暱稱／家庭稱謂可能無法分辨真實身份（例如不同家人的父母都叫「媽媽」），新增 `full_name`（全名），`create_user_and_invite()` 建立使用者時改為必填；生日推播「自行選擇」對象清單（`AppImportantDayService.family_users()`）改優先顯示 `full_name`。既有 4 筆資料嘗試依 nickname／family_title／role 比對回填（Robin／馬承安、羽璇／廖羽璇、阿佑／范宗佑、媽媽／范麗芳），比對不到的維持 NULL，之後由 Owner 透過 Telegram 權限管理手動補齊

```sql
CREATE TABLE invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    user_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL                                  -- 0083 追加，FR-4b：建立起 24 小時有效
);
```
`src/migrations/0002_create_invite_codes_table.sql`、`src/migrations/0083_restructure_user_identity_and_active_status.sql`

- **2026-08-15（0083，FR-4b／FR-4c）**：新增 `expires_at`，歷史未使用密碼一併補上（建立時間 +24 小時）再設為 `NOT NULL`。連續輸入錯誤 5 次鎖定 30 分鐘的計數**不落地存資料庫**，改在 `src/bot/auth.py` 以 process 記憶體字典（key 為 `telegram_user_id`）保存，理由：綁定成功前系統還不知道這個 Telegram 使用者對應哪筆 `users` 記錄，無法把鎖定狀態掛在 `invite_codes` 或 `users` 上；比照既有 NFR-2「Owner 設定對話流狀態存 process 記憶體」的簡化原則，服務重啟會遺失鎖定計數，刻意簡化
- 不重複存 `role`（已在 `users.role`，透過 `user_id` 查得到）
- `code UNIQUE` 避免重複；`is_used`＋`updated_at` 記錄是否用過、何時變更，符合一次性使用規則
</details>

## Gemini 對話核心

| Migration | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `0094_drop_cancelled_chat_tables.sql` | 已套用 | FR-77 | 已移除 `knowledge_base`、`conversation_logs`、`conversation_summaries`；舊 migration 保留不改寫，且未使用 `CASCADE` |

## 通知接收設定

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `notification_preferences` | 已套用 | FR-6f～FR-6g／FR-20a | 每位使用者、每種通知的接收開關與可選推播小時；關閉通知不停止來源功能或背景工作 |

```sql
CREATE TABLE notification_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_key TEXT NOT NULL CHECK (notification_key IN (
        'todo', 'important_day', 'budget_alert', 'monthly_report',
        'tech_digest', 'youtube', 'job_search', 'exam_quiz'
    )),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notification_hour SMALLINT CHECK (notification_hour BETWEEN 0 AND 23),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, notification_key)
);
CREATE INDEX idx_notification_preferences_user_id ON notification_preferences (user_id);
```

Migration：`0093_create_notification_preferences.sql`。`updated_at` 由資料庫 Trigger 維護；查無資料時應用層預設為接收，避免升級後意外停止既有通知。

- `feature_key` 用 CHECK 鎖定模組英文代號；`UNIQUE (user_id, feature_key)` 確保每人每功能一筆
- 新使用者綁定成功時由程式邏輯一次補齊全部預設值（`is_enabled=TRUE`），非 schema 責任
</details>

## 影像辨識

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `media_uploads` | 已建立 | ADR-13（圖片）／FR-14（語音沿用） | 圖片／語音／音檔上傳的 Google Drive 網址記錄；`created_at` 僅作建立時間，已不再用於舊 FR-15 的 15 分鐘語音修正窗口判斷 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE media_uploads (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'audio')),
    gdrive_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_media_uploads_user_id ON media_uploads (user_id);
```
`src/migrations/0008_create_media_uploads_table.sql`

- 只存原始檔 `gdrive_url`：壓縮版圖片僅在餵給 Gemini 前於記憶體內即時處理，不落地存回 Drive（見 `docs/ADR/discuss/submodules-core.md`）
- `media_type='audio'` 於 Step 1.4 語音功能上線後共用同一張表，不需另外建表
</details>

## 待辦事項

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `todos` | 已套用（`0102` 精簡、`0106` 改日期區間、`0109` 提前提醒、`0110` 常態性待辦） | — | 2026-11 精簡：純一次性日期（可為區間）＋文字提醒推播，拿掉 status／30 分鐘前提醒／每日摘要；既有資料已清空重來；2026-11-26 再追加可複選提前提醒天數；2026-11-28 再追加「常態性（每月固定一天）」類型 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE todos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    remind_start_date DATE,
    remind_end_date DATE,
    recurrence_type TEXT NOT NULL DEFAULT 'once',
    recurrence_day INTEGER,
    remind_offsets INTEGER[] NOT NULL DEFAULT '{0}',
    reminded_offsets_sent INTEGER[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_todos_user_id ON todos (user_id);
CREATE INDEX idx_todos_remind_start_date ON todos (remind_start_date);
```
`src/migrations/0013_create_todos_table.sql`（原始建表）、`0102_wipe_and_simplify_todos_and_logs.sql`
（2026-11，拿掉 `status`／`remind_before_30min`／`daily_pushed_on`／`start_at`，`due_at` 改名
`remind_at`、`reminded_30min_sent_at` 改名 `reminded_sent_at`，既有資料清空）、
`0106_todo_remind_date_range.sql`（2026-11-26，單一 `remind_at`（固定 09:00 時間點）改成
`remind_start_date`／`remind_end_date` 兩個日期，單日待辦＝兩者相同；推播固定改成「第一天台灣
時間 08:30」，恢復行事曆 UI 選取區間，見 `docs/ADR/discuss/robinson.md`）、
`0109_todo_remind_offsets.sql`（2026-11-26 同日再追加，Robin 要求提前提醒邏輯比照生日設定：
新增 `remind_offsets INTEGER[]`（可複選 `{0,3,7,14}` 天前推播）；待辦是一次性事件、不像生日
每年重複，不能沿用生日那套以年份區分的 `important_notifications_log` 去重機制，改新增
`reminded_offsets_sent INTEGER[]` 記錄「這筆待辦已推播過的 offset」，並移除舊的單一時間戳
`reminded_sent_at`）、`0110_todo_recurrence.sql`（2026-11-28，Robin 要求信用卡／車貸這類每月
固定某一天要繳費的待辦，不想每次都手動新增一筆：新增 `recurrence_type`（`once`／`monthly`）與
`recurrence_day`（1~31，只有 `monthly` 有意義，該月天數不足時退回當月最後一天）；`monthly`
類型沒有日期區間概念，`remind_start_date`／`remind_end_date` 改放寬為可為 `NULL`）

- Robin 明確決策：「待辦事項只是純粹去做通知而已，不需要確認動作，不想增加使用者負擔」，新增/編輯/
  刪除全部改到 Mobile App 做，Telegram 端（`src/bot/todo.py`）只負責讀取與推播
- `reminded_offsets_sent` 是 `once` 類型的去重記號，存在 DB（非記憶體）以撐過 Render 重啟；
  `monthly` 類型不用這個欄位去重（整筆待辦只會記一次、不符合每月重複推播的需求），改沿用生日
  設定那套 `important_notifications_log`（`year` 欄位借用存「年份*100+月份」當去重鍵，讓同一個
  offset 每個月都能重新推播一次）；推播機制借用 `/healthz` 既有固定頻率 cron，由
  `check_and_push_reminders()` 判斷「提醒時間已到、該 offset 還沒推播過」；待辦推播一律只送給
  建立者本人，不提供生日設定的推播對象選擇
</details>

## 已取消功能資料表清理

| Migration | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `0094_drop_cancelled_chat_tables.sql` | 已套用 | FR-77 | 同批已移除空的 `complaints`；未使用 `CASCADE` |
| `0101_drop_cancelled_feature_tables.sql` | 已建立 | — | 2026-11 功能大幅精簡：移除心情小記、收藏與旅遊、成果展示、跨模組目標追蹤、功能開關、YouTube 技術情報、求職模組、TOEIC／證照題庫、個人技能成長電子報、系統錯誤管理與告警對應的全部資料表（詳見各功能章節），並移除 `users` 上對應的 10 個已停用欄位；未使用 `CASCADE` |

## 記帳

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `transactions` | 已建立 | FR-42 | 支出/收入交易紀錄，`amount` 一律正數，方向由 `type` 決定 |

> **2026-11-26（`0104`）**：`budget_overrides`（原 FR-41a「特殊月份預算覆蓋」）經 Robin 確認
> 「設定記帳預算」功能從頭到尾沒有任何 Telegram 或 Mobile App 設定入口（純死碼），已整張表移除，
> 詳見 `docs/ADR/discuss/robinson.md`。

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
    category TEXT NOT NULL CHECK (category IN (
        '餐飲', '交通', '購物', '居住', '娛樂', '醫療', '薪資', '獎金', '其他'
    )),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    note TEXT,
    transaction_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_transactions_user_id ON transactions (user_id);
```
`src/migrations/0019_create_transactions_table.sql`

- FR-41「理財目標」定案為「每月支出預算上限」而非儲蓄目標比對，經 2026-08-04 AskUserQuestion 與 Robin 確認；交易表仍同時記支出/收入，保留未來結餘概念的彈性

`budget_overrides` 原建表於 `src/migrations/0020_create_budget_overrides_table.sql`，已由
`src/migrations/0104_drop_dead_budget_and_body_goal_features.sql` 整張表 `DROP TABLE`。
</details>

## 體態管理

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `body_weight_logs` | 已建立 | FR-46 | 體重歷史紀錄，`weight_kg >= 40` 為最後防線檢查 |
| `exercise_categories` | 已套用 | FR-47a | 全域共用運動類別表，新增自訂類別採正規化比對＋LLM 語意判斷兩段式同義詞合併 |
| `exercise_logs` | 已套用 0084 新結構 | FR-47／FR-47a、FR-64 | 已移除 `input_mode`／`training_details` 並新增 `category_id`；使用新版單一表單結構 |
| `diet_logs` | 已建立 | FR-48、FR-64 | 飲食與飲水共用一表，營養數值可由 AI 估算或人工輸入並保留來源 |

> **2026-11-26（`0104`）**：`body_goals`（原 FR-45～FR-48「體態目標」三子功能）經 Robin 確認
> 「設定體態目標」從頭到尾沒有任何 Telegram 或 Mobile App 設定入口（純死碼，Mobile App 從未實作
> 對應畫面），已整張表移除，連同 `src/services/goal_parser.py`（僅供 `diet` 目標解析用，零其他
> 呼叫者）一併刪除，詳見 `docs/ADR/discuss/robinson.md`。

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE body_weight_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    weight_kg NUMERIC(5,1) NOT NULL CHECK (weight_kg >= 40),
    entry_date DATE NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_body_weight_logs_user_id ON body_weight_logs (user_id);
```
`src/migrations/0024_create_body_weight_logs_table.sql`

- 身高「初始設定、變動才修正」放 `users.height_cm`（腰圍 `waist_cm` 比照，2026-08-08 新增，範圍 40～200 較寬鬆因僅供參考）；體重「有量才記」需獨立多筆歷史表

```sql
CREATE TABLE exercise_categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_exercise_categories_normalized_name ON exercise_categories (normalized_name);

CREATE TABLE exercise_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    category_id BIGINT NOT NULL REFERENCES exercise_categories(id),
    activity TEXT NOT NULL,
    duration_minutes INT NOT NULL CHECK (duration_minutes > 0),
    heart_rate INT,
    note TEXT,
    estimated_calories NUMERIC(6,1),
    calorie_source TEXT NOT NULL CHECK (calorie_source IN ('ai', 'manual')),
    entry_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_exercise_logs_user_id ON exercise_logs (user_id);
CREATE INDEX idx_exercise_logs_category_id ON exercise_logs (category_id);
```
`src/migrations/0025_create_exercise_logs_table.sql`（原始建表）、
`src/migrations/0078_add_mobile_record_input_sources.sql`（曾新增 `input_mode`／`calorie_source`／
`training_details`，已於下方 migration 移除前兩者之外的欄位並整併）、
`src/migrations/0084_redesign_exercise_categories.sql`（2026-08-17，FR-47a，批次2：新增
`exercise_categories` 全域類別表並種子既有固定類別；清空舊 `exercise_logs` 資料後改結構——
`duration_minutes` 恢復必填、新增 `category_id`、沿用 0025 已建立的 `note`、移除 `input_mode`／`training_details`，
`calorie_source` 保留但語意改為單純的「AI 估算／人工輸入」二選一，不再跟「時間／熱量」雙頁籤
綁定）

- 卡路里用 LLM 估算而非 MET 公式；估算失敗時允許 NULL，不擋下整筆紀錄
- `activity` 是類別名稱的 denormalized 快照（寫入當下複製自 `exercise_categories.name`），方便
  清單顯示與既有分析查詢（`app_analytics.py` 的 `STRING_AGG(DISTINCT activity, ...)`）不用額外
  JOIN；`category_id` 才是類別管理與同義詞合併的權威來源
- `exercise_categories` 全域共用（不分使用者），新增自訂類別時先做正規化字串比對（trim／全形轉
  半形／大小寫統一），沒命中才呼叫 LLM 判斷是否為既有類別的同義詞，仍沒命中才新增一筆，LLM 失敗
  一律降級為新增，見 `src/bot/body.py find_or_create_exercise_category()`

```sql
CREATE TABLE diet_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('food', 'water')),
    description TEXT NOT NULL,
    water_ml INT,
    estimated_calories NUMERIC(6,1),
    protein_g NUMERIC(6,1),
    carbs_g NUMERIC(6,1),
    fat_g NUMERIC(6,1),
    entry_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_diet_logs_user_id ON diet_logs (user_id);
```
`src/migrations/0026_create_diet_logs_table.sql`

- 飲食與飲水共用一表、`entry_type` 區分（比照 `transactions.type`），兩者互斥欄位皆允許 NULL；營養拆算靠 LLM（無食物資料庫），回覆需附誤差聲明（FR-17c）
- `0078_add_mobile_record_input_sources.sql` 新增 `nutrition_source`（`ai`／`manual`）與營養數值範圍檢查；
  人工模式要求脂肪、碳水、蛋白質與熱量皆有值，飲水列固定標記為人工來源。

`body_goals` 原建表於 `src/migrations/0027_create_body_goals_table.sql`（後續
`0082_link_goals_to_important_days.sql`／`0087_add_target_unit_to_body_goals.sql`／
`0089_add_target_direction_to_body_goals.sql` 陸續擴充欄位），已由
`src/migrations/0104_drop_dead_budget_and_body_goal_features.sql` 整張表 `DROP TABLE`。
`module_goals`／`goal_summaries`（跨模組目標追蹤，記帳／收藏清單通用目標與每日摘要快取）則已隨
對應功能一併移除，見 `src/migrations/0101_drop_cancelled_feature_tables.sql`。
</details>

## 生日設定

2026-11 精簡（原「重要日子」）：Telegram 端只剩「每年固定（國曆）月/日重複一次的生日」，新增/編輯/
查詢全部改到 Mobile App 做；Telegram（`src/bot/important_days.py`）只負責讀清單與排程推播。

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `important_days` | 已套用（`0103` 精簡、`0105` 多選提前提醒、`0107` 推播對象可選） | FR-53 | 生日設定；拿掉單次事件／浮動（農曆）日期／通知對象／備註／行程或目標連動等舊欄位 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE important_days (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    birth_month SMALLINT NOT NULL CHECK (birth_month BETWEEN 1 AND 12),
    birth_day SMALLINT NOT NULL CHECK (birth_day BETWEEN 1 AND 31),
    remind_offsets INTEGER[] NOT NULL DEFAULT '{0}',                 -- 0105 追加
    audience_mode TEXT NOT NULL DEFAULT 'self'                       -- 0107 追加
        CHECK (audience_mode IN ('self', 'selected', 'everyone')),
    audience_user_ids INTEGER[] NOT NULL DEFAULT '{}',               -- 0107 追加
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`src/migrations/0069_create_important_days.sql`（原始建表，原欄位 `owner_user_id`／`title`／
`recurrence_type`／`event_date`／`event_month`／`event_day` 等）、
`0103_simplify_important_days_to_birthdays.sql`（2026-11，`owner_user_id` 改名 `user_id`、`title`
改名 `name`，新增 `birth_month`／`birth_day`，其餘舊欄位全部移除；`important_day_occurrences`／
`important_day_recipients` 兩張輔助表一併移除）、
`0105_add_remind_offsets_to_important_days.sql`（2026-11-26，可複選提前幾天提醒：0／3／7／14，
預設僅「當天」；詳見 `docs/ADR/discuss/robinson.md`）、
`0107_add_audience_to_important_days.sql`（2026-11-26，推播對象：`self`／`selected`／`everyone`，
預設 `self` 等同舊行為，詳見 `docs/ADR/discuss/robinson.md`）

- `remind_offsets` 可複選，僅允許 `{0, 3, 7, 14}` 的非空子集合；`check_and_push_birthdays()`
  逐一走訪選定天數，各自用 `notification_key = birthday_important_day_{id}_offset_{offset}`
  去重，彼此互不影響（同一天同時命中多個 offset 會各推一次）
- `audience_mode='selected'` 時 `audience_user_ids` 必須至少一筆、且每個 id 必須是真實存在的
  `users.id`；其餘模式 `audience_user_ids` 固定留空陣列；`selected` 模式完全依照勾選名單推播，
  建立者未勾選自己時不會收到

- 既有資料轉換規則：只有舊 `recurrence_type = 'fixed_annual'`（國曆固定每年重複）的既有資料視為
  生日予以保留、`birth_month`／`birth_day` 直接取自舊 `event_month`／`event_day`；`flexible_annual`
  （農曆浮動）與 `one_time`（單次事件，多半是舊版行程／目標自動同步產生的一次性提醒）判斷為
  「不是生日」而捨棄，為本次遷移唯一需要人工判斷之處（Robin 已核准「既有的一次性重要日子資料
  如果不是生日，不在保留範圍內，可以捨棄」）
- 推播去重沿用既有 `important_notifications_log`，`notification_key` 改用
  `birthday_important_day_{important_day_id}`，`UNIQUE (notification_key, year)` 確保同一年只推播一次

```sql
CREATE TABLE important_notifications_log (
    id BIGSERIAL PRIMARY KEY,
    notification_key TEXT NOT NULL,
    year INT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (notification_key, year)
);
```
`src/migrations/0029_create_important_notifications_log_table.sql`

- 本表未隨本次精簡變動；舊版節日／行程／目標相關 `notification_key` 會成為不會再被比對到的孤兒
  紀錄，不影響新版 `birthday_important_day_{id}` key 的比對邏輯
</details>

## 未分類

（無——所有資料表皆可依內容明確對應到上述功能分組。）
