# Robinson 資料庫 Schema

> 本文件記錄 Neon PostgreSQL 上所有資料表的建表 SQL 與設計理由。依 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) 的 ADR-10，任何建表 / 改表操作都必須「先給 Robin 看 SQL 語法 + 說明設計理由 → 取得同意」，不得跳過審核直接執行。
>
> **執行機制（ADR-11）**：同意後，SQL 不是直接對 Neon 執行，而是存成 [`src/migrations/`](../migrations/README.md) 底下的檔案，commit + push 後由 Render 自動部署套用。所以本文件的「記錄時機」是 push 完成當下，實際套用時間以資料庫的 `schema_migrations` 追蹤表為準（下次確認部署成功後可回頭核對）。

## 使用方式

新增一張表時，複製下方樣板，填入實際內容，依「建立時間」由舊到新往下疊加。**不要**回頭修改已核准並執行過的舊紀錄（除非該表結構真的變更，這種情況要新增一筆「變更紀錄」，而不是竄改原始記錄）。

```markdown
### <table_name>

**建立日期**：YYYY-MM-DD
**用途**：<這張表存什麼資料、被哪些 FR 使用>
**Migration 檔案**：`src/migrations/NNNN_xxx.sql`

​```sql
CREATE TABLE ...
​```

**設計理由**：
- <為什麼這樣選型別/欄位/索引/外鍵>

**變更紀錄**（如果有）：
| 日期 | 變更內容 | 原因 | Migration 檔案 |
| --- | --- | --- | --- |
```

---

## 資料表清單

### users

**建立日期**：2026-07-30
**用途**：Telegram Bot 的每一位使用者（含 Robin 本人）。對應 FR-5～FR-8。
**Migration 檔案**：`src/migrations/0001_create_users_table.sql`

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE,
    role TEXT NOT NULL,
    is_owner BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS '使用者表：Telegram Bot 的每一位使用者（含 Robin 本人）；家人在通關密碼設定階段就會先建立一筆，此時 telegram_user_id 尚為 NULL，綁定成功後才補上';
COMMENT ON COLUMN users.id IS '內部主鍵';
COMMENT ON COLUMN users.telegram_user_id IS 'Telegram 使用者 ID；設定通關密碼階段尚未綁定時為 NULL，綁定成功後才寫入';
COMMENT ON COLUMN users.role IS '稱謂，例如「爸爸」；Robin 本人固定寫入 "Robin"';
COMMENT ON COLUMN users.is_owner IS '是否為管理者（Robin），依 telegram_user_id 是否等於 ROBIN_TELEGRAM_TOKEN 判斷後寫入';
COMMENT ON COLUMN users.created_at IS '這筆使用者記錄建立的時間（家人可能設定通關密碼當下就建立，早於實際綁定時間）';
```

**設計理由**：
- `telegram_user_id` 允許 `NULL` 是因為家人在 Robin 用 `/set_invite_codes` 設定通關密碼的當下就會先建立這筆使用者記錄，此時對方還沒傳過訊息、不知道其 Telegram user id，等綁定成功才補上；Postgres 的 `UNIQUE` 允許多筆 `NULL` 並存，不影響唯一性約束
- `role` 存稱謂文字（如「爸爸」），Robin 本人由程式邏輯寫入固定值
- `is_owner` 由程式邏輯依 `telegram_user_id` 是否等於環境變數 `ROBIN_TELEGRAM_TOKEN`（Robin 的 Telegram 使用者 ID）判斷後寫入，用於 FR-5 的管理者權限判斷
- 用 `BIGINT`／`BIGSERIAL` 是因為 Telegram user ID 可能超過一般 `INT` 上限

**變更紀錄**：
| 日期 | 變更內容 | 原因 | Migration 檔案 |
| --- | --- | --- | --- |
| 2026-08-04 | 新增 `monthly_budget`（每月支出預算上限）、`budget_alert_50_sent_month`／`budget_alert_80_sent_month`（FR-43 門檻預警去重用） | Step 2.1 記帳模組 FR-41／FR-43，設計理由見下方 `transactions` 表 | `0018_add_budget_fields_to_users.sql` |
| 2026-08-04 | 新增 `finance_reminder_sent_date`（FR-42a 每日記帳提醒去重用） | Robin 提出「有設定預算時應每天固定時間提醒記帳」的回饋，設計比照 `todos.daily_pushed_on`，詳見下方 `budget_overrides` 表 | `0021_add_finance_reminder_field_to_users.sql` |
| 2026-08-04 | 新增 `finance_monthly_report_sent_month`（FR-44a 月底記帳月報推播去重用） | Robin 要求「記帳摘要請在每月底自動推一次月報」，設計比照 `budget_alert_50_sent_month`／`budget_alert_80_sent_month` | `0022_add_finance_monthly_report_field_to_users.sql` |
| 2026-08-04 | 新增 `height_cm`（身高，初始設定、變動才修正） | Step 2.2 體態管理模組 FR-46，設計理由見下方 `body_weight_logs` 表 | `0023_add_height_to_users.sql` |
| 2026-08-04 | 新增 `birthday`（生日，只比對月/日） | Step 2.3 重要通知模組 FR-53，設計理由見下方 `important_notifications_log` 表 | `0028_add_birthday_to_users.sql`；已知 5 位家人（弟弟／大妹／小妹／爸爸／媽媽）生日資料見 `0030_seed_family_birthdays.sql` |
| 2026-08-07 | 新增 `toeic_weekly_question_count`（軌道二每週生成題數，預設 21）／`toeic_pipeline_last_run_on`（週排程去重） | Step 3.2 TOEIC 雙軌題庫 Pipeline FR-25e／FR-25f，設計理由見下方 `toeic_questions`／`toeic_vocab_questions` 表 | `0037_add_toeic_weekly_question_count_to_users.sql` |
| 2026-08-08 | 新增 `waist_cm`（腰圍，初始設定、變動才修正，設計比照 `height_cm`） | 體態管理模組擴充 FR-46：Robin 要求新增腰圍設定，明確定位為「參考指標、非必要」，BMI 計算不使用此欄位；合理範圍 40~200 公分（比身高體重寬鬆，因為只是參考用途，不用像身高體重那麼嚴格） | `0046_add_waist_to_users.sql` |
| 2026-08-08 | 新增 `certificate_answer_reminder_sent_on`（FR-28 20:00 作答提醒去重用） | Step 3.3 作答與批改流程，設計比照 `finance_reminder_sent_date`／`toeic_pipeline_last_run_on` 等既有「當日去重」欄位慣例，避免 `/healthz` 同一小時內多次觸發重複推播 | `0048_add_certificate_answer_reminder_field_to_users.sql` |
| 2026-08-08 | 新增 `youtube_last_run_on`（FR-59a 週推播去重用） | Step 3.4 YouTube 技術情報模組，設計比照 `toeic_pipeline_last_run_on`，避免週四當天 `/healthz` 多次觸發重複推播 | `0051_add_youtube_last_run_on_to_users.sql` |
| 2026-08-09 | 新增 `job_resume`／`job_expectation`（履歷/期望工作敘述）、`years_of_experience`／`expected_salary_min`／`expected_salary_max`（結構化年資/期望薪資）、`job_search_last_run_on`（週排程去重用） | Step 4.1 求職模組 FR-33／FR-34b／FR-36，見 SPEC.md ADR-24，詳見下方 `job_search_criteria`／`job_companies`／`job_postings` 表 | `0053_add_job_search_fields_to_users.sql` |

---

### invite_codes

**建立日期**：2026-07-30
**用途**：Robin 為每位家人設定的一次性通關密碼。對應 FR-6～FR-6d。
**Migration 檔案**：`src/migrations/0002_create_invite_codes_table.sql`

```sql
CREATE TABLE invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    user_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE invite_codes IS '通關密碼表：Robin 為每位家人設定的一次性通關密碼，設定當下就會連同 users 那筆待綁定的記錄一起建立';
COMMENT ON COLUMN invite_codes.id IS '內部主鍵';
COMMENT ON COLUMN invite_codes.code IS '通關密碼本身，僅能使用一次';
COMMENT ON COLUMN invite_codes.is_used IS '是否已被使用（綁定）過';
COMMENT ON COLUMN invite_codes.user_id IS '這組密碼對應的使用者，對應 users.id（稱謂記錄在 users.role，這裡不重複存）';
COMMENT ON COLUMN invite_codes.created_at IS 'Robin 設定這組密碼的時間';
COMMENT ON COLUMN invite_codes.updated_at IS '最後變更時間（例如密碼被使用綁定成功的當下）';
```

**設計理由**：
- 不重複存 `role`：稱謂已經記錄在對應的 `users.role`，透過 `user_id` 就能查到，不需要在這張表重複一份
- `user_id` 設 `NOT NULL`：因為 Robin 設定密碼當下就會先建立 `users` 那筆記錄並在此處引用，不是等綁定後才補
- `code` 設 `UNIQUE` 避免重複；`is_used` + `updated_at` 一起記錄「是否用過、何時變更」，符合一次性使用規則

---

### knowledge_base

**建立日期**：2026-07-30
**用途**：知識庫，對應 FR-9 前三類（人格背景／家人背景故事／使用者自建知識庫）。
**Migration 檔案**：`src/migrations/0003_create_knowledge_base_table.sql`

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

COMMENT ON TABLE knowledge_base IS '知識庫表：對應 FR-9 前三類（人格背景／家人背景故事／使用者自建知識庫）';
COMMENT ON COLUMN knowledge_base.id IS '內部主鍵';
COMMENT ON COLUMN knowledge_base.category IS '知識庫類別：general_persona=Robinson人格背景, general_family=Robin與家人的共同背景故事, custom=特定使用者自建的客製知識庫';
COMMENT ON COLUMN knowledge_base.user_id IS '所屬使用者；general_persona/general_family 為全體共用固定 NULL，custom 才會指向對應 users.id';
COMMENT ON COLUMN knowledge_base.content IS '知識庫內容文字';
COMMENT ON COLUMN knowledge_base.created_at IS '建立時間';
COMMENT ON COLUMN knowledge_base.updated_at IS '最後更新時間';
```

