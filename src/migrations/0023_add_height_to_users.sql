-- 體態管理模組：使用者身高（初始設定，變動才修正），對應 docs/specs/robinson/SPEC.md FR-46。
-- Robin 於 2026-08-04 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN height_cm NUMERIC(5,1) CHECK (height_cm BETWEEN 140 AND 220);

COMMENT ON COLUMN users.height_cm IS 'FR-46 身高（公分），初始設定、變動才修正；成人合理範圍 140~220 公分，App 層與 DB CHECK 雙重把關';
