-- 體態管理模組：運動紀錄表，對應 docs/specs/robinson/SPEC.md FR-47。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE exercise_logs IS '運動紀錄表：對應 FR-47，支援補記/更新/刪除';
COMMENT ON COLUMN exercise_logs.id IS '內部主鍵';
COMMENT ON COLUMN exercise_logs.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN exercise_logs.activity IS '運動項目（自由文字，例如「跑步」「重訓」）';
COMMENT ON COLUMN exercise_logs.duration_minutes IS '運動時長（分鐘）';
COMMENT ON COLUMN exercise_logs.heart_rate IS '心率（下/分鐘），選填';
COMMENT ON COLUMN exercise_logs.estimated_calories IS '估算消耗大卡，由 Gemini 依項目/時長/心率估算（見 src/bot/body.py estimate_exercise_calories()）；估算失敗時為 NULL，不影響紀錄本身';
COMMENT ON COLUMN exercise_logs.entry_date IS '這筆運動實際發生的日期（可補記過去日期）；一律由 app 端依台灣時區算好日期後寫入';
COMMENT ON COLUMN exercise_logs.note IS '備註，可能含個資，已經過 FR-13 個資遮蔽處理，選填';
COMMENT ON COLUMN exercise_logs.created_at IS '這筆紀錄建立的時間';
COMMENT ON COLUMN exercise_logs.updated_at IS '最後變更時間';