**設計理由**：
- `category` 用 `CHECK` 限制在三種值，FR-9 第④類「對話紀錄」另外用 `conversation_logs` 存，不塞進這裡
- `user_id` 允許 `NULL`：兩種通用類別不屬於特定人，設 `NULL` 代表全體共用；`custom` 類別才會填入對應使用者 id，查詢時依此做 FR-10 的資安隔離
- Robin 的客製知識庫依 FR-9 說明「涵蓋管理者與使用者身份，不拆分」，即 `user_id` 指向 Robin 那筆記錄的 `custom` 資料，不特別拆欄位

**種子資料**：`general_persona`（Robinson 人格背景）與 `general_family`（Robin 與家人背景故事）兩筆初始資料，由 Robin 於 2026-07-30 提供內容，透過 `src/migrations/0006_seed_persona_and_family_knowledge.sql` 寫入，逐字採用未經改寫。

**2026-07-31 資料修正**：Robin 回報問「小布丁的生日年」時 Robinson 答錯（回 2013 年，正確為 2024 年）。追查發現 `general_family` 內容中，馬筱雯／馬筱媛家庭段落的幾筆日期（訂婚/結婚/子女出生）只寫了民國年（如「113/12/11」），沒有像其他家人一樣附上「(西元年)」對照，LLM 沒有可靠的曆法換算能力才會憑印象亂算。透過 `src/migrations/0009_fix_family_knowledge_roc_year_conversion.sql` 用 `UPDATE` 補上西元年對照（113→2024、114→2025、115→2026），其餘內容不變。

**2026-07-31 新增家庭成員**：Robin 提供資料，新增第 7 筆家庭成員「阿姨（母親范麗芳的親妹妹）：范焞琪」——生日民國 72 年 (1983) 2 月 9 日、居住南投縣水里鄉、喜歡貓咪、兼職兩份（早上全聯、晚上 7-11 六合門市），透過 `src/migrations/0010_add_aunt_fan_tunqi_to_family_knowledge.sql` 用 `UPDATE` 附加到 `general_family` 內容末尾，格式沿用既有慣例（民國年附西元年對照）。

**2026-08-01 新增家庭寵物**：Robin 提供資料，新增第 8、9 筆內容「阿牛（暱稱牛牛）：Robin 家養超過 7 年的黑底狗，胸腹部大片白毛帶黑色斑點似乳牛紋路，尾巴全白也帶黑色斑點」與「龜龜：Robin 爸爸養的蘇卡達陸龜」，透過 `src/migrations/0011_add_family_pets_to_family_knowledge.sql` 用 `UPDATE` 附加到 `general_family` 內容末尾。

**變更紀錄**（如果有）：
| 日期 | 變更內容 | 原因 | Migration 檔案 |
| --- | --- | --- | --- |
| 2026-08-01 | 新增 `label TEXT` 欄位（允許 NULL） | chat-core SPEC.md FR-11／ADR-8：主動新增知識功能需要一個分類/標籤欄位（例如「SOP」「食譜」「行程」），方便之後依主題查找，也供 FR-12 `/clean-target-dialog` 判斷刪除範圍時參考；既有資料與大部分 `general_persona`／`general_family` 內容不使用此欄位，不回填、允許 NULL | `src/migrations/0012_add_label_to_knowledge_base.sql` |

---

### conversation_logs

**建立日期**：2026-07-30
**用途**：個人化完整對話歷史，對應 FR-9 第④類。
**Migration 檔案**：`src/migrations/0004_create_conversation_logs_table.sql`

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

COMMENT ON TABLE conversation_logs IS '對話紀錄表：對應 FR-9 第④類，個人化的完整對話歷史';
COMMENT ON COLUMN conversation_logs.id IS '內部主鍵';
COMMENT ON COLUMN conversation_logs.user_id IS '這則訊息屬於哪位使用者，對應 users.id';
COMMENT ON COLUMN conversation_logs.role IS '訊息角色：user=使用者傳送, assistant=Robinson回覆';
COMMENT ON COLUMN conversation_logs.content IS '訊息內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN conversation_logs.created_at IS '訊息發生時間';
COMMENT ON COLUMN conversation_logs.deleted_at IS '軟刪除時間戳記；FR-13 觸發個資清除機制時，將該筆設為此欄位而非真的砍掉資料列，查詢時需排除 deleted_at IS NOT NULL 的記錄';
```

**設計理由**：
- `content` 存的內容前提是已經過 FR-13d 的個資遮蔽處理，不額外存「原始未遮蔽版本」，降低外洩風險
- `deleted_at` 採軟刪除：FR-13 觸發個資清除機制時只標記這個時間戳記，不真的刪除資料列，保留稽核軌跡；所有查詢邏輯都要記得加上 `WHERE deleted_at IS NULL`
- 複合索引 `(user_id, created_at)` 對應最常見查詢「查某人最近的對話」

---

### feature_toggles

**建立日期**：2026-07-30
**用途**：每位使用者各功能模組獨立開關，對應 FR-2。
**Migration 檔案**：`src/migrations/0005_create_feature_toggles_table.sql`（建表）、`src/migrations/0034_split_skill_growth_toggle.sql`（2026-08-07，`skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關）

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

COMMENT ON TABLE feature_toggles IS '功能開關表：對應 FR-2，每位使用者各模組獨立開關';
COMMENT ON COLUMN feature_toggles.id IS '內部主鍵';
COMMENT ON COLUMN feature_toggles.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN feature_toggles.feature_key IS '功能代號：todo=待辦, job_search=求職, budget=記帳, body=體態管理, tech_intel=技術情報（新聞/電子報/YouTube）, certificate=證照準備（TOEIC等）, language=語言學習, mood_journal=心情小記, friend_mode=好友模式, important_notify=重要通知';
COMMENT ON COLUMN feature_toggles.is_enabled IS '是否開啟此功能';
COMMENT ON COLUMN feature_toggles.updated_at IS '最後變更時間';
```

**設計理由**：
- `feature_key` 用 `CHECK` 鎖定 FR-2 列出的 10 個模組英文代號，避免打錯字造成查詢對不上
- `UNIQUE (user_id, feature_key)` 確保每人每個功能只有一筆設定
- 新使用者綁定成功時，由程式邏輯一次幫他把 10 個 `feature_key` 都插入預設值（`is_enabled = TRUE`），不是 schema 本身的責任
- **2026-08-07 拆分**：原本規劃的單一 `skill_growth`（涵蓋每日技術分享、TOEIC、YouTube）拆成三個獨立開關——Robin 認為證照準備（`certificate`，TOEIC 等）跟技術情報訂閱（`tech_intel`，新聞/電子報/YouTube）性質不同，語言學習（`language`，英文口說、其他語言，尚未開發）也該獨立於證照準備之外，三者應能各自開關，不該綁在一起。既有的 `skill_growth` 資料列由 `0034` migration 搬移為 `tech_intel`（保留原本的開關狀態），`certificate`／`language` 則等對應功能實際開工、使用者第一次觸發「我的功能設定」時，由既有的 `ensure_default_toggles()` 自動補上預設值

---

### conversation_summaries

**建立日期**：2026-07-31
**用途**：長記憶滾動摘要，對應 [chat-core SPEC.md](../../docs/specs/chat-core/SPEC.md) ADR-3。
**Migration 檔案**：`src/migrations/0007_create_conversation_summaries_table.sql`

```sql
CREATE TABLE conversation_summaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    summary TEXT NOT NULL DEFAULT '',
    summarized_up_to_log_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE conversation_summaries IS '長記憶滾動摘要表：每位使用者一筆，對應 chat-core SPEC.md ADR-3';
