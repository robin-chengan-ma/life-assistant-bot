-- 證照題庫軌道一泛用化：不再限定 TOEIC，開放任意證照類型（GCP／AWS...），對應
-- docs/specs/robinson/SPEC.md FR-25a、Step 3.2 追記。Robin 於 2026-08-07 核准此 ALTER TABLE SQL。
ALTER TABLE toeic_questions RENAME TO certificate_questions;
ALTER INDEX idx_toeic_questions_test_id RENAME TO idx_certificate_questions_test_id;

ALTER TABLE certificate_questions ADD COLUMN exam_type TEXT NOT NULL DEFAULT 'toeic';
ALTER TABLE certificate_questions ALTER COLUMN exam_type DROP DEFAULT;

CREATE INDEX idx_certificate_questions_exam_type ON certificate_questions (exam_type);

COMMENT ON TABLE certificate_questions IS '證照題庫軌道一：Robin 手動上傳到 Google Drive 的題目照片/音檔，經 Gemini Vision 解析（聽力題另經 Groq Whisper 對齊/切割）後寫入的高準確度題庫；exam_type 開放任意字串（toeic／gcp／aws...），不寫死清單，新增證照類型不需要改程式碼或建 migration，只要檔名第一段換成新的 exam_type 即可';
COMMENT ON COLUMN certificate_questions.exam_type IS '證照類型，從檔名第一段解析而來（例如 toeic／gcp／aws），開放任意字串，不受 CHECK 限制，未來新增證照類型不需要改程式碼';
