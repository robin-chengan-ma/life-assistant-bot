-- 記帳模組擴充：每日記帳提醒去重欄位，對應 docs/specs/robinson/SPEC.md FR-42a。
-- Robin 於 2026-08-04 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN finance_reminder_sent_date DATE;

COMMENT ON COLUMN users.finance_reminder_sent_date IS 'FR-42a 每日記帳提醒去重用：今天是否已經推播過提醒，NULL 或不等於今天代表還沒推播過，比照 todos.daily_pushed_on 的做法';