COMMENT ON COLUMN conversation_summaries.id IS '內部主鍵';
COMMENT ON COLUMN conversation_summaries.user_id IS '所屬使用者，對應 users.id，一人僅一筆（UNIQUE）';
COMMENT ON COLUMN conversation_summaries.summary IS '目前的滾動式摘要內容，新對話會定期融合進來，不是逐字對話紀錄';
COMMENT ON COLUMN conversation_summaries.summarized_up_to_log_id IS '摘要已涵蓋到哪一則 conversation_logs.id，避免同一段對話被重複摘要';
COMMENT ON COLUMN conversation_summaries.updated_at IS '最後一次摘要更新時間';
```

**設計理由**：
- 每人一筆（`UNIQUE user_id`），用 `UPDATE` 覆蓋既有摘要，不累積多筆歷史版本，維持表格輕量（對應 NFR-3 容量考量）
- `summarized_up_to_log_id` 是進度記號：只有「比短記憶（最近 10 則）更早、且 id 大於這個記號」的對話才算尚未摘要的 backlog；backlog 累積到 10 則以上才觸發一次摘要更新，避免每則訊息都多打一次 API
- 摘要呼叫使用 `GEMINI_API_TEXT_KEY`（長文生成類用途，見 ADR-12），不是一般問答用的 `GEMINI_API_BOT_KEY`

---

### media_uploads

**建立日期**：2026-07-31
**用途**：圖片/語音上傳的 Google Drive 網址記錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) ADR-13。
**Migration 檔案**：`src/migrations/0008_create_media_uploads_table.sql`

```sql
CREATE TABLE media_uploads (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'audio')),
    gdrive_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_media_uploads_user_id ON media_uploads (user_id);

COMMENT ON TABLE media_uploads IS '使用者上傳的圖片/語音檔案 Google Drive 網址記錄，對應 ADR-13';
COMMENT ON COLUMN media_uploads.id IS '內部主鍵';
COMMENT ON COLUMN media_uploads.user_id IS '上傳者，對應 users.id';
COMMENT ON COLUMN media_uploads.media_type IS '檔案類型：image（圖片）或 audio（語音），Step 1.4 語音功能上線後會共用這張表';
COMMENT ON COLUMN media_uploads.gdrive_url IS '原始檔案的 Google Drive 網址（圖片壓縮只在辨識前即時處理，不另外存壓縮版）';
COMMENT ON COLUMN media_uploads.created_at IS '上傳時間';
```

**設計理由**：
- `media_type` 用 `CHECK` 限制 `image`／`audio` 兩種，Step 1.3b（影像）先用到 `image`，Step 1.4（語音）上線後共用同一張表寫入 `audio`，不必屆時另外提案建表
- 只存 `gdrive_url`（原始檔）：Robin 2026-07-31 確認壓縮版圖片只在餵給 Gemini 前於記憶體內即時處理，不落地存回 Google Drive，因此表裡不需要壓縮版欄位（原提案的 `compressed_gdrive_url` 已移除，`original_gdrive_url` 更名為 `gdrive_url`）
- `user_id` 索引對應最常見查詢「查某人上傳過的檔案」

**2026-08-01 補充（Step 1.4）**：`media_type='audio'` 正式開始寫入（語音辨識，見 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-14／FR-15）；`created_at` 除了記錄上傳時間，也是 FR-15「15 分鐘修正窗口」判斷的依據——查該使用者最近一筆 `audio` 記錄的 `created_at`，未滿 15 分鐘則拒絕新的語音訊息，見 `src/bot/voice.py` 的 `is_within_correction_window()`；沒有新增欄位，沿用既有 schema。

---

### todos

**建立日期**：2026-08-02
**用途**：待辦事項，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-31／FR-31a／FR-31b／FR-32（Step 1.7；FR-31b 為 2026-08-02 追加的區間待辦支援）。
**Migration 檔案**：`src/migrations/0013_create_todos_table.sql`（建表）、`src/migrations/0016_add_start_at_to_todos.sql`（新增 `start_at`，FR-31b）

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

COMMENT ON TABLE todos IS '待辦事項表：對應 FR-31／FR-31a／FR-31b／FR-32，使用者以自然語言描述的待辦事項';
COMMENT ON COLUMN todos.id IS '內部主鍵';
COMMENT ON COLUMN todos.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN todos.content IS '待辦事項內容摘要（由 LLM 從使用者自然語言描述中萃取）';
COMMENT ON COLUMN todos.due_at IS '預定執行時間，由 LLM 依對話內容與伺服器當下日期換算成絕對時間；FR-31b 的區間待辦時代表區間的結束/截止時間';
COMMENT ON COLUMN todos.remind_before_30min IS '使用者記錄當下是否選擇要在預定時間前 30 分鐘收到提醒（FR-32）';
COMMENT ON COLUMN todos.status IS '狀態：pending=待處理, completed=使用者確認已完成, cancelled=使用者確認取消, expired=已超過預定時間仍未處理而自動標記（FR-31a）';
COMMENT ON COLUMN todos.reminded_30min_sent_at IS '「預定時間前 30 分鐘提醒」實際送出的時間戳記；非 NULL 代表已經推播過，避免同一則提醒被重複推播多次';
COMMENT ON COLUMN todos.daily_pushed_on IS '「每日 08:00 固定推播」最後一次把這筆待辦包含在推播內容裡的日期；避免同一天內因排程重複觸發而被重複推播';
COMMENT ON COLUMN todos.created_at IS '這筆待辦事項建立的時間';
COMMENT ON COLUMN todos.start_at IS '區間待辦事項的起始時間（FR-31b）；NULL 代表這是單一時間點待辦（沿用原本 due_at 語意），非 NULL 時 due_at 代表區間的結束/截止時間';
```

**設計理由**：
- `status` 用 `CHECK` 限制在四種狀態；`expired` 由 `/healthz` 排程檢查時自動標記（見 `src/bot/todo.py` 的 `mark_overdue_as_expired()`），不需要使用者手動操作
- `reminded_30min_sent_at`／`daily_pushed_on` 兩個欄位都是「去重記號」：整個推播機制沒有獨立的排程系統，是借用 `/healthz` 既有的 10 分鐘 cron 頻率（比照 Step 1.6 `NeonCapacityMonitor` 的做法），若不記錄「這則提醒是否已經送過」，同一筆待辦在期限前 30 分鐘的視窗內會被重複推播多次；選擇存在 DB（而非記憶體狀態）是因為 Render 免費方案可能不定期重啟，記憶體狀態重啟就會遺失，但待辦提醒的正確性比 Step 1.6 的容量告警更重要，值得多花一個欄位換取跨重啟的持久性
- 兩個索引分別對應「查某人目前待處理清單」（`user_id, status`）與「掃描所有使用者裡快到期/逾期的待辦」（`due_at`，推播與逾期標記都會用到）
- FR-31 提到的跨模組歧義判斷（例如「打籃球」要反問記到體態管理還是待辦事項）Phase 1 暫不實作，目前沒有其他已完成的模組可以比較（體態管理是 Phase 2、心情小記 Step 1.8 也還沒做），待那些模組做出來後再回頭補上，schema 本身不受影響
- **`start_at`（2026-08-02，FR-31b）**：Robin 詢問「待辦事項是不是只能存單一時間點，不能存像『8/2 08:00～8/5 17:00』這種區間」後新增。選擇用「額外的可選欄位」而不是把 `due_at` 整個改成必填的 `start_at`/`end_at` 兩欄，是為了讓既有單一時間點待辦的 schema 與程式邏輯完全不受影響（`start_at` 是 NULL）、只有真的描述成區間時才會兩個欄位都有值，屬於最小改動；相應地，「前 30 分鐘提醒」的判斷基準改用 `COALESCE(start_at, due_at)`（區間以開始時間為準、單一時間點仍以到期時間為準），「每日 08:00 摘要」改為同時檢查 `due_at`／`start_at` 落在今天的情況，且去重條件從「`daily_pushed_on IS NULL`（曾經推播過就不再推播）」放寬為「`daily_pushed_on IS NULL OR daily_pushed_on != 今天`（只看今天有沒有推播過）」，讓區間待辦可以在開始日、結束日分別各推播一次；沒有另外加索引（`idx_todos_due_at` 沿用即可），因為這是個人使用的生活小助手，`todos` 資料量不會大到需要額外複合索引

