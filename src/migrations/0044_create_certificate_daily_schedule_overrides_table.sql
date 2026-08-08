-- Step 3.3（FR-26、ADR-20 決策 5）：彈性排程的日期區間覆蓋，比照 budget_overrides
-- 「全局預設值＋特殊區間覆蓋」的既有模式。Robin 於 2026-08-08 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE certificate_daily_schedule_overrides IS 'Step 3.3 FR-26：某個日期區間的每日出題數量覆蓋，查詢當天生效題數時先查是否有覆蓋當天的區間，沒有才 fallback 用 certificate_daily_settings 的全局值，見 ADR-20 決策 5；「今天改到別天」用兩筆覆蓋組合（今天設 0＋目標日加開），「直接取消今天的」用單筆今天 daily_question_count=0 表示';
COMMENT ON COLUMN certificate_daily_schedule_overrides.daily_question_count IS '該區間每天的出題數量，允許 0（代表這幾天完全不出題，供「取消」語意使用）';
