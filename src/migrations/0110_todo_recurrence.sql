-- 2026-11-28（待辦事項支援「常態性（每月固定一天）」，見 docs/ADR/discuss/robinson.md）：Robin
-- 反饋信用卡、車貸這類每月固定某一天要繳費的待辦，不想每次都手動新增一筆，要求新增「常態性」
-- 類型，跟現有「一次性」並存。

BEGIN;

ALTER TABLE todos
ADD COLUMN IF NOT EXISTS recurrence_type TEXT NOT NULL DEFAULT 'once';

ALTER TABLE todos
ADD CONSTRAINT todos_recurrence_type_check
CHECK (recurrence_type IN ('once', 'monthly'));

ALTER TABLE todos
ADD COLUMN IF NOT EXISTS recurrence_day INTEGER;

ALTER TABLE todos
ADD CONSTRAINT todos_recurrence_day_check
CHECK (recurrence_day IS NULL OR (recurrence_day BETWEEN 1 AND 31));

-- 常態性待辦沒有固定的「某一天到某一天」區間概念（每個月都重複），兩個日期欄位改成可為 NULL；
-- 既有一次性待辦不受影響，仍然維持 NOT NULL 的實際資料（只是放寬欄位本身的限制）。
ALTER TABLE todos ALTER COLUMN remind_start_date DROP NOT NULL;
ALTER TABLE todos ALTER COLUMN remind_end_date DROP NOT NULL;

COMMENT ON COLUMN todos.recurrence_type IS
'待辦類型：once=一次性（維持既有 remind_start_date/remind_end_date 區間邏輯）、monthly=常態性，每月固定 recurrence_day 那天重複提醒';

COMMENT ON COLUMN todos.recurrence_day IS
'recurrence_type=monthly 時才有意義，1~31 的每月固定日期；該月天數不足時（例如 31 號遇到 2 月）退回當月最後一天';

COMMIT;