---

### mood_journals

**建立日期**：2026-08-02
**用途**：心情小記，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-49／FR-50（Step 1.8）。
**Migration 檔案**：`src/migrations/0014_create_mood_journals_table.sql`

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

COMMENT ON TABLE mood_journals IS '心情小記表：對應 FR-49／FR-50，使用者每日心情紀錄與隨筆';
COMMENT ON COLUMN mood_journals.id IS '內部主鍵';
COMMENT ON COLUMN mood_journals.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN mood_journals.mood_category IS '心情分類（FR-56h 情境範例六選一）：angry_anxious=生氣/焦慮, sad_down=難過/低落, tired_burned_out=疲倦/厭世, neutral=普通/平淡, calm_relaxed=平靜/放鬆, happy_excited=高興/興奮';
COMMENT ON COLUMN mood_journals.content IS '完整日記內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN mood_journals.achievement_note IS 'FR-50 個人成就三選一提示的回答（今天完成了什麼一句話總結／挑一件有感覺的事／寫下啟發或下次想改變的地方，僅需一項）；使用者選擇跳過時為 NULL，同樣已經過 FR-13 個資遮蔽處理';
COMMENT ON COLUMN mood_journals.created_at IS '這筆心情小記建立的時間';
COMMENT ON COLUMN mood_journals.entry_date IS '這筆心情小記實際對應的日期（可補記過去日期）；既有舊資料此欄位為 NULL，讀取時 fallback 使用 created_at 的日期部分；一律由 app 端依台灣時區算好日期後寫入，不依賴資料庫預設值';
```

**Migration 檔案（entry_date）**：`src/migrations/0017_add_entry_date_to_mood_journals.sql`

**設計理由**：
- `mood_category` 用 `CHECK` 鎖定 FR-56h 情境範例列出的固定 6 種分類，避免自由輸入造成資料不一致
- `achievement_note` 允許 `NULL`：FR-50 明確是「使用者自行選擇是否回答」，跳過是合法情況
- `content`／`achievement_note` 都套用 FR-13 個資遮蔽（跟一般聊天、圖片說明文字、語音轉文字三個既有入口一致），2026-08-02 與 Robin 確認新入口也要套用同一套防線
- 只建 `user_id` 單欄索引：目前唯一常見查詢是「查某人的心情小記」，沒有像 `todos` 那種需要跨使用者掃描的排程查詢，不需要額外複合索引
- **`entry_date`（2026-08-02，FR-49 補記/更新/刪除擴充）**：Robin 提出「記帳、心情小記、體重、飲食、運動習慣都要有補記、更新、刪除、新增的功能」，心情小記優先實作。設計比照 `todos.start_at`（FR-31b）：新增可選欄位而不動既有必填欄位，既有資料/程式邏輯不受影響（此欄位為 NULL 即可）；一律由 app 端用台灣時區算好日期後寫入，不依賴資料庫 `DEFAULT`（理由同 `todos.start_at`：資料庫伺服器時區可能是 UTC，靠 DB 端算日期在台灣午夜前後容易出現差一天的 bug）。讀取時（`mood._entry_date_of()`）對舊資料 fallback 使用 `created_at` 換算成台灣時區後的日期部分，語意上等同「當時新增的那天就是實際發生的那天」

---

### complaints

**建立日期**：2026-08-02
**用途**：客訴/意見回饋收集，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-60～FR-63（Step 1.9）。
**Migration 檔案**：`src/migrations/0015_create_complaints_table.sql`

```sql
CREATE TABLE complaints (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_complaints_user_id ON complaints (user_id);

COMMENT ON TABLE complaints IS '客訴/意見回饋收集表：對應 FR-60～FR-63';
COMMENT ON COLUMN complaints.id IS '內部主鍵';
COMMENT ON COLUMN complaints.user_id IS '提出客訴的使用者，對應 users.id';
COMMENT ON COLUMN complaints.content IS '客訴原始內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN complaints.created_at IS '這筆客訴建立的時間';
```

**設計理由**：
- `content` 套用 FR-13 個資遮蔽（跟一般聊天／圖片說明文字／語音轉文字／心情小記四個既有入口一致，2026-08-02 與 Robin 確認：FR-62 的隱私例外只是允許 Robin 看到客訴內容，不代表個資保護防線可以跳過，兩者是不同層面的隱私考量）
- FR-62 的 Gemini 分析結果只透過私訊即時送給 Robin，刻意不落地存進這張表——分析報告是輔助判讀用途，Robin 看過即可，不需要永久保留一份重複於私訊內容的資料
- 只建 `user_id` 單欄索引，用途與 `mood_journals` 相同（查某人的客訴紀錄），不需要額外複合索引

---

### transactions

**建立日期**：2026-08-04
**用途**：記帳交易紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-42（Step 2.1）。
**Migration 檔案**：`src/migrations/0019_create_transactions_table.sql`

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

COMMENT ON TABLE transactions IS '記帳交易表：對應 FR-42，使用者的支出/收入紀錄，支援補記/更新/刪除';
COMMENT ON COLUMN transactions.id IS '內部主鍵';
COMMENT ON COLUMN transactions.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN transactions.type IS '交易類型：expense=支出, income=收入';
COMMENT ON COLUMN transactions.category IS '交易分類（固定清單）：餐飲/交通/購物/居住/娛樂/醫療三類屬於支出常見分類，薪資/獎金屬於收入常見分類，其他兩種皆可用；分類與 type 的合理搭配由應用層驗證，不由資料庫層限制';
COMMENT ON COLUMN transactions.amount IS '交易金額，一律為正數，方向由 type 決定';
COMMENT ON COLUMN transactions.note IS '備註，可能含個資，已經過 FR-13 個資遮蔽處理，選填';
COMMENT ON COLUMN transactions.transaction_date IS '這筆交易實際發生的日期（可補記過去日期）；一律由 app 端依台灣時區算好日期後寫入，不依賴資料庫預設值，設計比照 mood_journals.entry_date';
COMMENT ON COLUMN transactions.created_at IS '這筆交易記錄建立的時間';
```

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：FR-41「理財目標」解讀為「每月支出預算上限」（單一數字），不是「每月儲蓄目標」，所以不需要算「收入-支出」結餘去比對目標；但交易紀錄本身仍然「支出」「收入」兩種都做，保留未來需要結餘概念時的彈性，`monthly_budget` 因此存在 `users` 表而不是這張表（見上方 `users`「變更紀錄」）
- `type`／`category` 都用 `CHECK` 鎖定固定清單，設計比照 `mood_journals.mood_category`；分類清單全部是中文，不像 `mood_journals` 需要英文代碼＋中文標籤兩層
- `amount` 用 `NUMERIC(12,2)` 存實際金額（非整數分），並用 `CHECK (amount > 0)` 強制正數，方向完全由 `type` 決定，避免正負號與 type 語意互相矛盾的資料
- `transaction_date` 必填且一律由 app 端依台灣時區算好日期後寫入，不依賴資料庫預設值，設計理由與 `mood_journals.entry_date` 完全相同（支援補記過去日期、避免 DB 伺服器時區在台灣午夜前後產生差一天的 bug）
- 只建 `user_id` 單欄索引，用途與 `mood_journals`／`complaints` 相同（查某人的記帳紀錄／月加總），不需要額外複合索引——月加總查詢（`user_id`／`type`／`transaction_date` 範圍）目前資料量小，個人使用不需要為此額外建複合索引

---

### budget_overrides

**建立日期**：2026-08-04
**用途**：預算特殊月份覆蓋，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-41a。Robin 提出「某幾個月固定開銷較高（報稅、包紅包），想單獨設定跟平常不同的預算」的回饋後新增。
**Migration 檔案**：`src/migrations/0020_create_budget_overrides_table.sql`

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

COMMENT ON TABLE budget_overrides IS 'FR-41a 預算特殊月份覆蓋：使用者可對某幾個月設定跟全局預設（users.monthly_budget）不同的支出預算上限，查詢當月生效預算時優先用這裡的值，沒有才 fallback 用全局預設';
COMMENT ON COLUMN budget_overrides.id IS '內部主鍵';
COMMENT ON COLUMN budget_overrides.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN budget_overrides.year IS '這筆覆蓋值套用的年份';
COMMENT ON COLUMN budget_overrides.month IS '這筆覆蓋值套用的月份（1~12）';
COMMENT ON COLUMN budget_overrides.amount IS '這個月的特殊預算上限金額，一律為正數';
COMMENT ON COLUMN budget_overrides.created_at IS '這筆覆蓋值建立的時間';
```

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：預算跟月份的關聯採「全局預設值＋特殊月份覆蓋」設計，而非「每個月都各自存一筆」——`users.monthly_budget` 保留當全局預設，這張表只存「跟預設值不同」的特殊月份，好處是改全局預設不會動到已經設定過的特殊月份、資料量小、查詢邏輯只多一層 fallback（`finance.get_effective_monthly_budget()`）
- `UNIQUE (user_id, year, month)` 確保同一個使用者同一年同一月只會有一筆覆蓋值，寫入邏輯是「已存在就 UPDATE，不存在就 INSERT」（`finance.set_budget_override()`），不是資料庫層 `ON CONFLICT`
- `year`／`month` 分開存而不是存一個 `DATE`，因為這裡的語意是「套用範圍」而非「某一天」，`month` 額外加 `CHECK (month BETWEEN 1 AND 12)` 防呆
- 沒有另外建索引：查詢一律帶 `user_id`／`year`／`month`（有 `UNIQUE` 約束自帶索引）或只帶 `year`／`month`（FR-43 門檻預警、FR-42a 每日提醒找出「這個月有覆蓋值」的使用者），資料量小，個人使用不需要額外複合索引

---

### body_weight_logs

**建立日期**：2026-08-04
**用途**：體重紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-46（Step 2.2）。
**Migration 檔案**：`src/migrations/0024_create_body_weight_logs_table.sql`

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

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：身高「初始設定、變動才修正」放在 `users.height_cm`（見 `users` 表變更紀錄），體重「有量才記」則需要獨立的多筆歷史紀錄表
- `weight_kg` 用 `CHECK (weight_kg >= 40)` 做 FR-46 合理範圍檢查的最後一道防線，App 層（`body.is_weight_reasonable()`）會先擋一次並反問使用者確認，不直接讓明顯異常的數字寫入
- `entry_date` 設計比照 `mood_journals.entry_date`／`transactions.transaction_date`：一律由 app 端依台灣時區算好日期後寫入，支援補記過去日期
- 只建 `user_id` 單欄索引，用途同其餘個人紀錄表（查某人的體重紀錄／算 BMI 趨勢），資料量小不需要額外複合索引

---

### exercise_logs

**建立日期**：2026-08-04
**用途**：運動紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-47（Step 2.2）。
**Migration 檔案**：`src/migrations/0025_create_exercise_logs_table.sql`

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

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：消耗卡路里改用 LLM 估算（而非 MET 公式），沿用 `GEMINI_API_BOT_KEY`（見 `src/bot/body.py` `estimate_exercise_calories()`），符合 FR-56g 情境3「自然口吻回覆＋估算免責聲明」的示範；估算失敗時 `estimated_calories` 允許 `NULL`，不擋下整筆紀錄
- `activity` 用自由文字而非固定分類清單，因為運動項目種類差異太大，不像記帳/心情小記能窮舉
- `heart_rate` 選填，對應 FR-56g 情境3「有沒有心率紀錄」的示範

---

### diet_logs

**建立日期**：2026-08-04
**用途**：飲食與飲水紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-48（Step 2.2）。
**Migration 檔案**：`src/migrations/0026_create_diet_logs_table.sql`

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

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：飲食與飲水用同一張表、`entry_type` 區分（比照 `transactions.type` 的做法），而非兩張獨立表，因為兩者共用大部分欄位結構（使用者/日期/描述），只有飲食才需要營養拆算欄位
- 三大營養素與熱量拆算沿用 `GEMINI_API_BOT_KEY`（見 `src/bot/body.py` `estimate_diet_macros()`），因為沒有食物資料庫，本來就只能靠 LLM 語意判斷；估算失敗時各欄位允許 `NULL`，不擋下整筆紀錄；回覆務必附上 FR-17c 估算誤差聲明
- `water_ml` 只有 `entry_type=water` 才有值，`estimated_calories`／`protein_g`／`carbs_g`／`fat_g` 只有 `entry_type=food` 才有值，兩者互斥但都設計成可為 `NULL` 的欄位，不拆成兩張表換取查詢/程式碼簡潔

---

### body_goals

**建立日期**：2026-08-04
**用途**：體態目標（身高體重/運動/飲食三個子功能共用一張），對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-46～FR-48、FR-45（Step 2.2）。
**Migration 檔案**：`src/migrations/0027_create_body_goals_table.sql`

```sql
CREATE TABLE body_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    goal_type TEXT NOT NULL CHECK (goal_type IN ('weight', 'exercise', 'diet')),
    target_description TEXT NOT NULL,
    target_value NUMERIC(6,2),
    baseline_value NUMERIC(6,2),
    target_date DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'achieved', 'cancelled')),
    achieved_notified BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_body_goals_user_id ON body_goals (user_id);
