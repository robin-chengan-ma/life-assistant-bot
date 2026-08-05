-- 重要通知模組：各類節日/生日通知的年度去重紀錄，對應 docs/specs/robinson/SPEC.md FR-53。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
CREATE TABLE important_notifications_log (
    id BIGSERIAL PRIMARY KEY,
    notification_key TEXT NOT NULL,
    year INT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (notification_key, year)
);

COMMENT ON TABLE important_notifications_log IS 'FR-53 重要通知的年度推播去重紀錄，一張表通用所有固定節日與生日類型，用 notification_key 區分';
COMMENT ON COLUMN important_notifications_log.id IS '內部主鍵';
COMMENT ON COLUMN important_notifications_log.notification_key IS '通知類型代碼：new_year／fathers_day／mothers_day／lunar_new_year_eve／lunar_new_year_day1／tomb_sweeping／mid_autumn／dragon_boat 等固定節日，生日則用 birthday_<user_id>（每位使用者各自獨立去重）';
COMMENT ON COLUMN important_notifications_log.year IS '這筆推播對應的年份（西曆），配合 notification_key 做 UNIQUE 約束，確保同一年同一類型只推播一次';
COMMENT ON COLUMN important_notifications_log.sent_at IS '實際推播的時間';
