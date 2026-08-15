ALTER TABLE users
    ADD COLUMN nickname TEXT,
    ADD COLUMN family_title TEXT,
    ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- 既有 role 欄位資料回填到 family_title，維持向前相容；Robin 本人（role='Robin'）
-- 不寫入 family_title，改以 nickname 呈現，避免與既有「role 混用授權與稱謂」的舊語意混淆。
UPDATE users
SET family_title = role
WHERE role IS NOT NULL AND role <> 'Robin';

UPDATE users
SET nickname = 'Robin'
WHERE role = 'Robin';

ALTER TABLE invite_codes
    ADD COLUMN expires_at TIMESTAMPTZ;

-- 既有未使用的通關密碼補上到期時間（以建立時間起算 24 小時），避免歷史資料變成永久有效。
UPDATE invite_codes
SET expires_at = created_at + INTERVAL '24 hours'
WHERE expires_at IS NULL;

ALTER TABLE invite_codes
    ALTER COLUMN expires_at SET NOT NULL;

COMMENT ON COLUMN users.nickname IS 'FR-4a 使用者暱稱，與家庭稱謂、授權身分分開保存；Mobile App 與 Telegram 共用顯示';
COMMENT ON COLUMN users.family_title IS 'FR-4a 家庭稱謂（例如「爸爸」），只作顯示用途，不承擔授權判斷；授權一律以 is_owner 判斷';
COMMENT ON COLUMN users.is_active IS 'FR-4d 帳號是否啟用；停用時後端拒絕 Telegram 與 Mobile 存取，不刪除帳號與既有資料';
COMMENT ON COLUMN invite_codes.expires_at IS 'FR-4b 通關密碼到期時間，建立起 24 小時；逾期即使未使用也視為失效';
