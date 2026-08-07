-- TOEIC 雙軌題庫 Pipeline 軌道一（人工上傳照片/音檔，Gemini Vision 解析），對應
-- docs/specs/robinson/SPEC.md FR-25a～FR-25c、Step 3.2。Robin 於 2026-08-07 核准此 CREATE TABLE SQL。
CREATE TABLE toeic_questions (
    id BIGSERIAL PRIMARY KEY,
    test_id TEXT NOT NULL,
    question_type TEXT NOT NULL CHECK (question_type IN ('write', 'listen')),
    question_number INT NOT NULL,
    question_text TEXT NOT NULL,
    options JSONB NOT NULL,
    image_gdrive_url TEXT NOT NULL,
    audio_gdrive_url TEXT,
    source_image_filename TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_toeic_questions_test_id ON toeic_questions (test_id);

COMMENT ON TABLE toeic_questions IS 'TOEIC 雙軌題庫軌道一：Robin 手動上傳到 Google Drive 的題目照片/音檔，經 Gemini Vision 解析、Groq Whisper 對齊/切割後寫入的高準確度題庫';
COMMENT ON COLUMN toeic_questions.id IS '內部主鍵';
COMMENT ON COLUMN toeic_questions.test_id IS '從檔名解析出的測驗場次代號（例如 toeic_0001_write_1.png 的 0001）';
COMMENT ON COLUMN toeic_questions.question_type IS '題目類型：write=填空/單字題（僅圖片），listen=聽力題（圖片+對應音檔）';
COMMENT ON COLUMN toeic_questions.question_number IS '該場次內的題號，對應檔名中的「第幾題」';
COMMENT ON COLUMN toeic_questions.question_text IS 'Gemini Vision 解析出的題目文字';
COMMENT ON COLUMN toeic_questions.options IS 'Gemini Vision 解析出的選項，JSON 陣列（例如 ["A. xxx", "B. xxx", ...]）；依 FR-25c 刻意不存正解，題目照片本身未必附答案';
COMMENT ON COLUMN toeic_questions.image_gdrive_url IS '題目照片的 Google Drive 網址';
COMMENT ON COLUMN toeic_questions.audio_gdrive_url IS '對應聽力音檔的 Google Drive 網址，write 類型為 NULL；listen 類型可能是 Robin 已切好的小檔，或系統從整包 MP3 切割後重新上傳的小檔';
COMMENT ON COLUMN toeic_questions.source_image_filename IS '來源圖片在 Google Drive 上的原始檔名，UNIQUE 約束供週排程掃描時判斷「這個檔案是否已經處理過」（去重，取代原規劃的檔名日期判斷，見 FR-25f 2026-08-07 修正）';
COMMENT ON COLUMN toeic_questions.created_at IS '這筆題目寫入的時間';
