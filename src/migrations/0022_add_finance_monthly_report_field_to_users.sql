-- 記帳模組擴充：月底自動月報推播去重欄位，對應 docs/specs/robinson/SPEC.md FR-44a。
-- Robin 於 2026-08-04 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN finance_monthly_report_sent_month DATE;

COMMENT ON COLUMN users.finance_monthly_report_sent_month IS 'FR-44a 月底記帳月報推播去重用：已推播過月報的月份（每月第一天），NULL 代表這個月還沒推播過，比照 users.budget_alert_50_sent_month 的做法';
