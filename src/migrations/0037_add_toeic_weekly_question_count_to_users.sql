-- TOEIC 雙軌題庫 Pipeline：軌道二每週生成題數設定 + 排程去重欄位，對應
-- docs/specs/robinson/SPEC.md FR-25e、FR-25f、Step 3.2。Robin 於 2026-08-07 核准此 ALTER TABLE SQL，
-- 預設 21 題（Robin 指定：一天 3 題 x 7 天）。
ALTER TABLE users ADD COLUMN toeic_weekly_question_count INT NOT NULL DEFAULT 21;
ALTER TABLE users ADD COLUMN toeic_pipeline_last_run_on DATE;

COMMENT ON COLUMN users.toeic_weekly_question_count IS 'TOEIC 軌道二每週排程要生成並存入 toeic_vocab_questions 的題數，預設 21（Robin 可自訂，日後除以 7 即為每日推播題數，推播機制留待 Step 3.3）';
COMMENT ON COLUMN users.toeic_pipeline_last_run_on IS 'TOEIC 雙軌 Pipeline 週排程去重：記錄最後一次執行當下的日期（台灣時區），避免 /healthz 每 10 分鐘觸發在同一個週日 22:00 的整個小時內重複掃描 Drive／重複生成超過預期題數的單字題，比照 todos.daily_pushed_on 慣例';
