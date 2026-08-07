-- Step 3.3（FR-27、FR-29、ADR-19 決策 6）：作答紀錄，串連軌道一（certificate_questions）與
-- 軌道二（toeic_vocab_questions）兩張分開的題庫表，供每日推播批改與成效統計使用。
-- Robin 於 2026-08-07 核准此 CREATE TABLE SQL。
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
    CONSTRAINT answer_logs_exactly_one_question CHECK (
        (certificate_question_id IS NOT NULL AND vocab_question_id IS NULL)
        OR (certificate_question_id IS NULL AND vocab_question_id IS NOT NULL)
    )
);

CREATE INDEX idx_answer_logs_user_answered_on ON answer_logs (user_id, answered_on);
CREATE INDEX idx_answer_logs_user_exam_type ON answer_logs (user_id, exam_type);

COMMENT ON TABLE answer_logs IS 'Step 3.3 作答紀錄：每次作答一筆，供每日推播批改、錯題複習與 FR-29 成效統計使用；用兩個可為 NULL 的外鍵 + CHECK 限制只能填一個，串連軌道一/軌道二兩張分開的題庫表，避免統計查詢需要 UNION 兩張表（見 SPEC.md ADR-19 決策 6）';
COMMENT ON COLUMN answer_logs.certificate_question_id IS '對應軌道一考古題（certificate_questions.id）；作答軌道二單字題時此欄位為 NULL';
COMMENT ON COLUMN answer_logs.vocab_question_id IS '對應軌道二單字題（toeic_vocab_questions.id）；作答軌道一考古題時此欄位為 NULL';
COMMENT ON COLUMN answer_logs.exam_type IS '證照類型，寫入當下從對應題目複製過來（軌道二固定為 toeic），避免統計查詢時需要額外 JOIN 回題庫表才能篩選';
COMMENT ON COLUMN answer_logs.question_type IS '題型維度，值為 write／listen（軌道一，複製自 certificate_questions.question_type）或 vocab（軌道二單字題固定值），供 FR-29「最常出錯的地方」統計使用，同樣為避免額外 JOIN 而寫入當下複製';
COMMENT ON COLUMN answer_logs.is_correct IS '這題是否答對';
COMMENT ON COLUMN answer_logs.answered_on IS '實際作答日期（台灣時區），供 FR-29 依日期區間統計與「排除未作答日」判斷使用';
