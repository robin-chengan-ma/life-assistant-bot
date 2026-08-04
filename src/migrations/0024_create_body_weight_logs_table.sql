-- 體態管理模組：體重紀錄表，對應 docs/specs/robinson/SPEC.md FR-46。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE body_weight_logs IS '體重紀錄表：對應 FR-46，使用者「有量才記」的體重紀錄，支援補記/更新/刪除';
COMMENT ON COLUMN body_weight_logs.id IS '內部主鍵';
COMMENT ON COLUMN body_weight_logs.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN body_weight_logs.weight_kg IS '體重（公斤），合理範圍檢查（>=40）由 App 層與 DB CHECK 雙重把關';
COMMENT ON COLUMN body_weight_logs.entry_date IS '這筆體重實際量測的日期（可補記過去日期）；一律由 app 端依台灣時區算好日期後寫入，設計比照 mood_journals.entry_date';
COMMENT ON COLUMN body_weight_logs.note IS '備註，可能含個資，已經過 FR-13 個資遮蔽處理，選填';
COMMENT ON COLUMN body_weight_logs.created_at IS '這筆紀錄建立的時間';
COMMENT ON COLUMN body_weight_logs.updated_at IS '最後變更時間';
