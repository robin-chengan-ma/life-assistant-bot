-- 體態目標新增 Google Calendar 同步欄位，對應 docs/specs/robinson/SPEC.md FR-66c、ADR-17。
-- Robin 於 2026-08-05 核准此 ALTER TABLE SQL。
ALTER TABLE body_goals ADD COLUMN sync_to_calendar BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE body_goals ADD COLUMN google_calendar_event_id TEXT;

COMMENT ON COLUMN body_goals.sync_to_calendar IS '設定當下使用者是否選擇同步到 Google 家庭共用行事曆（FR-66c），MVP 不支援事後修改';
COMMENT ON COLUMN body_goals.google_calendar_event_id IS 'Google Calendar 事件 ID；sync_to_calendar=TRUE 時才會有值，供更新/達成/取消目標時對應到已建立的 Calendar 事件';