```

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：三個子功能的目標設定共用一張表、用 `goal_type` 區分（比照 `budget_overrides` 的精神），而非各自獨立建表；代價是 `target_value`／`baseline_value` 的語意隨 `goal_type` 而不同，由 App 層（`src/bot/body.py`）負責正確解讀
- `baseline_value` 只有 `goal_type=weight` 使用：設定目標當下記錄的體重，用來判斷這個目標是「要瘦」還是「要增」（`target_value` 跟 `baseline_value` 比大小），每次記體重時即時檢查是否達成（`check_weight_goal_achieved()`）
- `goal_type=exercise` 的 `target_value` 語意是「累積運動分鐘數」（Robin 指出用公里數對非跑步類運動不通用，分鐘數才是各種運動都適用的共同單位）；因為需要跨多筆 `exercise_logs` 加總才能判斷達成，改成借用 `/healthz` 頻率的排程檢查（`check_and_push_exercise_goal_achievements()`），不像體重目標能在單次記錄當下就地判斷
- `goal_type=diet` 目前不支援自動達成判斷（太主觀，例如「飲食完美控制」無法量化），`target_value` 固定為 `NULL`，只能由使用者手動標記完成/取消——這是已知的刻意簡化
- `deadline_reminder_sent`：期限前 7 天固定提醒一次（`check_and_push_goal_deadline_reminders()`），跟記帳月報不同，這裡不用「月份」去重，因為目標的期限提醒本來就只會觸發一次（不像月報是每月重複事件）

---

### important_notifications_log

**建立日期**：2026-08-04
**用途**：重要通知模組的年度推播去重紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-53（Step 2.3）。
**Migration 檔案**：`src/migrations/0029_create_important_notifications_log_table.sql`

```sql
CREATE TABLE important_notifications_log (
    id BIGSERIAL PRIMARY KEY,
    notification_key TEXT NOT NULL,
    year INT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (notification_key, year)
);
```

**設計理由**：
- 2026-08-04 經 AskUserQuestion 與 Robin 確認：農曆節日（除夕/初一/中秋/端午）改用 `lunarcalendar` 套件即時計算西曆日期（純 Python 計算、不需要網路），不維護每年日期對照表；父親節固定 8/8、母親節固定西曆 5 月第二個星期日，同樣不需要對照表
- 一張表通用所有「固定節日」與「生日」兩種通知類型，用 `notification_key` 區分：固定節日用英文代碼（`new_year`／`fathers_day`／`mothers_day`／`lunar_new_year_eve`／`lunar_new_year_day1`／`tomb_sweeping`／`mid_autumn`／`dragon_boat`），生日用 `birthday_<user_id>`（每位使用者各自獨立去重，不會因為某人生日推播過就擋住別人）
- `UNIQUE (notification_key, year)` 確保同一個通知類型同一年只會推播一次，即使 `/healthz` 每 10 分鐘觸發一次 cron 檢查、同一天內會被命中好幾次
- 不用 `month`／`day` 額外欄位記錄實際觸發日期，因為「哪一天觸發」本來就是即時計算出來的（農曆節日每年日期不同），只需要知道「這一年這個類型推播過了沒」即可決定要不要再推播一次
- 只用 `notification_key`＋`year` 做唯一約束就足夠當索引，資料量小（一年最多十幾筆），不需要額外複合索引

---

### skill_growth_digests

**建立日期**：2026-08-07（2026-08-09 經 Robin 生產環境回饋修正為一天多筆、一筆一個來源管道的正規化設計，見 ADR-25）
**用途**：個人技能成長模組的每日技術摘要收集與推播狀態，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-22、FR-23（Step 3.1）。
**Migration 檔案**：`src/migrations/0052_recreate_skill_growth_digests_per_source.sql`（`0033_add_skill_growth_pushed_on_to_users.sql` 建立的舊表直接 `DROP TABLE` 砍掉重建；經 Robin 確認舊表當時僅有 1 筆資料，重建成本可忽略，不需要額外寫資料搬遷邏輯）

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

COMMENT ON TABLE skill_growth_digests IS '個人技能成長模組：每日技術摘要的收集與推播狀態（FR-22、FR-23）。一天最多三筆，一筆對應一個來源管道（tldr／ithome／techcrunch）；固定台灣時間 23:00 各來源各自收集並產出精簡總結，隔天固定台灣時間 08:00 讀取「昨天」那幾筆資料組成三行式訊息推播給 Robin';
COMMENT ON COLUMN skill_growth_digests.digest_date IS '收集內容所屬的日期（23:00 收集當下的「今天」）';
COMMENT ON COLUMN skill_growth_digests.source IS '這筆摘要屬於哪個技術情報管道：tldr／ithome／techcrunch，未來新增管道只需要寫入新的 source 值，不需要改 schema；NULL 保留給「當天完全沒有任何一筆收集結果」時的去重標記列（見 pushed_on 說明）';
COMMENT ON COLUMN skill_growth_digests.summary_text IS '這個管道當天的精簡總結（100 字內，只給重點結論）；「今日無內容」代表該來源當天確實沒有抓到任何內容（已完成收集但真的沒東西），跟「完全沒有這個 source 的列」（收集當下服務不可用）是兩種不同情境';
COMMENT ON COLUMN skill_growth_digests.pushed_on IS '這筆摘要推播給 Robin 的日期（收集隔天的 08:00）；同一天收集到的幾筆一起標記，避免 08:00 那個小時內 /healthz 多次觸發重複推播；NULL 代表尚未推播';
COMMENT ON COLUMN skill_growth_digests.created_at IS '這筆收集結果建立的時間';
```

