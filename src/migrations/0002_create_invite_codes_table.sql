CREATE TABLE invite_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    user_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE invite_codes IS '通關密碼表：Robin 為每位家人設定的一次性通關密碼，設定當下就會連同 users 那筆待綁定的記錄一起建立';
COMMENT ON COLUMN invite_codes.id IS '內部主鍵';
COMMENT ON COLUMN invite_codes.code IS '通關密碼本身，僅能使用一次';
COMMENT ON COLUMN invite_codes.is_used IS '是否已被使用（綁定）過';
COMMENT ON COLUMN invite_codes.user_id IS '這組密碼對應的使用者，對應 users.id（稱謂記錄在 users.role，這裡不重複存）';
COMMENT ON COLUMN invite_codes.created_at IS 'Robin 設定這組密碼的時間';
COMMENT ON COLUMN invite_codes.updated_at IS '最後變更時間（例如密碼被使用綁定成功的當下）';
