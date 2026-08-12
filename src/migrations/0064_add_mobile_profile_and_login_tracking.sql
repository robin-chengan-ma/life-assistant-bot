ALTER TABLE users
    ADD COLUMN gender TEXT,
    ADD COLUMN previous_login_at TIMESTAMPTZ,
    ADD COLUMN current_login_at TIMESTAMPTZ,
    ADD CONSTRAINT users_gender_check CHECK (gender IS NULL OR gender IN ('male', 'female'));

UPDATE users
SET gender = 'male'
WHERE role = 'Robin';

COMMENT ON COLUMN users.gender IS 'Mobile App 通用頭像性別：male 或 female；由 Robin 透過 Telegram 設定';
COMMENT ON COLUMN users.previous_login_at IS 'FR-65 前一次帳密登入成功時間；Refresh Token 續登不更新';
COMMENT ON COLUMN users.current_login_at IS 'FR-65 最近一次帳密登入成功時間；Refresh Token 續登不更新';
