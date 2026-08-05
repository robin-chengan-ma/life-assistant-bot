-- 重要通知模組：使用者生日（FR-53 家人生日提醒），對應 docs/specs/robinson/SPEC.md。
-- Robin 於 2026-08-04 核准此 ALTER TABLE SQL。
ALTER TABLE users ADD COLUMN birthday DATE;

COMMENT ON COLUMN users.birthday IS 'FR-53 生日提醒用；只比對月/日（西曆），年份若不確定就用占位年份，判斷生日當天一律用 EXTRACT(MONTH)/EXTRACT(DAY) 比對，不比對年份；NULL 代表尚未設定';
