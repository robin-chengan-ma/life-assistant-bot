-- 2026-11 功能大幅精簡（Robin 明確核准資料清空範圍）：運動/飲食/體態與記帳沒有值得保留的既有
-- 資料（筆數極少），予以清空重來；待辦事項同時清空並簡化成「純一次性日期＋文字提醒」，拿掉
-- status／30 分鐘前提醒／每日摘要／區間待辦等舊欄位（見 src/bot/todo.py 檔頭欄位假設）。

BEGIN;

-- 運動/飲食/體態：清空既有紀錄（exercise_categories 是類別定義表非紀錄，不清空）。
TRUNCATE TABLE body_weight_logs;
TRUNCATE TABLE exercise_logs;
TRUNCATE TABLE diet_logs;
TRUNCATE TABLE body_goals;

-- 記帳：清空既有交易與預算覆蓋值。
TRUNCATE TABLE transactions;
TRUNCATE TABLE budget_overrides;

-- 待辦事項：清空既有資料（新版無狀態概念，舊資料無法／無需映射），再簡化欄位結構。
TRUNCATE TABLE todos;

ALTER TABLE todos RENAME COLUMN due_at TO remind_at;
ALTER TABLE todos RENAME COLUMN reminded_30min_sent_at TO reminded_sent_at;
DROP INDEX IF EXISTS idx_todos_user_id_status;
DROP INDEX IF EXISTS idx_todos_due_at;
ALTER TABLE todos DROP COLUMN IF EXISTS remind_before_30min;
ALTER TABLE todos DROP COLUMN IF EXISTS status;
ALTER TABLE todos DROP COLUMN IF EXISTS daily_pushed_on;
ALTER TABLE todos DROP COLUMN IF EXISTS start_at;

CREATE INDEX idx_todos_user_id ON todos (user_id);
CREATE INDEX idx_todos_remind_at ON todos (remind_at);

COMMENT ON TABLE todos IS '待辦事項：純粹的一次性日期＋文字提醒推播，不含完成/取消/逾期狀態（2026-11 精簡）';
COMMENT ON COLUMN todos.remind_at IS '要推播提醒的時間點（原 due_at）';
COMMENT ON COLUMN todos.reminded_sent_at IS '推播去重記號，NULL 代表還沒推播過（原 reminded_30min_sent_at）';

COMMIT;
