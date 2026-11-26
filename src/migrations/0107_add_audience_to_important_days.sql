-- 2026-11-26（生日推播對象可選，見 docs/ADR/discuss/robinson.md）：生日推播原本固定只推給建立者
-- 本人，Robin 要求能選擇推播對象：僅限自己／自行選擇特定人／所有人都推播。既有資料預設
-- 'self'（只推給建立者本人），等同目前的行為，不改變既有使用者體感。

BEGIN;

ALTER TABLE important_days
ADD COLUMN IF NOT EXISTS audience_mode TEXT NOT NULL DEFAULT 'self';

ALTER TABLE important_days
ADD CONSTRAINT important_days_audience_mode_check
CHECK (audience_mode IN ('self', 'selected', 'everyone'));

ALTER TABLE important_days
ADD COLUMN IF NOT EXISTS audience_user_ids INTEGER[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN important_days.audience_mode IS
'生日推播對象：self=僅限自己、selected=自行選擇的名單、everyone=所有人都推播';

COMMENT ON COLUMN important_days.audience_user_ids IS
'audience_mode=selected 時才有意義，列出要推播的 users.id；其餘模式留空陣列';

COMMIT;