**設計理由**：
- 2026-08-07 經 Robin 回饋修正：原規劃在 `check_and_push_daily_digest()` 執行當下（08:00）才即時抓取「昨天」的信件/新聞；Robin 改要求分成兩個獨立排程時間點——固定 23:00 收集「當天」的信件/新聞、隔天 08:00 才推播，讓收集與推播解耦，這樣資料需要跨時間點持久化，原本規劃在 `users` 表加一個 `skill_growth_pushed_on` 去重欄位已不夠用，改成獨立一張表存收集結果本身
- 2026-08-09 經 Robin 生產環境回饋修正（見 ADR-25）：原本三個來源合併寫入單一 `summary_text`，Robin 完全無法分辨當天到底是哪個來源沒抓到內容、還是收集本身出了問題；推播訊息也塞了太多原文內容，Robin 只需要三行結論。曾提案改成 3 個獨立欄位（`tldr_summary`／`ithome_summary`／`techcrunch_summary`），被 Robin 否決——理由是新增來源就要再 `ALTER TABLE` 加欄位，擴充性差；改成新增 `source` 欄位＋`UNIQUE (digest_date, source)`，`summary_text` 保留但只存單一來源的精簡總結，未來新增來源只需要多寫一個 `source` 值
- `UNIQUE (digest_date, source)`：同一天同一來源只會有一筆收集結果，避免 23:00 那個小時內 `/healthz` 被觸發多次時重複收集/重複呼叫 Gemini；PostgreSQL 的 `UNIQUE` 約束不視 `NULL` 為相等，`source IS NULL` 的去重標記列因此不受此約束限制
- `summary_text` 存固定文字「今日無內容」而非 `NULL`：代表該來源當天確實收集完成、只是沒有內容，此時不呼叫 Gemini（省 Token）；跟「完全沒有這個 source 的列」（收集當下服務不可用，例如整個小時 23:00 都連不上）是兩種不同情境，後者才用 `source IS NULL` 表示，隔天推播時一律回覆 Robin 指定的固定訊息「未獲得最新技術分享」
- `pushed_on` 沿用 `todos.daily_pushed_on` 的慣例，記錄「這批（同一天最多三筆）是否已經推播過」，避免 08:00 那個小時內重複推播；跟 `digest_date` 分開兩個欄位是因為推播時間點（隔天）跟收集時間點（當天）本來就不同一天

---

### toeic_questions

**建立日期**：2026-08-07
**用途**：TOEIC 雙軌題庫軌道一，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-25a～FR-25c（Step 3.2）。
**Migration 檔案**：`src/migrations/0035_create_toeic_questions_table.sql`

```sql
CREATE TABLE toeic_questions (
    id BIGSERIAL PRIMARY KEY,
    test_id TEXT NOT NULL,
    question_type TEXT NOT NULL CHECK (question_type IN ('write', 'listen')),
    question_number INT NOT NULL,
    question_text TEXT NOT NULL,
    options JSONB NOT NULL,
    image_gdrive_url TEXT NOT NULL,
    audio_gdrive_url TEXT,
    source_image_filename TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_toeic_questions_test_id ON toeic_questions (test_id);
```

**設計理由**：
- 2026-08-07 經 AskUserQuestion 與 Robin 確認：Robin 手動把題目照片/音檔直接上傳到 Google Drive 指定資料夾（不透過 Telegram），機器人固定每週日 22:00 排程掃描比對，見 `src/bot/toeic.py`
- `source_image_filename UNIQUE`：取代原規劃「檔名日期是否在過去一週內」的去重方式（Robin 確認的實際檔名格式沒有日期，見 SPEC.md FR-25f 修正記錄），改用「這個檔名是否已經處理過」判斷，更直覺也不會漏檔
- 依 FR-25c 原文刻意不存正解欄位：題目照片本身未必附答案，避免存入不存在或錯誤的資料
- `options` 用 `JSONB` 存 Gemini Vision 解析出的選項陣列，欄位數不固定（可能 3～5 個選項）比起拆成 `option_a`/`option_b`... 固定欄位更貼合實際情況
- `audio_gdrive_url` 允許 `NULL`：`write`（填空/單字題）類型只有圖片，沒有對應音檔

**變更紀錄**：
- 2026-08-07（同日追記）：Robin 詢問「以後新增 GCP、AWS 等其他證照考試，現有機制能否直接沿用」，確認需求後泛用化本表，經 Robin 核准 `0038_generalize_toeic_questions_to_certificate_questions.sql`：
  - 表名由 `toeic_questions` 重新命名為 **`certificate_questions`**（`idx_toeic_questions_test_id` 索引同步改名為 `idx_certificate_questions_test_id`），本節上方的 CREATE TABLE／設計理由仍保留原文不改寫，只在此追記變更
  - 新增 `exam_type TEXT NOT NULL` 欄位（從檔名第一段解析，例如 `toeic`／`gcp`／`aws`），**刻意不加 CHECK 限制清單**——Robin 明確要求「exam_type 不能直接鎖死這三類，因為會有多種可能」，未來新增證照類型只需要換檔名前綴，不必改程式碼或再開 migration
  - 新增 `idx_certificate_questions_exam_type` 索引，供未來依證照類型篩題
  - 對應程式碼：`src/bot/toeic.py` 的 `parse_filename()`／`classify_drive_files()`／`_insert_question()` 皆已改用 `exam_type`；`sync_track1_from_drive()` 掃描 Drive 資料夾時也從「檔名含 toeic 關鍵字」改成「列出整個資料夾所有檔案」（Robin 確認選擇），避免用關鍵字過濾漏掉其他證照類型的檔案
