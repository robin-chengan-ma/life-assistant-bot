-- 2026-11-26（生日推播對象全名，見 docs/ADR/discuss/robinson.md）：家人之間的暱稱／家庭稱謂可能
-- 重名或無法分辨身份（例如弟媳的父母雙方都被稱作「媽媽」「爸爸」），Robin 要求「自行選擇」推播
-- 對象清單改顯示全名。新增 `users.full_name`，並嘗試用既有 nickname／family_title／role 比對
-- 回填目前已知的 4 筆資料；比對不到的既有使用者 `full_name` 留 NULL，由 Robin 之後透過 Telegram
-- 權限管理流程的新問題補齊（見 commands.py 新增的 awaiting_full_name 步驟），後續新建立的使用者
-- 一律必填。

BEGIN;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS full_name TEXT;

COMMENT ON COLUMN users.full_name IS
'全名，用於生日推播「自行選擇」對象清單等需要分辨真實身份的地方；暱稱/家庭稱謂可能重複或無法分辨身份';

UPDATE users SET full_name = '馬承安'
WHERE full_name IS NULL AND (nickname = 'Robin' OR role = 'Robin' OR is_owner = TRUE);

UPDATE users SET full_name = '廖羽璇'
WHERE full_name IS NULL AND (nickname = '羽璇' OR family_title = '羽璇' OR role = '羽璇');

UPDATE users SET full_name = '范宗佑'
WHERE full_name IS NULL AND (nickname = '阿佑' OR family_title = '阿佑' OR role = '阿佑');

UPDATE users SET full_name = '范麗芳'
WHERE full_name IS NULL AND (nickname = '媽媽' OR family_title = '媽媽' OR role = '媽媽');

COMMIT;
