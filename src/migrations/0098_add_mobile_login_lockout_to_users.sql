-- 2026-08-23：Mobile App 帳密登入連續錯誤鎖定（見 docs/ADR/discuss/mobile-app.md）。
-- mobile_login_failed_attempts：連續密碼錯誤次數，登入成功歸零。
-- mobile_login_locked_at：NULL 代表未鎖定；有值代表已鎖定時間，只能由 Owner 在 Telegram
-- 「權限管理」選單手動解鎖（清空為 NULL 並歸零錯誤次數），不會自動過期。
ALTER TABLE users ADD COLUMN mobile_login_failed_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN mobile_login_locked_at TIMESTAMPTZ;
