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
**Migration 檔案**：`src/migrations/0005_create_feature_toggles_table.sql`

```sql
CREATE TABLE feature_toggles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    feature_key TEXT NOT NULL CHECK (feature_key IN (
        'todo', 'job_search', 'budget', 'body', 'skill_growth',
        'mood_journal', 'friend_mode', 'important_notify'
    )),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, feature_key)
);

COMMENT ON TABLE feature_toggles IS '功能開關表：對應 FR-2，每位使用者各模組獨立開關';
COMMENT ON COLUMN feature_toggles.id IS '內部主鍵';
COMMENT ON COLUMN feature_toggles.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN feature_toggles.feature_key IS '功能代號：todo=待辦, job_search=求職, budget=記帳, body=體態管理, skill_growth=技能成長, mood_journal=心情小記, friend_mode=好友模式, important_notify=重要通知';
COMMENT ON COLUMN feature_toggles.is_enabled IS '是否開啟此功能';
COMMENT ON COLUMN feature_toggles.updated_at IS '最後變更時間';
```

**設計理由**：
- `feature_key` 用 `CHECK` 鎖定 FR-2 列出的 8 個模組英文代號，避免打錯字造成查詢對不上
- `UNIQUE (user_id, feature_key)` 確保每人每個功能只有一筆設定
- 新使用者綁定成功時，由程式邏輯一次幫他把 8 個 `feature_key` 都插入預設值（`is_enabled = TRUE`），不是 schema 本身的責任

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
