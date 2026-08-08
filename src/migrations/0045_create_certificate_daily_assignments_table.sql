-- Step 3.3（FR-27、FR-28、ADR-20）：記錄每天實際推播了哪幾題，供 20:00 提醒／23:00 視為跳過
-- 判斷「還沒作答的題目」、以及錯題複習池計算使用。Robin 於 2026-08-08 核准此 CREATE TABLE SQL。
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

COMMENT ON TABLE certificate_daily_assignments IS 'Step 3.3：每日 08:00 推播當下寫入「今天推了哪幾題」，兩個可為 NULL 的外鍵＋CHECK 串連軌道一/軌道二題庫，設計比照 answer_logs；是否已作答靠比對同一題目在 answer_logs 有沒有對應紀錄判斷，本表不直接存作答狀態';
COMMENT ON COLUMN certificate_daily_assignments.is_review IS '這題是不是從錯題複習池挑出來的（而非全新題目），供之後統計/除錯使用，不影響作答批改邏輯本身';
