---
title: DB Schema
updated: 2026-08-15
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
> 本文件目前涵蓋到 migration `0061`（`system_error_reports`）為止；`0062` 之後（Mobile App 帳密欄位、
> 探索紀錄／旅遊模組、成就系統等）尚未回頭補登，見 `src/migrations/` 目錄與 `docs/specs/SPEC.md`
> 對應功能區塊掌握最新範圍。CREATE TABLE 語法只保留欄位定義本身，`COMMENT ON` 逐欄註解請直接看
> 對應 migration 檔案，不在此重複。

## Mobile App 生活探索與成果（Phase 5）

| Migration | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `0071`～`0077` | 已建立 | 前置 POC | 建立 `trips`、`collection_items`、`exploration_events`、舊版每日行程、探索照片、成果及 `transactions.trip_id` |
| `0079_align_life_exploration_phase5.sql` | 待套用 | FR-73～FR-76a | 以追加 migration 對齊 2026-08-14 定案規格，不回寫既有 migration |
| `0080_create_geocoding_cache.sql` | 待套用 | FR-75 | 建立 Nominatim 地址轉座標快取；以正規化查詢字串唯一去重，保存座標、顯示名稱及來源 |

`0079` Schema 異動摘要：

- `trips`：起訖日期改為規劃中可空值；狀態改為 `planning／confirmed／completed／cancelled`；新增國家、區域／城市、六種新台幣分類預估支出及 `deleted_at`。
- `trip_collection_items`：新增收藏與旅遊行程多對多關聯，保存排序、實際造訪結果、探索事件關聯與名稱快照。
- `trips.sync_to_important_day`／`trips.important_day_id`：控制 FR-74b 行程是否同步一次性重要日子，並以外鍵保存穩定的一對一連動關係；關閉同步、取消或刪除行程時只停用重要日子。
- `collection_items`：新增 `deleted_at` 供刪除復原；既有 `priority／desired_date／administrative_area／trip_id` 暫不刪欄，只停止由新版 API／UI 寫入。
- `exploration_events`：新增原收藏關聯、來源網址與 `deleted_at`；原有位置、日期及文字欄位作為造訪快照。
- `user_achievements`：建立來源統一為 `manual／suggested`，新增 `deleted_at`。
- `achievement_candidates`：新增使用者成果候選、來源、完成日期與 `pending／accepted／rejected` 決策狀態，同一使用者的 `candidate_key` 唯一以防重複提示。
- 所有既有記帳金額仍只存於 `transactions`；`trip_id` 沿用 `0077`，不複製實際支出。

`0080` Schema 異動摘要：

- `geocoding_cache`：以 `query_key` 唯一約束快取地址查詢，保存原查詢、緯度、經度、顯示名稱、Nominatim 來源與時間戳；座標具合法範圍檢查。

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
    monthly_budget NUMERIC(12,2),                                    -- 0018 追加
    budget_alert_50_sent_month DATE,                                 -- 0018 追加
    budget_alert_80_sent_month DATE,                                 -- 0018 追加
    finance_reminder_sent_date DATE,                                 -- 0021 追加
    finance_monthly_report_sent_month DATE,                          -- 0022 追加
    height_cm NUMERIC(5,1) CHECK (height_cm BETWEEN 140 AND 220),    -- 0023 追加
    birthday DATE,                                                   -- 0028 追加
    toeic_weekly_question_count INT NOT NULL DEFAULT 21,             -- 0037 追加
    toeic_pipeline_last_run_on DATE,                                 -- 0037 追加
    waist_cm NUMERIC(5,1) CHECK (waist_cm BETWEEN 40 AND 200),       -- 0046 追加
    certificate_answer_reminder_sent_on DATE,                        -- 0048 追加
    youtube_last_run_on DATE,                                        -- 0051 追加
    job_resume TEXT,                                                 -- 0053 追加
    job_expectation TEXT,                                            -- 0053 追加
    years_of_experience NUMERIC(4,1),                                -- 0053 追加
    expected_salary_min INT,                                         -- 0053 追加
    expected_salary_max INT,                                         -- 0053 追加
    job_search_last_run_on DATE                                      -- 0053 追加
);
```
`src/migrations/0001_create_users_table.sql`（後續 12 個 migration 陸續 `ALTER TABLE` 新增，見上方註解編號）

- `telegram_user_id` 允許 NULL：家人設定通關密碼當下就先建立記錄，綁定成功才補上；Postgres `UNIQUE` 允許多筆 NULL 並存
- `is_owner` 由程式依 `telegram_user_id` 是否等於 `ROBIN_TELEGRAM_TOKEN` 判斷寫入
- 後續各模組陸續在此表新增個人化設定欄位，皆以「新增可選欄位、不動既有結構」為原則；記帳（monthly_budget／三個去重欄位）對應 FR-41～FR-44a，體態（height_cm／waist_cm）對應 FR-46，生日對應 FR-53，TOEIC（toeic_weekly_question_count／toeic_pipeline_last_run_on）對應 Step 3.2，證照作答提醒／YouTube 週推播去重對應 FR-28／FR-59a，求職五個履歷欄位對應 FR-36；逐欄 `COMMENT ON` 與核准脈絡見對應 migration 檔案

```sql
CREATE TABLE invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    user_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`src/migrations/0002_create_invite_codes_table.sql`

