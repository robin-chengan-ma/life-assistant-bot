ALTER TABLE system_error_reports
ADD COLUMN owner_notification_method TEXT,
ADD COLUMN owner_notification_status TEXT NOT NULL DEFAULT 'pending',
ADD COLUMN owner_notified_at TIMESTAMPTZ,
ADD COLUMN recovery_status TEXT NOT NULL DEFAULT 'pending',
ADD COLUMN recovery_sent_at TIMESTAMPTZ,
ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
ADD CONSTRAINT system_error_reports_owner_notification_method_check
    CHECK (owner_notification_method IS NULL OR owner_notification_method IN ('telegram', 'email')),
ADD CONSTRAINT system_error_reports_owner_notification_status_check
    CHECK (owner_notification_status IN ('pending', 'sent', 'undelivered')),
ADD CONSTRAINT system_error_reports_recovery_status_check
    CHECK (recovery_status IN ('pending', 'partial', 'sent'));

COMMENT ON COLUMN system_error_reports.owner_notification_method IS 'Robin 最後成功收到錯誤通知的管道：telegram 或 email；未送達為 NULL。';
COMMENT ON COLUMN system_error_reports.owner_notification_status IS 'Robin 錯誤通知狀態：pending、sent 或 undelivered。';
COMMENT ON COLUMN system_error_reports.owner_notified_at IS 'Robin 最後成功收到錯誤通知的時間。';
COMMENT ON COLUMN system_error_reports.recovery_status IS '康復通知狀態：pending、partial 或 sent。';
COMMENT ON COLUMN system_error_reports.recovery_sent_at IS '最後一次成功發送康復通知的時間。';
COMMENT ON COLUMN system_error_reports.updated_at IS '最後更新時間，由資料庫觸發器維護。';

CREATE FUNCTION update_system_error_reports_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_system_error_reports_updated_at
BEFORE UPDATE ON system_error_reports
FOR EACH ROW EXECUTE FUNCTION update_system_error_reports_updated_at();

CREATE TABLE system_error_notification_recipients (
    id BIGSERIAL PRIMARY KEY,
    system_error_report_id BIGINT NOT NULL REFERENCES system_error_reports(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    notification_type TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    notified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT system_error_notification_recipients_type_check
        CHECK (notification_type IN ('incident', 'recovery')),
    CONSTRAINT system_error_notification_recipients_delivery_check
        CHECK (delivery_status IN ('sent', 'failed')),
    CONSTRAINT system_error_notification_recipients_notified_at_check
        CHECK ((delivery_status = 'sent' AND notified_at IS NOT NULL)
            OR (delivery_status = 'failed' AND notified_at IS NULL))
);

COMMENT ON TABLE system_error_notification_recipients IS '每次系統事故與康復通知的實際收件人及 Telegram 送達結果。';
COMMENT ON COLUMN system_error_notification_recipients.id IS '內部主鍵。';
COMMENT ON COLUMN system_error_notification_recipients.system_error_report_id IS '對應 system_error_reports.id；刪除事故時一併刪除收件紀錄。';
COMMENT ON COLUMN system_error_notification_recipients.user_id IS '實際嘗試通知的 users.id；保留歷史故限制刪除使用者。';
COMMENT ON COLUMN system_error_notification_recipients.notification_type IS '通知階段：incident 為事故通知，recovery 為康復通知。';
COMMENT ON COLUMN system_error_notification_recipients.delivery_status IS 'Telegram 發送結果：sent 或 failed。';
COMMENT ON COLUMN system_error_notification_recipients.notified_at IS '成功發送時間；失敗時為 NULL。';
COMMENT ON COLUMN system_error_notification_recipients.created_at IS '建立時間，由資料庫產生。';
COMMENT ON COLUMN system_error_notification_recipients.updated_at IS '最後更新時間，由資料庫觸發器維護。';

CREATE FUNCTION update_system_error_notification_recipients_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_system_error_notification_recipients_updated_at
BEFORE UPDATE ON system_error_notification_recipients
FOR EACH ROW EXECUTE FUNCTION update_system_error_notification_recipients_updated_at();

CREATE INDEX idx_system_error_notification_recipients_report
ON system_error_notification_recipients (system_error_report_id, notification_type, delivery_status);
