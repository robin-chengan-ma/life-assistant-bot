-- 記帳模組：使用者的每月支出預算上限，對應 docs/specs/robinson/SPEC.md FR-41、FR-43。
-- Robin 於 2026-08-04 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN monthly_budget NUMERIC(12,2);
ALTER TABLE users ADD COLUMN budget_alert_50_sent_month DATE;
ALTER TABLE users ADD COLUMN budget_alert_80_sent_month DATE;

COMMENT ON COLUMN users.monthly_budget IS 'FR-41 每月支出預算上限；使用者尚未設定時為 NULL，NULL 時不進行 FR-43 門檻檢查';
COMMENT ON COLUMN users.budget_alert_50_sent_month IS 'FR-43 50% 門檻預警去重用：已推播過該門檻的月份（每月第一天），避免同一個月重複推播；NULL 代表這個月還沒推播過';
COMMENT ON COLUMN users.budget_alert_80_sent_month IS 'FR-43 80% 門檻預警去重用，語意同 budget_alert_50_sent_month';