- 不重複存 `role`（已在 `users.role`，透過 `user_id` 查得到）
- `code UNIQUE` 避免重複；`is_used`＋`updated_at` 記錄是否用過、何時變更，符合一次性使用規則
</details>

## Gemini 對話核心

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `knowledge_base` | 已建立 | FR-9（前三類） | 知識庫：`general_persona`／`general_family`（全體共用）／`custom`（個人客製，含 `label` 分類欄位） |
| `conversation_logs` | 已建立 | FR-9（第④類） | 個人化完整對話歷史，`content` 已過個資遮蔽，`deleted_at` 軟刪除 |
| `conversation_summaries` | 已建立 | chat-core ADR-3 | 長記憶滾動摘要，每人一筆，`summarized_up_to_log_id` 標記摘要進度 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE knowledge_base (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('general_persona', 'general_family', 'custom')),
    user_id BIGINT REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_knowledge_base_user_id ON knowledge_base (user_id);
```
`src/migrations/0003_create_knowledge_base_table.sql`（建表）、`0006_seed_persona_and_family_knowledge.sql`（種子資料）、`0012_add_label_to_knowledge_base.sql`（2026-08-01 新增 `label TEXT`，供 FR-11 主動記知識分類與 FR-12 刪除範圍判斷參考）

- `category` 用 CHECK 限制三種值；`user_id` 允許 NULL 代表兩種通用類別全體共用，`custom` 才指向特定使用者
- `general_family` 內容曾兩度用 `UPDATE` 補正（2026-07-31 民國年換算西元年對照修正家庭成員生日誤判、新增阿姨資料；2026-08-01 新增家庭寵物資料），見 `0009`／`0010`／`0011` migrations

```sql
CREATE TABLE conversation_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_conversation_logs_user_id_created_at ON conversation_logs (user_id, created_at);
```
`src/migrations/0004_create_conversation_logs_table.sql`

- `content` 存的內容已過 FR-13 個資遮蔽，不存未遮蔽原文；`deleted_at` 軟刪除保留稽核軌跡

```sql
CREATE TABLE conversation_summaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    summary TEXT NOT NULL DEFAULT '',
    summarized_up_to_log_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`src/migrations/0007_create_conversation_summaries_table.sql`

- 每人一筆（UPDATE 覆蓋），backlog 累積到 10 則以上才觸發摘要更新；摘要呼叫用 `GEMINI_API_TEXT_KEY`
</details>

## 功能開關系統

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `feature_toggles` | 已建立 | FR-2 | 每位使用者各功能模組獨立開關；2026-08-07 `skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE feature_toggles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    feature_key TEXT NOT NULL CHECK (feature_key IN (
        'todo', 'job_search', 'budget', 'body', 'tech_intel', 'certificate', 'language',
        'mood_journal', 'friend_mode', 'important_notify'
    )),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, feature_key)
);
```
`src/migrations/0005_create_feature_toggles_table.sql`（建表）、`0034_split_skill_growth_toggle.sql`（2026-08-07 拆分）

