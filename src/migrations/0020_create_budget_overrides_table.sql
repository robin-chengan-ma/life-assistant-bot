-- 記帳模組擴充：預算特殊月份覆蓋，對應 docs/specs/robinson/SPEC.md FR-41a。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
CREATE TABLE budget_overrides (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, year, month)
);

COMMENT ON TABLE budget_overrides IS 'FR-41a 預算特殊月份覆蓋：使用者可對某幾個月設定跟全局預設（users.monthly_budget）不同的支出預算上限，查詢當月生效預算時優先用這裡的值，沒有才 fallback 用全局預設';
COMMENT ON COLUMN budget_overrides.id IS '內部主鍵';
COMMENT ON COLUMN budget_overrides.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN budget_overrides.year IS '這筆覆蓋值套用的年份';
COMMENT ON COLUMN budget_overrides.month IS '這筆覆蓋值套用的月份（1~12）';
COMMENT ON COLUMN budget_overrides.amount IS '這個月的特殊預算上限金額，一律為正數';
COMMENT ON COLUMN budget_overrides.created_at IS '這筆覆蓋值建立的時間';
