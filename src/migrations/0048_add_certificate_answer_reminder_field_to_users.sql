-- Step 3.3（FR-28，作答提醒）：20:00 作答提醒的推播去重欄位，比照
-- `toeic_pipeline_last_run_on` 既有慣例，避免 /healthz 同一小時內多次觸發重複推播。
-- Robin 於 2026-08-08 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN certificate_answer_reminder_sent_on DATE;

COMMENT ON COLUMN users.certificate_answer_reminder_sent_on IS 'FR-28：20:00 作答提醒最後一次推播的日期，當天已推播過就不再重複推播；只有「還有題目沒作答」時才會推播並寫入這個欄位，全都作答完不會更新（下次還有未作答題目時仍會提醒）';
