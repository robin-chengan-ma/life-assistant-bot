CREATE TABLE user_password_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_password_history_user_id
    ON user_password_history (user_id);

COMMENT ON TABLE user_password_history IS
    'FR-68／FR-72 Mobile App 永久密碼歷程；只保存 bcrypt 雜湊，用於禁止重複使用舊密碼';
COMMENT ON COLUMN user_password_history.password_hash IS
    '使用者曾使用過的 bcrypt 單向雜湊，不保存或提供明碼密碼';
