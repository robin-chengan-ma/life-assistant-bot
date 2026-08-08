-- Step 3.3（FR-26、ADR-20）：使用者對某個 exam_type 的每日出題設定（每日題數、TOEIC 專屬的
-- 三軌比例、新題/複習題比例）。Robin 於 2026-08-08 核准此 CREATE TABLE SQL。
CREATE TABLE certificate_daily_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    exam_type TEXT NOT NULL,
    daily_question_count INT NOT NULL DEFAULT 6,
    review_ratio_new INT NOT NULL DEFAULT 7,
    review_ratio_review INT NOT NULL DEFAULT 3,
    listen_ratio INT,
    write_ratio INT,
    vocab_ratio INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_type)
);

COMMENT ON TABLE certificate_daily_settings IS 'Step 3.3 FR-26：每個使用者對某個 exam_type 的每日出題設定；同一使用者同一 exam_type 只保留一筆最新設定，重新設定即覆蓋（UPSERT），比照 certificate_goals 的設計';
COMMENT ON COLUMN certificate_daily_settings.daily_question_count IS '每日出題數量，預設 6 題（沿用 FR-25 原文 TOEIC 預設：1 聽力+2 填空+3 單字）；非 TOEIC 證照只能調這個欄位，見 ADR-20 決策 1';
COMMENT ON COLUMN certificate_daily_settings.review_ratio_new IS '新題:複習題比例當中「新題」的份額，預設 7；跟 listen/write/vocab 三軌比例是不同維度，所有 exam_type 通用，見 ADR-20 決策 2';
COMMENT ON COLUMN certificate_daily_settings.review_ratio_review IS '新題:複習題比例當中「複習題」的份額，預設 3，語意同 review_ratio_new';
COMMENT ON COLUMN certificate_daily_settings.listen_ratio IS 'TOEIC 專屬：聽力題在總出題數中的比例份額；非 TOEIC 證照固定 NULL（只有單一題庫池，沒有三軌可分配），見 ADR-20 決策 1';
COMMENT ON COLUMN certificate_daily_settings.write_ratio IS 'TOEIC 專屬：填空題比例份額，語意同 listen_ratio';
COMMENT ON COLUMN certificate_daily_settings.vocab_ratio IS 'TOEIC 專屬：單字題比例份額，語意同 listen_ratio';