- `feature_key` 用 CHECK 鎖定模組英文代號；`UNIQUE (user_id, feature_key)` 確保每人每功能一筆
- 新使用者綁定成功時由程式邏輯一次補齊全部預設值（`is_enabled=TRUE`），非 schema 責任
</details>

## 影像辨識

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `media_uploads` | 已建立 | ADR-13（圖片）／FR-14、FR-15（語音沿用） | 圖片/語音上傳的 Google Drive 網址記錄；`created_at` 同時作為語音 15 分鐘修正窗口判斷依據 |

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
| `todos` | 已建立 | FR-31、FR-31a、FR-31b、FR-32 | 待辦事項；`start_at`（2026-08-02）支援時間區間，NULL 代表單一時間點 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE todos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    remind_before_30min BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'expired')),
    reminded_30min_sent_at TIMESTAMPTZ,
    daily_pushed_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    start_at TIMESTAMPTZ
);
CREATE INDEX idx_todos_user_id_status ON todos (user_id, status);
CREATE INDEX idx_todos_due_at ON todos (due_at);
```
`src/migrations/0013_create_todos_table.sql`（建表）、`0016_add_start_at_to_todos.sql`（`start_at`，FR-31b）

- `reminded_30min_sent_at`／`daily_pushed_on` 是去重記號，存在 DB（非記憶體）以撐過 Render 重啟；推播機制借用 `/healthz` 既有 10 分鐘 cron 頻率，不另建排程系統
- `start_at` 為可選欄位而非把 `due_at` 改成必填區間兩欄，是為了讓既有單一時間點待辦零改動；跨模組歧義判斷（FR-31）Phase 1 暫不實作
</details>

## 心情小記

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `mood_journals` | 已建立 | FR-49、FR-50 | 心情小記；`entry_date`（2026-08-02）支援補記過去日期，NULL 舊資料 fallback 用 `created_at` |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE mood_journals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    mood_category TEXT NOT NULL CHECK (mood_category IN (
        'angry_anxious', 'sad_down', 'tired_burned_out', 'neutral', 'calm_relaxed', 'happy_excited'
    )),
    content TEXT NOT NULL,
    achievement_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    entry_date DATE
);
CREATE INDEX idx_mood_journals_user_id ON mood_journals (user_id);
```
`src/migrations/0014_create_mood_journals_table.sql`（建表）、`0017_add_entry_date_to_mood_journals.sql`（`entry_date`）

- `mood_category` 鎖定固定 6 分類；`content`／`achievement_note` 皆過 FR-13 個資遮蔽
- `entry_date` 一律由 app 端算好台灣時區日期後寫入，不依賴 DB 預設值（避免 UTC 午夜前後差一天）
</details>

## 客訴收集

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `complaints` | 已建立 | FR-60～FR-63 | 客訴/意見回饋原始內容（已過個資遮蔽）；Gemini 分析結果只即時私訊 Robin，刻意不落地存表 |

<details>
<summary>SQL</summary>

```sql
CREATE TABLE complaints (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_complaints_user_id ON complaints (user_id);
```
`src/migrations/0015_create_complaints_table.sql`
</details>

## 記帳

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `transactions` | 已建立 | FR-42 | 支出/收入交易紀錄，`amount` 一律正數，方向由 `type` 決定 |
| `budget_overrides` | 已建立 | FR-41a | 全局預設（存 `users.monthly_budget`）之外的特殊月份預算覆蓋值 |

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

```sql
CREATE TABLE budget_overrides (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, year, month)
);
```
`src/migrations/0020_create_budget_overrides_table.sql`

- 「全局預設＋特殊月份覆蓋」設計（非逐月都存一筆），查詢時 fallback 用 `users.monthly_budget`；`UNIQUE (user_id, year, month)` 確保每人每月僅一筆覆蓋值
</details>

## 體態管理

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `body_weight_logs` | 已建立 | FR-46 | 體重歷史紀錄，`weight_kg >= 40` 為最後防線檢查 |
| `exercise_logs` | 已建立 | FR-47、FR-64 | 運動紀錄支援時間 AI 估算與人工熱量雙模式，並保留來源及重訓內容 |
| `diet_logs` | 已建立 | FR-48、FR-64 | 飲食與飲水共用一表，營養數值可由 AI 估算或人工輸入並保留來源 |
| `body_goals` | 已建立 | FR-45～FR-48／FR-72a | 體重/運動/飲食三子功能共用一表（`goal_type` 區分）；`important_day_id` 連結期限事件 |

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
CREATE TABLE exercise_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    activity TEXT NOT NULL,
    duration_minutes INT NOT NULL CHECK (duration_minutes > 0),
    heart_rate INT,
    estimated_calories NUMERIC(6,1),
    entry_date DATE NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_exercise_logs_user_id ON exercise_logs (user_id);
