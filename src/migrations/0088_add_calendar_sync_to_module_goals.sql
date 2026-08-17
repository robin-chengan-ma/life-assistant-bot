-- 批次3補做（Robin 要求不得漏做）：記帳／收藏清單目標新增流程補上 Google Calendar 同步問句，
-- 欄位設計完全比照 body_goals（0032 migration）。
ALTER TABLE module_goals ADD COLUMN sync_to_calendar BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE module_goals ADD COLUMN google_calendar_event_id TEXT;

COMMENT ON COLUMN module_goals.sync_to_calendar IS '設定當下使用者是否選擇同步到 Google 家庭共用行事曆（FR-66c），MVP 不支援事後修改，比照 body_goals.sync_to_calendar';
COMMENT ON COLUMN module_goals.google_calendar_event_id IS 'Google Calendar 事件 ID；sync_to_calendar=TRUE 時才會有值，供更新/達成/取消目標時對應到已建立的 Calendar 事件';
