-- 體態管理模組：飲食/飲水紀錄表，對應 docs/specs/robinson/SPEC.md FR-48。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE diet_logs IS '飲食/飲水紀錄表：對應 FR-48，同一張表用 entry_type 區分飲食與飲水（設計比照 transactions.type），支援補記/更新/刪除';
COMMENT ON COLUMN diet_logs.id IS '內部主鍵';
COMMENT ON COLUMN diet_logs.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN diet_logs.entry_type IS '紀錄類型：food=飲食（需營養拆算）, water=飲水（只記毫升數）';
COMMENT ON COLUMN diet_logs.description IS '內容描述；food 為食物內容自由文字，water 固定寫「飲水」';
COMMENT ON COLUMN diet_logs.water_ml IS '飲水量（毫升），只有 entry_type=water 時才有值';
COMMENT ON COLUMN diet_logs.estimated_calories IS '估算熱量大卡，只有 entry_type=food 時才有值，由 Gemini 估算（見 src/bot/body.py estimate_diet_macros()）；估算失敗時為 NULL，不影響紀錄本身';
COMMENT ON COLUMN diet_logs.protein_g IS '估算蛋白質（公克），語意同 estimated_calories';
COMMENT ON COLUMN diet_logs.carbs_g IS '估算碳水化合物（公克），語意同 estimated_calories';
COMMENT ON COLUMN diet_logs.fat_g IS '估算脂肪（公克），語意同 estimated_calories';
COMMENT ON COLUMN diet_logs.entry_date IS '這筆紀錄實際發生的日期（可補記過去日期）；一律由 app 端依台灣時區算好日期後寫入';
COMMENT ON COLUMN diet_logs.created_at IS '這筆紀錄建立的時間';
COMMENT ON COLUMN diet_logs.updated_at IS '最後變更時間';