```
`src/migrations/0025_create_exercise_logs_table.sql`

- 卡路里用 LLM 估算而非 MET 公式；估算失敗時允許 NULL，不擋下整筆紀錄；`activity` 自由文字（項目差異太大無法窮舉）
- `0078_add_mobile_record_input_sources.sql` 將 `duration_minutes` 改為可空，新增 `input_mode`、
  `calorie_source`、`training_details` 與範圍檢查；人工熱量模式不呼叫 LLM。

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

```sql
CREATE TABLE body_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    goal_type TEXT NOT NULL CHECK (goal_type IN ('weight', 'exercise', 'diet')),
    target_description TEXT NOT NULL,
    target_value NUMERIC(6,2),
    baseline_value NUMERIC(6,2),
    target_date DATE,
    important_day_id BIGINT REFERENCES important_days(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'achieved', 'cancelled')),
    achieved_notified BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_body_goals_user_id ON body_goals (user_id);
```
`src/migrations/0027_create_body_goals_table.sql`、`0082_link_goals_to_important_days.sql`

- 三子功能共用一表、`goal_type` 區分，語意隨類型不同由 App 層解讀；`weight` 用 `baseline_value` 判斷增/減方向；`exercise` 用累積分鐘數（各運動類型通用單位）；`diet` 不支援自動達成判斷（太主觀），只能手動標記
</details>

## 重要通知

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `important_notifications_log` | 已建立 | FR-53 | 固定節日與生日的年度推播去重紀錄；農曆節日用 `lunarcalendar` 即時計算，不維護對照表 |

<details>
<summary>SQL 與設計理由</summary>

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

- 一表通用固定節日（英文代碼）與生日（`birthday_<user_id>`）；`UNIQUE (notification_key, year)` 確保同類型同年僅推播一次，即使 `/healthz` 同一天內觸發多次
</details>

## 個人技能成長：每日技術分享與 TOEIC 證照題庫

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `skill_growth_digests` | 已建立 | FR-22、FR-23 | 每日技術摘要收集與推播狀態；2026-08-09 改為「一天多筆、一筆一來源管道」正規化設計（見 `docs/ADR/discuss/skill-growth.md` ADR-25） |
| `certificate_questions`（原 `toeic_questions`） | 已建立 | FR-25a～FR-25c | 證照題庫軌道一（照片/音檔上傳建題），2026-08-07 泛用化支援任意證照類型 |
| `toeic_vocab_questions` | 已建立 | FR-25d、FR-25e | TOEIC 題庫軌道二（Gemini 即時生成單字題），刻意維持 TOEIC 專用不隨軌道一泛用化 |
| `answer_logs` | 已建立 | FR-27、FR-29 | 作答紀錄，跨軌道一/二共用一表；`assignment_id`（2026-08-08 追加）精準對應「今天這一批」 |
| `certificate_goals` | 已建立 | FR-24／FR-72a | 證照準備目標（UPSERT，每人每 `exam_type` 一筆）；`important_day_id` 連結考試日期事件 |
| `exam_official_scores` | 已建立 | FR-30 | 正式應考成績，僅查詢不修改，與每日小考作答紀錄分開建表 |
| `certificate_daily_settings` | 已建立 | FR-26 | 每日出題數量／新題複習題比例／TOEIC 三軌比例設定 |
| `certificate_daily_schedule_overrides` | 已建立 | FR-26 | 彈性排程的日期區間覆蓋（挪動/取消/區間覆蓋/平攤） |
| `certificate_daily_assignments` | 已建立 | FR-27、FR-28 | 每天實際推播的題目記錄 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE skill_growth_digests (
    id BIGSERIAL PRIMARY KEY,
    digest_date DATE NOT NULL,
    source TEXT,
    summary_text TEXT,
    pushed_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (digest_date, source)
);
```
`src/migrations/0052_recreate_skill_growth_digests_per_source.sql`（取代 `0033` 建立的舊表，直接 DROP 重建）

