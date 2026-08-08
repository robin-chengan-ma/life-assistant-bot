-- Step 3.4（FR-59a、ADR-21）：YouTube 技術情報週推播去重欄位，比照 toeic_pipeline_last_run_on
-- 既有慣例，避免週四當天 /healthz 多次觸發重複推播。Robin 於 2026-08-08 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN youtube_last_run_on DATE;

COMMENT ON COLUMN users.youtube_last_run_on IS 'FR-59a：YouTube 技術情報週推播最後一次執行的日期，今天已執行過就不再重複推播';
