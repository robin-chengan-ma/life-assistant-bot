-- 2026-11-26（生日多選提前提醒，見 docs/ADR/discuss/robinson.md）：生日提醒原本只能在「當天」
-- 推播，Robin 反應太晚，改成可複選「14／7／3／當天」天前推播。既有資料預設 '{0}'（只在當天推
-- 播），等同目前的行為，不改變既有使用者體感；新增時 Mobile App 預設也只勾「當天」。

BEGIN;

ALTER TABLE important_days
ADD COLUMN IF NOT EXISTS remind_offsets INTEGER[] NOT NULL DEFAULT '{0}';

COMMENT ON COLUMN important_days.remind_offsets IS
'提前幾天提醒，可複選，僅允許 0/3/7/14 的子集合，至少一個；0 代表當天才提醒';

COMMIT;
