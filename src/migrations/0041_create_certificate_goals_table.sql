-- Step 3.3（FR-24、ADR-19）：證照目標設定（考試時間、目標分數），每個使用者同一 exam_type
-- 只保留一筆最新目標，重新設定即覆蓋。Robin 於 2026-08-07 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE certificate_goals IS 'Step 3.3 FR-24：使用者對某個 exam_type 設定的準備目標（考試時間、目標分數），Robinson 據此提供方向建議；同一使用者同一 exam_type 只保留一筆，重新設定即覆蓋（UPSERT）';
COMMENT ON COLUMN certificate_goals.target_date IS '預計應考日期，選填（使用者可能只想設定分數目標，不確定確切考試日期）';
COMMENT ON COLUMN certificate_goals.target_score IS '目標分數，用 TEXT 而非數字型別是因為 exam_type 開放任意證照類型，有些是數字分數（TOEIC 850）、有些是通過/未通過（GCP／AWS 這類證照沒有量化分數），選填';