- 2026-08-07（Step 3.3，見 SPEC.md ADR-19 決策 2）：「依 FR-25c 原文刻意不存正解」的決策部分推翻——Robin 改為把購買的測驗書正確解答/詳解一併拍照上傳（檔名 `{exam_type}_{test_id}_write/listen_{題號}_ans.png`），經 Robin 核准 `0039_add_answer_fields_to_certificate_questions.sql`：
  - 新增 `correct_answer TEXT`／`explanation TEXT`：來自 Vision 解析答案照片的結果，非 AI 推論；皆允許 `NULL`（尚未補拍答案照時）
  - 新增 `answer_source_filename TEXT UNIQUE`：對應的答案照片檔名，去重設計比照 `source_image_filename`
  - 缺 `correct_answer` 的題目不會出現在每日推播候選池（見 SPEC.md FR-26、ADR-19 決策 3）
  - 對應程式碼：`src/bot/toeic.py` 的 `parse_filename()` 新增 `is_answer_key` 判斷、`sync_track1_from_drive()` 掃描順序改為兩階段（先建題目、再處理 `_ans` 檔案比對補正解）

---

### toeic_vocab_questions

**建立日期**：2026-08-07
**用途**：TOEIC 雙軌題庫軌道二，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-25d～FR-25e（Step 3.2）。
**Migration 檔案**：`src/migrations/0036_create_toeic_vocab_questions_table.sql`

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

**設計理由**：
- 這張表的選項固定就是英翻中選擇題的 4 個選項，跟 `toeic_questions`（軌道一，選項數不固定、來源是圖片 OCR）語意不同，用固定的 `option_a`～`option_d` 四欄比 `JSONB` 更直覺、也方便直接用 `correct_option` 對答案
- `LOWER(target_word)` 唯一索引：避免同一個單字（含大小寫差異，例如 `Abundant` 跟 `abundant`）重複生成，週排程生成前會先查詢既有單字清單，在 Prompt 裡明確告知 Gemini 要避開
- 每週要生成幾題由 `users.toeic_weekly_question_count` 決定（Robin 自訂，預設 21 題＝一天 3 題 x 7 天），不寫死在這張表
- 2026-08-07 追記：軌道一（`certificate_questions`）已泛用化為任意證照類型，但這張表（軌道二，Gemini 生成單字題）刻意維持 TOEIC 專用，未跟著改名——單字題的生成邏輯（英文單字→中文選擇題）是 TOEIC 特有的語言學習玩法，跟 GCP／AWS 這類技術證照的「考古題」性質不同，沒有泛用化的必要

---

### answer_logs

