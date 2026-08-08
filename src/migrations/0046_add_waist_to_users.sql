-- 體態管理模組擴充：使用者腰圍（初始設定，變動才修正，比照 height_cm 的既有設計），對應
-- docs/specs/robinson/SPEC.md FR-46。腰圍只是參考指標，不是必要欄位、也不參與 BMI 計算
-- （BMI 只需要身高體重）。Robin 於 2026-08-08 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN waist_cm NUMERIC(5,1) CHECK (waist_cm BETWEEN 40 AND 200);

COMMENT ON COLUMN users.waist_cm IS 'FR-46 腰圍（公分，參考指標，非必要），初始設定、變動才修正；合理範圍 40~200 公分（比身高體重寬鬆，因為只是參考用途），App 層與 DB CHECK 雙重把關；BMI 計算不使用這個欄位';
