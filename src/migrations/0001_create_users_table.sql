CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE,
    role TEXT NOT NULL,
    is_owner BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS '使用者表：Telegram Bot 的每一位使用者（含 Robin 本人）；家人在通關密碼設定階段就會先建立一筆，此時 telegram_user_id 尚為 NULL，綁定成功後才補上';
COMMENT ON COLUMN users.id IS '內部主鍵';
COMMENT ON COLUMN users.telegram_user_id IS 'Telegram 使用者 ID；設定通關密碼階段尚未綁定時為 NULL，綁定成功後才寫入';
COMMENT ON COLUMN users.role IS '稱謂，例如「爸爸」；Robin 本人固定寫入 "Robin"';
COMMENT ON COLUMN users.is_owner IS '是否為管理者（Robin），依 telegram_user_id 是否等於 ROBIN_TELEGRAM_TOKEN 判斷後寫入';
COMMENT ON COLUMN users.created_at IS '這筆使用者記錄建立的時間（家人可能設定通關密碼當下就建立，早於實際綁定時間）';
