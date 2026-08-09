-- Step 4.1（FR-33、FR-34b、FR-36，見 docs/specs/robinson/SPEC.md ADR-24）：求職模組個人設定欄位——
-- 履歷/期望工作敘述、結構化年資/期望薪資（供未來 Step 4.2 契合度評分使用）、每週爬蟲排程去重欄位
-- （比照 youtube_last_run_on／toeic_pipeline_last_run_on 既有慣例）。求職模組僅 Robin 一人可用
-- （job_search 開關 owner_only=True），故直接加在 users 表而非另開一人一份的 profile 表。
-- Robin 於 2026-08-09 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN job_resume TEXT;
ALTER TABLE users ADD COLUMN job_expectation TEXT;
ALTER TABLE users ADD COLUMN years_of_experience NUMERIC(4,1);
ALTER TABLE users ADD COLUMN expected_salary_min INT;
ALTER TABLE users ADD COLUMN expected_salary_max INT;
ALTER TABLE users ADD COLUMN job_search_last_run_on DATE;

COMMENT ON COLUMN users.job_resume IS 'FR-36：個人履歷全文（3500 字內），對話式收集，不含個資（電子郵件/手機號碼等）';
COMMENT ON COLUMN users.job_expectation IS 'FR-36：未來期望工作敘述（工作內容/企業文化/薪資/福利等自由文字）';
COMMENT ON COLUMN users.years_of_experience IS 'FR-36：結構化年資欄位（例如 3.5），供 Step 4.2 FR-37b 契合度評分比對職缺要求年資使用，不再靠 LLM 從自由文字猜測';
COMMENT ON COLUMN users.expected_salary_min IS 'FR-36：期望薪資下限，供 Step 4.2 FR-37b 契合度評分比對職缺薪資範圍使用';
COMMENT ON COLUMN users.expected_salary_max IS 'FR-36：期望薪資上限，供 Step 4.2 FR-37b 契合度評分比對職缺薪資範圍使用';
COMMENT ON COLUMN users.job_search_last_run_on IS 'FR-34b：104 職缺爬蟲週排程最後一次執行的日期（台灣時區），今天已執行過就不再重複觸發，比照 youtube_last_run_on 慣例';