- `source` 區分來源管道（tldr／ithome／techcrunch），`source IS NULL` 保留給「當天完全沒有任何一筆收集結果」的去重標記列；設計演進見 `docs/ADR/discuss/skill-growth.md` ADR-25／ADR-29（含 IThome RSS `pubDate` 解析 bug 修正）

```sql
CREATE TABLE certificate_questions (  -- 原 toeic_questions，0038 migration 改名
    id BIGSERIAL PRIMARY KEY,
    test_id TEXT NOT NULL,
    question_type TEXT NOT NULL CHECK (question_type IN ('write', 'listen')),
    question_number INT NOT NULL,
    question_text TEXT NOT NULL,
    options JSONB NOT NULL,
    image_gdrive_url TEXT NOT NULL,
    audio_gdrive_url TEXT,
    source_image_filename TEXT NOT NULL UNIQUE,
    exam_type TEXT NOT NULL,              -- 0038 追加
    correct_answer TEXT,                  -- 0039 追加
    explanation TEXT,                     -- 0039 追加
    answer_source_filename TEXT UNIQUE,   -- 0039 追加
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_certificate_questions_test_id ON certificate_questions (test_id);
CREATE INDEX idx_certificate_questions_exam_type ON certificate_questions (exam_type);
```
`src/migrations/0035_create_toeic_questions_table.sql`（建表）、`0038_generalize_toeic_questions_to_certificate_questions.sql`（改名＋`exam_type`）、`0039_add_answer_fields_to_certificate_questions.sql`（正解欄位）

- `source_image_filename UNIQUE` 做去重（取代原「檔名日期」方案）；`exam_type` 刻意不加 CHECK 清單，未來新增證照類型只需換檔名前綴；正解改為 Robin 拍照上傳答案照解析，非 AI 推論，見 `docs/ADR/discuss/skill-growth.md`

```sql
CREATE TABLE toeic_vocab_questions (
    id BIGSERIAL PRIMARY KEY,
    target_word TEXT NOT NULL,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option CHAR(1) NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    example_sentence TEXT NOT NULL,
    example_sentence_translation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_toeic_vocab_questions_target_word ON toeic_vocab_questions (LOWER(target_word));
```
`src/migrations/0036_create_toeic_vocab_questions_table.sql`

- `LOWER(target_word)` 唯一索引避免重複生成；每週生成題數由 `users.toeic_weekly_question_count` 決定（預設 21）

```sql
CREATE TABLE answer_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    certificate_question_id BIGINT REFERENCES certificate_questions(id),
    vocab_question_id BIGINT REFERENCES toeic_vocab_questions(id),
    exam_type TEXT NOT NULL,
    question_type TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    answered_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assignment_id BIGINT REFERENCES certificate_daily_assignments(id),  -- 0047 追加
    CONSTRAINT answer_logs_exactly_one_question CHECK (
        (certificate_question_id IS NOT NULL AND vocab_question_id IS NULL)
        OR (certificate_question_id IS NULL AND vocab_question_id IS NOT NULL)
    )
);
CREATE INDEX idx_answer_logs_user_answered_on ON answer_logs (user_id, answered_on);
CREATE INDEX idx_answer_logs_user_exam_type ON answer_logs (user_id, exam_type);
CREATE INDEX idx_answer_logs_assignment_id ON answer_logs (assignment_id);
```
`src/migrations/0040_create_answer_logs_table.sql`（建表）、`0047_add_assignment_id_to_answer_logs.sql`（2026-08-08 追加）

- 兩個可為 NULL 外鍵＋CHECK 串連軌道一/二題庫，單一 SQL 即可完成成效統計；`assignment_id` 解決複習池機制下同題被指派多次時「是否已作答」判斷不精準的問題

```sql
CREATE TABLE certificate_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    target_date DATE,
    target_score TEXT,
    important_day_id BIGINT REFERENCES important_days(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_type)
);
```
`src/migrations/0041_create_certificate_goals_table.sql`、`0082_link_goals_to_important_days.sql`