**建立日期**：2026-08-07
**用途**：Step 3.3 作答紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-27、FR-29、ADR-19 決策 6。
**Migration 檔案**：`src/migrations/0040_create_answer_logs_table.sql`；`assignment_id` 欄位見 `0047_add_assignment_id_to_answer_logs.sql`（2026-08-08 追加）

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
CREATE INDEX idx_answer_logs_assignment_id ON answer_logs (assignment_id);  -- 0047 追加
```

**設計理由**：
- 2026-08-07 經 AskUserQuestion 與 Robin 確認：軌道一（`certificate_questions`）跟軌道二（`toeic_vocab_questions`）是兩張分開的題庫表，用兩個可為 NULL 的外鍵 + `CHECK` 限制只能填一個串連，取代「分兩張作答紀錄表、查詢時 UNION」的方案，讓 FR-29 統計一段時間成效可以用單一 SQL 查完
- `exam_type`／`question_type` 皆為寫入當下複製自對應題目的冗餘欄位，避免統計查詢時要多一層 JOIN 回題庫表才能篩選/分組；`question_type` 的值為 `write`／`listen`（軌道一）或 `vocab`（軌道二固定值），供 FR-29「最常出錯的地方」統計使用
- `answered_on` 用 `DATE` 而非 `TIMESTAMPTZ`：FR-29 需要用「日期」為單位判斷某天有沒有作答、計算平均時要排除未作答日，不需要到秒等級的時間精度
- **2026-08-08 追加 `assignment_id`**（見 `src/bot/certificate_answer.py`）：作答與批改流程（FR-27/FR-28）開工時發現，原本規劃的「靠比對同一題目在 `answer_logs` 有沒有對應紀錄」判斷「這個 assignment 是否已作答」在允許跨日晚補答（見 FR-28 決策）的情境下會不夠精準——同一題目可能因複習池機制被指派超過一次，光比對題目 id 無法區分是回答「今天這一批」還是更早的批次；直接記錄對應的 `assignment_id`，查詢就變成單純的存在性檢查，不需要猜測

---

### certificate_goals

**建立日期**：2026-08-07
**用途**：Step 3.3 證照準備目標設定，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-24、ADR-19。
**Migration 檔案**：`src/migrations/0041_create_certificate_goals_table.sql`

```sql
CREATE TABLE certificate_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    target_date DATE,
    target_score TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_type)
);
```

**設計理由**：
- `UNIQUE (user_id, exam_type)`：同一使用者對同一 `exam_type` 只保留一筆最新目標，重新設定即覆蓋（UPSERT），比照 `budget_overrides` 類似設計的「不逐次累加、只存目前生效值」概念
- `target_date`／`target_score` 皆允許 `NULL`：使用者可能只想設定分數目標、不確定確切考試日期，反之亦然
- `target_score` 用 `TEXT`：`exam_type` 開放任意字串，有些是量化分數（TOEIC 850）、有些是通過/未通過（GCP／AWS 這類技術證照沒有量化分數），比照 `exam_official_scores.score` 的設計

**變更紀錄**：
- 2026-08-08（Step 3.3 剩餘範圍，見 SPEC.md FR-24）：建表當下（0041 migration）尚未有對應程式碼，本次補上 `src/bot/certificate_goals.py`（`get_goal()`／`set_goal()`〔UPSERT，讀到既有值就 `UPDATE`、沒有就 `INSERT`〕／`list_goals()`／`format_goal_set_reply()`／`format_goals_summary()`／`build_advice_prompt()`）；`commands.py` 新增「設定證照目標」／`/set_certificate_goal`、「我的證照目標」／`/my_certificate_goals`、「給我讀書建議」／`/certificate_advice` 三組對話流程/單次查詢指令

---

### exam_official_scores

**建立日期**：2026-08-07
**用途**：Step 3.3 正式應考成績，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-30、ADR-19 決策 7。
**Migration 檔案**：`src/migrations/0042_create_exam_official_scores_table.sql`

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

**設計理由**：
- 跟 `answer_logs`（每日小考作答紀錄）刻意分開建表：正式成績是「一次考試的最終結果」，每日小考是「每天練習的逐題紀錄」，語意與查詢邏輯都不同，混在一起會互相干擾
- 不加 `UNIQUE` 限制：同一 `exam_type` 可能多次應考（例如多益考了兩次），每次都是獨立一筆
- `score` 用 `TEXT`：理由同 `certificate_goals.target_score`

**變更紀錄**：
- 2026-08-08（Step 3.3 剩餘範圍，見 SPEC.md FR-30）：建表當下（0042 migration）尚未有對應程式碼，本次補上 `src/bot/certificate_exam_scores.py`（`record_score()`／`list_scores()`／`distinct_exam_types()`／`format_scores_summary()`）；`commands.py` 新增「我要記錄正式成績」／`/log_exam_score`、「我的正式成績」／`/my_exam_scores`（經 AskUserQuestion 與 Robin 確認範圍：只做查詢列表，不含修改／刪除）

---

### certificate_daily_settings

**建立日期**：2026-08-08
**用途**：Step 3.3 每日出題設定，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-26、ADR-20。
**Migration 檔案**：`src/migrations/0043_create_certificate_daily_settings_table.sql`

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

**設計理由**：
- `UNIQUE (user_id, exam_type)`：同一使用者同一 exam_type 只保留一筆最新設定，重新設定即覆蓋（UPSERT），比照 `certificate_goals`
- `listen_ratio`／`write_ratio`／`vocab_ratio` 三欄只有 TOEIC 會填值，其他證照類型固定 `NULL`：非 TOEIC 證照沒有軌道二（單字題），只有單一題庫池可抽，沒有三軌比例可分配（見 ADR-20 決策 1）
- `review_ratio_new`／`review_ratio_review`（新題:複習題比例）刻意跟三軌比例分開兩組欄位：這是不同維度的設定，且所有 exam_type 通用，不像三軌比例只有 TOEIC 適用（見 ADR-20 決策 2）

---

### certificate_daily_schedule_overrides

**建立日期**：2026-08-08
**用途**：Step 3.3 彈性排程的日期區間覆蓋，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-26、ADR-20 決策 5。
**Migration 檔案**：`src/migrations/0044_create_certificate_daily_schedule_overrides_table.sql`

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

**設計理由**：
- 比照 `budget_overrides`「全局預設值＋特殊區間覆蓋」的既有模式：查詢當天生效題數時先查是否有覆蓋當天的區間，沒有才 fallback 用 `certificate_daily_settings` 的全局值
- `daily_question_count` 允許 `0`：「直接取消今天的」用單筆當天 `daily_question_count=0` 表示；「今天改到別天」則用兩筆覆蓋組合（今天設 0＋目標日期加開對應題數）
- 不加 `UNIQUE` 限制：同一使用者同一 exam_type 可能同時有多個不重疊的區間覆蓋（例如這週跟下個月各自調整過）

---

### certificate_daily_assignments

**建立日期**：2026-08-08
**用途**：Step 3.3 記錄每天實際推播的題目，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-27、FR-28、ADR-20。
**Migration 檔案**：`src/migrations/0045_create_certificate_daily_assignments_table.sql`

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

**設計理由**：
- 兩個可為 NULL 的外鍵＋ CHECK 串連軌道一/軌道二題庫，設計比照 `answer_logs`
- 是否已作答不在本表直接存狀態，靠查詢 `answer_logs.assignment_id` 有沒有指回這一筆判斷（2026-08-08 追加，見 `answer_logs` 表變更紀錄）——避免兩張表的「作答狀態」互相不同步，也不需要用題目 id／日期比對猜測
- `is_review` 只是記錄「這題是不是從複習池挑出來的」，供統計/除錯用，不影響作答批改邏輯本身（批改邏輯只在乎正解對不對）

---

### youtube_topics

**建立日期**：2026-08-08
**用途**：Step 3.4 YouTube 技術情報多組主題設定，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-57a、ADR-21。
**Migration 檔案**：`src/migrations/0049_create_youtube_topics_table.sql`

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

**設計理由**：
- `UNIQUE (user_id, topic)`：避免同一使用者重複新增一模一樣的主題文字
- `last_recommended_on` 允許 `NULL`：代表這個主題從未被選中推播過，供 FR-58c「優先選距離上次被推播最久的主題」的輪替公平性判斷使用（`NULL` 視為最優先，比任何有日期的都久）
- 2026-08-08 經 Robin 與 Claude 對話釐清：ADR-9 原規劃的「單一關鍵字、Rule-based Weight」書面規格跟 Robin 原始需求有落差，改為 LLM 語意判讀＋支援多組主題＋保底輪替分配，見 SPEC.md ADR-21

---

### youtube_pushed_videos

**建立日期**：2026-08-08
**用途**：Step 3.4 YouTube 技術情報歷史推播紀錄，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-58d、ADR-21。
**Migration 檔案**：`src/migrations/0050_create_youtube_pushed_videos_table.sql`

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

**設計理由**：
- 不加 `video_id` `UNIQUE`：同一支影片理論上可能在 30 天後再次被推薦，不強制唯一，去重靠查詢邏輯本身（篩掉 `pushed_on` 在過去 30 天內的紀錄）
- `topic` 允許 `NULL`：只是記錄推播當下對應的主題文字，供除錯與統計用，不影響去重邏輯（去重只看 `video_id` + `pushed_on`）

---

### job_search_criteria

**建立日期**：2026-08-09
**用途**：Step 4.1 求職搜尋條件，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-33、ADR-24 決策 3。
**Migration 檔案**：`src/migrations/0054_create_job_search_criteria_table.sql`

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

**設計理由**：
- 不設 `UNIQUE (user_id, keyword)` 之類的唯一約束：ADR-24 決策 3 明確允許同時存多組條件，不比照記帳預算/證照目標「一人一份設定、重新設定即覆蓋」的既有慣例
- `region`／`salary_min`／`salary_max`／`industry` 皆允許 `NULL`：對話收集時使用者可能表示「不限」，只有 `keyword` 是 104 搜尋 API 的必要參數
- **`industry` 欄位 2026-08-09 起停用**：Robin 指示移除產業篩選（104 API 該參數名稱不值得繼續猜測），對話流程與 `job_search.save_search_criteria()` 皆已不再收集/寫入這個欄位；欄位本身保留在資料庫（允許 `NULL`），不做 migration 刪除，避免非必要的破壞性操作

---

### job_companies

**建立日期**：2026-08-09
**用途**：Step 4.1 104 公司背景資料，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-35、ADR-24 決策 1。
**Migration 檔案**：`src/migrations/0055_create_job_companies_table.sql`

```sql
CREATE TABLE job_companies (
    id BIGSERIAL PRIMARY KEY,
    company_id_104 TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    region TEXT,
    industry TEXT,
    background TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**設計理由**：
- `company_id_104 UNIQUE`：FR-35a 用「這批職缺所屬公司是否已存在」判斷是否為新公司，也作為 `job_postings` 的外鍵
- `background` 允許 `NULL`：代表尚待 Robin 人工查詢回填（FR-35b～FR-35e Email/CSV/Drive 協作流程），`NULL` 與「已查過但沒查到」刻意不區分，Robin 若查無資料可自行填入「查無公開資訊」等文字，不強制系統分辨兩者

---

### job_postings

**建立日期**：2026-08-09
**用途**：Step 4.1 104 職缺資料，對應 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) FR-34、ADR-24 決策 4；Step 4.2 評分欄位見下方。
**Migration 檔案**：`src/migrations/0056_create_job_postings_table.sql`、`0057_add_is_closed_to_job_postings.sql`、`0058_add_scoring_fields_to_job_postings.sql`

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
    score NUMERIC(5,2),  -- 0058 追加
    recommend_reason TEXT,  -- 0058 追加
    skill_gap_note TEXT,  -- 0058 追加
    is_unliked BOOLEAN NOT NULL DEFAULT FALSE  -- 0058 追加
);

CREATE INDEX idx_job_postings_company_id_104 ON job_postings (company_id_104);
```

**設計理由**：
- `job_id_104 UNIQUE` 作為 FR-34d ETL 去重鍵值：已存在的職缺 `UPDATE` 既有紀錄（例如薪資/內容變動），不重複新增
- `applicant_count`／`source_updated_at` 允許 `NULL`：**（2026-08-09 更新）**Robin 透過瀏覽器 DevTools 手動實測 104 真實 API 後確認兩者皆可正常取得（`applicant_count` 取自列表 API 的 `applyCnt`，`source_updated_at` 取自詳情 API 的 `header.appearDate`），FR-37b 契合度評分已將兩者納入必要比對維度；個別職缺這兩欄剛好是 `NULL`（理論上少數情況）時評分照樣略過該維度，不強行湊資料
- **`is_closed`（2026-08-09 追加，migration `0057`）**：Robin 實測確認 104 API 列表／詳情回應皆含 `jobSwitch`／`switch` 欄位（`"on"` 代表仍開放），可自動判斷職缺是否已關閉，不需要如 ADR-26 決策 5 原訂備案走人工 Excel 標記；`submodules/job104/client.py` `search_list()` 直接解析，`upsert_job_posting()` 每次爬蟲重新爬到既有職缺時同步更新，FR-38a 排名時排除 `is_closed = TRUE` 的職缺
- **`score`／`recommend_reason`／`skill_gap_note`／`is_unliked`（2026-08-09 追加，migration `0058`，Step 4.2）**：`score`／`recommend_reason`／`skill_gap_note` 三欄由 FR-37 每週批次 Gemini 評分時一起寫入，允許 `NULL`（尚未評分，例如所屬公司背景還沒回填）；`is_unliked` 由 Robin 於 FR-38d 推薦 Excel 人工標記回填，預設 `FALSE`
- **刻意不建立 `rank` 欄位**：FR-38a 要求「全庫排名」與「本週新職缺排名」兩種排名並存，同一職缺在兩種排名裡名次不同，存成單一欄位語意衝突；排名改在 FR-38b 產生 Excel 的當下依 `score` 動態計算（`job_search.build_ranked_jobs()`），不持久化存進資料庫（Robin 於 2026-08-09 確認此設計）
- `first_seen_at` 供 FR-38a「本週新職缺排名」判斷依據；`last_crawled_at` 每次週排程重新爬到既有職缺時更新，供未來除錯/資料新鮮度判斷用
