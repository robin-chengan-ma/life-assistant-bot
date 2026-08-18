-- FR-47a（批次2，2026-08-17）：運動紀錄表單全面改版，取代原本「時間／熱量」雙頁籤設計。
-- 新增全域共用的運動類別表，取代原本寫死在程式碼裡的固定類別字串；舊運動紀錄資料依定案
-- 直接清空，不做欄位相容回填，由新版重新開始累積。

CREATE TABLE exercise_categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_exercise_categories_normalized_name ON exercise_categories (normalized_name);

COMMENT ON TABLE exercise_categories IS '運動類別表（FR-47a）：全域共用，任何使用者可新增，新增時採正規化比對＋LLM 同義詞合併去重';
COMMENT ON COLUMN exercise_categories.name IS '類別顯示名稱（使用者輸入的原始文字）';
COMMENT ON COLUMN exercise_categories.normalized_name IS '正規化後（trim／全形轉半形／大小寫統一）的比對用欄位，UNIQUE 避免重複建立';

-- 種子資料：既有固定類別搬進新表（「其他」是 UI 端輸入新類別的 sentinel，不建列）。
INSERT INTO exercise_categories (name, normalized_name) VALUES
    ('跑步', '跑步'),
    ('健走', '健走'),
    ('騎自行車', '騎自行車'),
    ('游泳', '游泳'),
    ('重訓', '重訓'),
    ('打球', '打球'),
    ('瑜伽', '瑜伽');

-- 舊運動紀錄直接清空（FR-47a 定案），再改結構。
-- note 欄位已由 0025 建立，這裡沿用既有欄位，避免重複新增造成整條 migration 中斷。
TRUNCATE TABLE exercise_logs;

ALTER TABLE exercise_logs
    ADD COLUMN category_id BIGINT REFERENCES exercise_categories(id),
    ALTER COLUMN duration_minutes SET NOT NULL,
    DROP COLUMN input_mode,
    DROP COLUMN training_details,
    DROP CONSTRAINT IF EXISTS exercise_logs_input_mode_check,
    DROP CONSTRAINT IF EXISTS exercise_logs_mode_fields_check,
    DROP CONSTRAINT IF EXISTS exercise_logs_calorie_source_check,
    DROP CONSTRAINT IF EXISTS exercise_logs_calories_range_check,
    ADD CONSTRAINT exercise_logs_calorie_source_check CHECK (calorie_source IN ('ai', 'manual')),
    ADD CONSTRAINT exercise_logs_calories_range_check
        CHECK (estimated_calories IS NULL OR (estimated_calories > 0 AND estimated_calories <= 5000));

ALTER TABLE exercise_logs ALTER COLUMN category_id SET NOT NULL;

CREATE INDEX idx_exercise_logs_category_id ON exercise_logs (category_id);

COMMENT ON COLUMN exercise_logs.category_id IS '所屬運動類別，對應 exercise_categories.id（權威來源，供類別管理與同義詞合併使用）';
COMMENT ON COLUMN exercise_logs.activity IS '運動項目顯示文字，寫入當下複製自 exercise_categories.name 的 denormalized 快照，方便清單顯示與既有分析查詢不用額外 JOIN';
COMMENT ON COLUMN exercise_logs.note IS '補充內容（選填），取代原本只有重訓才有的「強度與組數」欄位，任何類別皆可填寫，AI 估算消耗熱量時一併參考；可能含個資，已經過 FR-13 個資遮蔽處理';
COMMENT ON COLUMN exercise_logs.calorie_source IS '消耗熱量來源：ai=交由 AI 依時長/心率/補充內容估算，manual=使用者自行輸入';