- `UNIQUE (user_id, exam_type)` UPSERT 設計；`target_score` 用 TEXT 相容量化分數與通過/未通過兩種形式

```sql
CREATE TABLE exam_official_scores (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    exam_date DATE NOT NULL,
    score TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_exam_official_scores_user_exam_type ON exam_official_scores (user_id, exam_type);
```
`src/migrations/0042_create_exam_official_scores_table.sql`

- 不加 UNIQUE：同一 `exam_type` 可能多次應考，每次獨立一筆

```sql
CREATE TABLE certificate_daily_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    daily_question_count INT NOT NULL DEFAULT 6,
    review_ratio_new INT NOT NULL DEFAULT 7,
    review_ratio_review INT NOT NULL DEFAULT 3,
    listen_ratio INT,
    write_ratio INT,
    vocab_ratio INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_type)
);
```
`src/migrations/0043_create_certificate_daily_settings_table.sql`

- 三軌比例（`listen_ratio`／`write_ratio`／`vocab_ratio`）只有 TOEIC 使用；新題/複習題比例通用所有 `exam_type`，兩組維度刻意分開欄位（見 `docs/ADR/discuss/skill-growth.md` ADR-20）

```sql
CREATE TABLE certificate_daily_schedule_overrides (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    daily_question_count INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date),
    CHECK (daily_question_count >= 0)
);
CREATE INDEX idx_certificate_daily_schedule_overrides_user_exam_type
    ON certificate_daily_schedule_overrides (user_id, exam_type);
```
`src/migrations/0044_create_certificate_daily_schedule_overrides_table.sql`

- 比照 `budget_overrides`「全局預設＋特殊區間覆蓋」模式；`daily_question_count=0` 代表取消當天

```sql
CREATE TABLE certificate_daily_assignments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    assigned_date DATE NOT NULL,
    certificate_question_id BIGINT REFERENCES certificate_questions(id),
    vocab_question_id BIGINT REFERENCES toeic_vocab_questions(id),
    is_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT certificate_daily_assignments_exactly_one_question CHECK (
        (certificate_question_id IS NOT NULL AND vocab_question_id IS NULL)
        OR (certificate_question_id IS NULL AND vocab_question_id IS NOT NULL)
    )
);
CREATE INDEX idx_certificate_daily_assignments_user_date
    ON certificate_daily_assignments (user_id, assigned_date);
```
`src/migrations/0045_create_certificate_daily_assignments_table.sql`

- 作答狀態不落地在本表，靠查 `answer_logs.assignment_id` 判斷，避免兩表狀態互相不同步
</details>

## YouTube 技術情報模組

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `youtube_topics` | 已建立 | FR-57a | 多組主題設定，`last_recommended_on` 供輪替公平性判斷 |
| `youtube_pushed_videos` | 已建立 | FR-58d | 歷史推播紀錄，去重靠查詢邏輯（過去 30 天內排除） |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE youtube_topics (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    topic TEXT NOT NULL,
    last_recommended_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, topic)
);
```
`src/migrations/0049_create_youtube_topics_table.sql`

- `last_recommended_on` NULL 視為最優先；設計改採 LLM 語意判讀＋多組主題輪替，取代原 Rule-based 規劃，見 `docs/ADR/discuss/youtube-intel.md` ADR-21

```sql
CREATE TABLE youtube_pushed_videos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    video_id TEXT NOT NULL,
    topic TEXT,
    pushed_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_youtube_pushed_videos_user_pushed_on ON youtube_pushed_videos (user_id, pushed_on);
```
`src/migrations/0050_create_youtube_pushed_videos_table.sql`

- 不加 `video_id` UNIQUE：同一支影片 30 天後可能再次推薦，去重靠查詢邏輯篩選時間窗口
</details>

## 求職模組

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `job_search_criteria` | 已建立 | FR-33 | 多組搜尋條件，`industry` 欄位 2026-08-09 起停用（保留於 DB 不刪除） |
| `job_companies` | 已建立 | FR-35 | 104 公司背景，`source`（2026-08-09）擴充支援外部管道公司共用 |
| `job_postings` | 已建立 | FR-34 | 104 職缺，陸續擴充 `is_closed`／評分欄位／`source` |
| `job_applications` | 已建立 | FR-39c | 應徵狀態歷程，append-only 設計 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE job_search_criteria (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    keyword TEXT NOT NULL,
    region TEXT,
    salary_min INT,
    salary_max INT,
    industry TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_job_search_criteria_user_id ON job_search_criteria (user_id);
```
`src/migrations/0054_create_job_search_criteria_table.sql`

