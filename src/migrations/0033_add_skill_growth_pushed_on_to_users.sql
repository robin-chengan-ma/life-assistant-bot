-- 個人技能成長模組：每日重點技術分享去重欄位（FR-22、FR-23），對應 docs/specs/robinson/SPEC.md。
-- Robin 於 2026-08-07 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN skill_growth_pushed_on DATE;

COMMENT ON COLUMN users.skill_growth_pushed_on IS 'FR-22 每日技術摘要推播去重用；記錄「今天是否已推播過」，比照 todos.daily_pushed_on 的慣例，避免同一天 /healthz 被觸發多次時重複推播；NULL 代表尚未推播過';
