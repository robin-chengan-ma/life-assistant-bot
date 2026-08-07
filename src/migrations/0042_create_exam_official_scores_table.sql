-- Step 3.3（FR-30、ADR-19 決策 7）：保留欄位記錄實際應考日期與正式成績，跟「每日小考作答
-- 紀錄」（answer_logs）是不同概念，同一 exam_type 可能多次應考、各自獨立一筆。
-- Robin 於 2026-08-07 核准此 CREATE TABLE SQL。
CREATE TABLE exam_official_scores (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    exam_date DATE NOT NULL,
    score TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_exam_official_scores_user_exam_type ON exam_official_scores (user_id, exam_type);

COMMENT ON TABLE exam_official_scores IS 'Step 3.3 FR-30：使用者實際應考的正式成績紀錄，跟每日小考的 answer_logs 是不同概念（一次考試的最終結果 vs. 每天練習的逐題紀錄），不與 answer_logs 混用；同一 exam_type 可能多次應考，各自獨立一筆，不做 UNIQUE 限制';
COMMENT ON COLUMN exam_official_scores.score IS '正式成績，用 TEXT 而非數字型別是因為 exam_type 開放任意證照類型，有些是數字分數、有些是通過/未通過，理由同 certificate_goals.target_score';
