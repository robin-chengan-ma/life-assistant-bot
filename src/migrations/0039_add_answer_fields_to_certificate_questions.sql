-- Step 3.3（FR-27、ADR-19 決策 2）：軌道一題目正解改用 Robin 拍照上傳的測驗書解答/詳解
-- （檔名 `{exam_type}_{test_id}_write/listen_{題號}_ans.png`），不再讓 AI 推論正解。
-- Robin 於 2026-08-07 核准此 ALTER TABLE SQL。
ALTER TABLE certificate_questions ADD COLUMN correct_answer TEXT;
ALTER TABLE certificate_questions ADD COLUMN explanation TEXT;
ALTER TABLE certificate_questions ADD COLUMN answer_source_filename TEXT UNIQUE;

COMMENT ON COLUMN certificate_questions.correct_answer IS '正解，來自 Robin 拍攝的測驗書解答照片（Gemini Vision 解析），非 AI 推論；NULL 代表這題還沒補正解，不會出現在每日推播候選池（見 ADR-19 決策 3）';
COMMENT ON COLUMN certificate_questions.explanation IS '詳解文字，同樣來自解答照片的 Vision 解析結果，NULL 代表尚未補上';
COMMENT ON COLUMN certificate_questions.answer_source_filename IS '對應的 `_ans` 答案照片檔名，UNIQUE 供去重判斷（避免同一張答案照重複解析覆蓋），比照 source_image_filename 的去重設計';
