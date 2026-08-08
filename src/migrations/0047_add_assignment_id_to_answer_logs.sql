-- Step 3.3（FR-27/FR-28，作答與批改流程）：answer_logs 新增可為 NULL 的 assignment_id 外鍵，
-- 讓「這筆每日推播出的題目是否已作答」的判斷變成單純查詢 answer_logs 有沒有對應這個
-- assignment_id 的紀錄，不需要靠日期比對猜測（同一題可能跨日被指派多次，日期比對容易誤判）。
-- Robin 於 2026-08-08 核准此 ALTER TABLE SQL。
ALTER TABLE answer_logs ADD COLUMN assignment_id BIGINT REFERENCES certificate_daily_assignments(id);

CREATE INDEX idx_answer_logs_assignment_id ON answer_logs (assignment_id);

COMMENT ON COLUMN answer_logs.assignment_id IS 'Step 3.3 作答流程：對應這筆答案是回答 certificate_daily_assignments 的哪一筆每日推播指派；可為 NULL 是保留彈性（理論上目前所有作答都經由每日推播指派，但不強制 NOT NULL，避免未來若有其他作答入口時需要再改 schema）；查詢「這個 assignment 是否已作答」直接用這個欄位比對，不用日期猜測';
