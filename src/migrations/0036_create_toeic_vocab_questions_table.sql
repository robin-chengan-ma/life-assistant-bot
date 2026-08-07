-- TOEIC 雙軌題庫 Pipeline 軌道二（Gemini 即時生成單字題），對應
-- docs/specs/robinson/SPEC.md FR-25d～FR-25e、Step 3.2。Robin 於 2026-08-07 核准此 CREATE TABLE SQL。
CREATE TABLE toeic_vocab_questions (
    id BIGSERIAL PRIMARY KEY,
    target_word TEXT NOT NULL,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option CHAR(1) NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    example_sentence TEXT NOT NULL,
    example_sentence_translation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_toeic_vocab_questions_target_word ON toeic_vocab_questions (LOWER(target_word));

COMMENT ON TABLE toeic_vocab_questions IS 'TOEIC 雙軌題庫軌道二：Gemini 即時生成的多益核心單字英翻中選擇題，生成後存表供後續測驗重複抽考，避免重複呼叫 API 浪費 Token（FR-25e）';
COMMENT ON COLUMN toeic_vocab_questions.id IS '內部主鍵';
COMMENT ON COLUMN toeic_vocab_questions.target_word IS '這題考的目標單字；LOWER(target_word) 上建唯一索引，避免同一個單字（含大小寫差異）重複生成，供週排程比對既有單字後請 Gemini 避開';
COMMENT ON COLUMN toeic_vocab_questions.question_text IS '英翻中選答題目文字';
COMMENT ON COLUMN toeic_vocab_questions.option_a IS '選項 A（繁體中文）';
COMMENT ON COLUMN toeic_vocab_questions.option_b IS '選項 B（繁體中文）';
COMMENT ON COLUMN toeic_vocab_questions.option_c IS '選項 C（繁體中文）';
COMMENT ON COLUMN toeic_vocab_questions.option_d IS '選項 D（繁體中文）';
COMMENT ON COLUMN toeic_vocab_questions.correct_option IS '正確選項代號（A/B/C/D）';
COMMENT ON COLUMN toeic_vocab_questions.example_sentence IS '目標單字的英文實用例句';
COMMENT ON COLUMN toeic_vocab_questions.example_sentence_translation IS '例句的繁體中文翻譯';
COMMENT ON COLUMN toeic_vocab_questions.created_at IS '這筆題目生成的時間';
