CREATE TABLE notification_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_key TEXT NOT NULL CHECK (notification_key IN (
        'todo', 'important_day', 'budget_alert', 'monthly_report',
        'tech_digest', 'youtube', 'job_search', 'exam_quiz'
    )),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notification_hour SMALLINT CHECK (notification_hour BETWEEN 0 AND 23),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, notification_key)
);

CREATE INDEX idx_notification_preferences_user_id
ON notification_preferences (user_id);

COMMENT ON TABLE notification_preferences IS 'Telegram 主動通知接收設定；關閉通知不停止來源功能與背景工作。';
COMMENT ON COLUMN notification_preferences.id IS '內部主鍵。';
COMMENT ON COLUMN notification_preferences.user_id IS '設定所屬使用者，對應 users.id；使用者刪除時一併刪除。';
COMMENT ON COLUMN notification_preferences.notification_key IS '通知類型：todo／important_day／budget_alert／monthly_report／tech_digest／youtube／job_search／exam_quiz。';
COMMENT ON COLUMN notification_preferences.is_enabled IS '是否接收此類 Telegram 主動通知；FALSE 不影響來源資料與背景工作。';
COMMENT ON COLUMN notification_preferences.notification_hour IS '允許自訂時保存台灣時間 0～23 時；NULL 使用該排程預設時間。';
COMMENT ON COLUMN notification_preferences.created_at IS '建立時間，由資料庫產生。';
COMMENT ON COLUMN notification_preferences.updated_at IS '最後更新時間，由資料庫觸發器維護。';

CREATE FUNCTION update_notification_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notification_preferences_updated_at
BEFORE UPDATE ON notification_preferences
FOR EACH ROW EXECUTE FUNCTION update_notification_preferences_updated_at();
