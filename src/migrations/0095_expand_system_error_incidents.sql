ALTER TABLE system_error_reports
ADD COLUMN source_platform TEXT NOT NULL DEFAULT 'telegram',
ADD COLUMN occurrence_count INTEGER NOT NULL DEFAULT 1,
ADD COLUMN last_occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
ADD COLUMN resolved_by_user_id BIGINT REFERENCES users(id) ON DELETE RESTRICT,
ADD COLUMN resolved_at TIMESTAMPTZ,
ADD CONSTRAINT system_error_reports_source_platform_check
    CHECK (source_platform IN ('telegram', 'mobile')),
ADD CONSTRAINT system_error_reports_occurrence_count_check
    CHECK (occurrence_count > 0);

UPDATE system_error_reports
SET last_occurred_at = occurred_at,
    resolved_by_user_id = CASE
        WHEN resolution IS NOT NULL THEN (SELECT id FROM users WHERE is_owner = TRUE ORDER BY id LIMIT 1)
        ELSE NULL
    END,
    resolved_at = CASE WHEN resolution IS NOT NULL THEN updated_at ELSE NULL END;

ALTER TABLE system_error_reports
ADD CONSTRAINT system_error_reports_resolution_state_check
CHECK (
    (resolution IS NULL AND resolved_by_user_id IS NULL AND resolved_at IS NULL)
    OR (resolution IS NOT NULL AND resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL)
);

CREATE TABLE system_error_affected_users (
    id BIGSERIAL PRIMARY KEY,
    system_error_report_id BIGINT NOT NULL REFERENCES system_error_reports(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT system_error_affected_users_report_user_unique
        UNIQUE (system_error_report_id, user_id)
);

CREATE INDEX idx_system_error_reports_pending_dedup
ON system_error_reports (source_platform, triggering_feature, error_summary, last_occurred_at DESC)
WHERE resolution IS NULL;

COMMENT ON COLUMN system_error_reports.source_platform IS '事故來源平台：telegram 或 mobile。';
COMMENT ON COLUMN system_error_reports.occurrence_count IS '同類未結案事故在 10 分鐘合併後的累計發生次數。';
COMMENT ON COLUMN system_error_reports.last_occurred_at IS '事故最近一次發生時間；新事故等於 occurred_at。';
COMMENT ON COLUMN system_error_reports.resolved_by_user_id IS '結案的 Owner users.id；未結案為 NULL。';
COMMENT ON COLUMN system_error_reports.resolved_at IS '結案時間；未結案為 NULL。';
COMMENT ON TABLE system_error_affected_users IS 'Mobile App 事故可辨識的受影響使用者；未知使用者不建立資料列。';
COMMENT ON COLUMN system_error_affected_users.id IS '內部主鍵。';
COMMENT ON COLUMN system_error_affected_users.system_error_report_id IS '對應 system_error_reports.id；刪除事故時一併刪除。';
COMMENT ON COLUMN system_error_affected_users.user_id IS '受影響的 users.id；保留事故歷史故限制刪除使用者。';
COMMENT ON COLUMN system_error_affected_users.created_at IS '建立時間，由資料庫產生。';
