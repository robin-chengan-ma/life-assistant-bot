ALTER TABLE users
    ADD COLUMN password_hash TEXT,
    ADD COLUMN password_changed_at TIMESTAMPTZ,
    ADD COLUMN refresh_token_hash TEXT,
    ADD COLUMN refresh_token_expires_at TIMESTAMPTZ,
    ADD CONSTRAINT users_refresh_token_pair_check CHECK (
        (refresh_token_hash IS NULL AND refresh_token_expires_at IS NULL)
        OR (refresh_token_hash IS NOT NULL AND refresh_token_expires_at IS NOT NULL)
    );

COMMENT ON COLUMN users.password_hash IS 'FR-65 App 登入密碼的 bcrypt 單向雜湊；既有使用者首次透過忘記密碼流程建立';
COMMENT ON COLUMN users.password_changed_at IS 'FR-65 App 密碼最後修改時間';
COMMENT ON COLUMN users.refresh_token_hash IS 'FR-65c 目前有效 Refresh Token 的 bcrypt 雜湊；新登入、Rolling Refresh 或登出時更新';
COMMENT ON COLUMN users.refresh_token_expires_at IS 'FR-65c Refresh Token 到期時間，固定自簽發日起 30 天';
