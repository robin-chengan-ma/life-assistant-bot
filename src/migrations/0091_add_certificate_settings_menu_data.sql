CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE certificate_profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    certificate_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, certificate_key),
    CHECK (certificate_key = lower(btrim(certificate_key))),
    CHECK (btrim(display_name) <> '')
);

COMMENT ON TABLE certificate_profiles IS 'Owner 的證照設定名冊；停用不刪除歷史資料。';
COMMENT ON COLUMN certificate_profiles.id IS '證照設定流水號。';
COMMENT ON COLUMN certificate_profiles.user_id IS '所屬 users.id。';
COMMENT ON COLUMN certificate_profiles.certificate_key IS '證照名稱正規化小寫鍵。';
COMMENT ON COLUMN certificate_profiles.display_name IS 'Telegram 選單顯示名稱。';
COMMENT ON COLUMN certificate_profiles.is_active IS '是否顯示於設定選單。';
COMMENT ON COLUMN certificate_profiles.is_builtin IS '系統內建證照；TOEIC 不允許停用。';
COMMENT ON COLUMN certificate_profiles.created_at IS '建立時間，由資料庫產生。';
COMMENT ON COLUMN certificate_profiles.updated_at IS '最後更新時間，由資料庫觸發器維護。';

CREATE FUNCTION update_certificate_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_certificate_profiles_updated_at
BEFORE UPDATE ON certificate_profiles
FOR EACH ROW EXECUTE FUNCTION update_certificate_profiles_updated_at();

INSERT INTO certificate_profiles (user_id, certificate_key, display_name, is_active, is_builtin)
SELECT id, 'toeic', 'TOEIC', TRUE, TRUE FROM users WHERE is_owner = TRUE
ON CONFLICT (user_id, certificate_key) DO NOTHING;

INSERT INTO certificate_profiles (user_id, certificate_key, display_name, is_active, is_builtin)
SELECT DISTINCT user_id, lower(btrim(exam_type)), btrim(exam_type), TRUE, FALSE
FROM (
    SELECT user_id, exam_type FROM certificate_goals
    UNION SELECT user_id, exam_type FROM exam_official_scores
    UNION SELECT user_id, exam_type FROM certificate_daily_settings
    UNION SELECT user_id, exam_type FROM certificate_daily_schedule_overrides
    UNION SELECT user_id, exam_type FROM certificate_daily_assignments
    UNION SELECT user_id, exam_type FROM answer_logs
) AS known_certificates
WHERE btrim(exam_type) <> ''
ON CONFLICT (user_id, certificate_key) DO NOTHING;

ALTER TABLE exam_official_scores ADD COLUMN note TEXT;
COMMENT ON COLUMN exam_official_scores.note IS '正式應考成績的選填補充內容。';

ALTER TABLE certificate_daily_settings
ADD COLUMN toeic_listen_count INT,
ADD COLUMN toeic_write_count INT,
ADD COLUMN toeic_vocab_count INT,
ADD CONSTRAINT certificate_daily_settings_toeic_track_counts_check CHECK (
    (toeic_listen_count IS NULL AND toeic_write_count IS NULL AND toeic_vocab_count IS NULL)
    OR (toeic_listen_count >= 0 AND toeic_write_count >= 0 AND toeic_vocab_count >= 0
        AND daily_question_count = toeic_listen_count + toeic_write_count + toeic_vocab_count)
);
COMMENT ON COLUMN certificate_daily_settings.toeic_listen_count IS 'TOEIC 每日聽力題數；非 TOEIC 為 NULL。';
COMMENT ON COLUMN certificate_daily_settings.toeic_write_count IS 'TOEIC 每日讀寫題數；非 TOEIC 為 NULL。';
COMMENT ON COLUMN certificate_daily_settings.toeic_vocab_count IS 'TOEIC 每日單字題數；非 TOEIC 為 NULL。';

ALTER TABLE certificate_daily_schedule_overrides
ADD COLUMN toeic_listen_count INT,
ADD COLUMN toeic_write_count INT,
ADD COLUMN toeic_vocab_count INT,
ADD CONSTRAINT certificate_daily_schedule_overrides_toeic_track_counts_check CHECK (
    (toeic_listen_count IS NULL AND toeic_write_count IS NULL AND toeic_vocab_count IS NULL)
    OR (toeic_listen_count >= 0 AND toeic_write_count >= 0 AND toeic_vocab_count >= 0
        AND daily_question_count = toeic_listen_count + toeic_write_count + toeic_vocab_count)
);
COMMENT ON COLUMN certificate_daily_schedule_overrides.toeic_listen_count IS 'TOEIC 區間每日聽力題數；非 TOEIC 為 NULL。';
COMMENT ON COLUMN certificate_daily_schedule_overrides.toeic_write_count IS 'TOEIC 區間每日讀寫題數；非 TOEIC 為 NULL。';
COMMENT ON COLUMN certificate_daily_schedule_overrides.toeic_vocab_count IS 'TOEIC 區間每日單字題數；非 TOEIC 為 NULL。';

CREATE INDEX idx_certificate_profiles_active ON certificate_profiles (user_id, is_active, display_name);

ALTER TABLE certificate_daily_schedule_overrides
ADD CONSTRAINT certificate_daily_schedule_overrides_no_overlap
EXCLUDE USING gist (
    user_id WITH =,
    exam_type WITH =,
    daterange(start_date, end_date, '[]') WITH &&
);