- 不設唯一約束：允許同時存多組條件；`industry` 欄位停用後保留於 DB（不做破壞性刪除），對話流程已不再收集寫入

```sql
CREATE TABLE job_companies (
    id BIGSERIAL PRIMARY KEY,
    company_id_104 TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    region TEXT,
    industry TEXT,
    background TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL DEFAULT '104'  -- 0059 追加
);
```
`src/migrations/0055_create_job_companies_table.sql`（建表）、`0059_add_source_to_job_postings_and_companies.sql`（`source`）

- `background` NULL 代表待 Robin 人工查詢回填（Email/CSV/Drive 協作）；`source` 讓外部管道（LinkedIn／Cake）公司共用同一表，外部來源用系統配發合成 ID（`EXT-<序號>`）

```sql
CREATE TABLE job_postings (
    id BIGSERIAL PRIMARY KEY,
    job_id_104 TEXT NOT NULL UNIQUE,
    company_id_104 TEXT NOT NULL REFERENCES job_companies (company_id_104),
    title TEXT NOT NULL,
    region TEXT,
    url TEXT NOT NULL,
    salary_min INT,
    salary_max INT,
    content TEXT,
    required_years_experience NUMERIC(4,1),
    applicant_count INT,
    source_updated_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_crawled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,  -- 0057 追加
    score NUMERIC(5,2),                        -- 0058 追加
    recommend_reason TEXT,                      -- 0058 追加
    skill_gap_note TEXT,                        -- 0058 追加
    is_unliked BOOLEAN NOT NULL DEFAULT FALSE,  -- 0058 追加
    source TEXT NOT NULL DEFAULT '104'          -- 0059 追加
);
CREATE INDEX idx_job_postings_company_id_104 ON job_postings (company_id_104);
```
`src/migrations/0056`（建表）、`0057`（`is_closed`）、`0058`（評分欄位）、`0059`（`source`）

- `job_id_104 UNIQUE` 作 ETL 去重鍵；`is_closed` 由 104 API `jobSwitch`/`switch` 欄位自動判斷；`score`/`recommend_reason`/`skill_gap_note` 由 FR-37 週批次評分寫入；刻意不建 `rank` 欄位（全庫/本週新職缺兩種排名並存，動態計算不持久化）；`source` 讓外部管道職缺共用同一表並沿用既有評分/排名邏輯
- Mobile 求職分析 SQL 讀取正式欄位 `score`，並以 `score AS match_score` 對外維持既有 API 欄位名稱；資料庫本身沒有 `match_score` 欄位

```sql
CREATE TABLE job_applications (
    id BIGSERIAL PRIMARY KEY,
    job_id_104 TEXT NOT NULL REFERENCES job_postings (job_id_104),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_job_applications_job_id_104 ON job_applications (job_id_104);
```
`src/migrations/0060_create_job_applications_table.sql`

- append-only：每次狀態變更新增一筆而非 UPDATE，保留完整時間軸，「目前狀態」＝最新一筆
</details>

## 服務健康與治理

| 資料表 | 狀態 | 對應 FR | 說明 |
| --- | --- | --- | --- |
| `system_error_reports` | 已建立 | FR-19j | 系統例外自動記錄與解法追蹤；`error_summary` 寫入前先去除 URL 查詢字串 |

<details>
<summary>SQL 與設計理由</summary>

```sql
CREATE TABLE system_error_reports (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity TEXT NOT NULL,
    triggering_feature TEXT,
    error_summary TEXT NOT NULL,
    drive_log_url TEXT,
    resolution TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`src/migrations/0061_create_system_error_reports_table.sql`

- 讓既有「私訊 Robin＋Drive log 連結」機制額外落地一份可查詢紀錄；`resolution` NULL 代表尚未處理；與 `complaints` 刻意分開（使用者主動客訴 vs 系統主動錯誤回報，性質不同）
</details>

## 未分類

（無——所有 33 張資料表皆可依內容明確對應到上述功能分組。）
