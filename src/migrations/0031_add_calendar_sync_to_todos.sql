-- 待辦事項新增 Google Calendar 同步欄位，對應 docs/specs/robinson/SPEC.md FR-66a、ADR-17。
-- Robin 於 2026-08-05 核准此 ALTER TABLE SQL。
ALTER TABLE todos ADD COLUMN sync_to_calendar BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE todos ADD COLUMN google_calendar_event_id TEXT;

COMMENT ON COLUMN todos.sync_to_calendar IS '建立當下使用者是否選擇同步到 Google 家庭共用行事曆（FR-66a），MVP 不支援事後修改';
COMMENT ON COLUMN todos.google_calendar_event_id IS 'Google Calendar 事件 ID；sync_to_calendar=TRUE 時才會有值，供更新/刪除待辦事項時對應到已建立的 Calendar 事件';
