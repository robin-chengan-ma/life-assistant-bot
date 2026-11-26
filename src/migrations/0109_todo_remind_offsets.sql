-- 2026-11-26（待辦事項提前提醒，見 docs/ADR/discuss/robinson.md）：Robin 要求待辦事項的提前
-- 提醒邏輯跟生日設定一模一樣（可複選「14／7／3／當天」天前推播），但不需要推播對象選擇——待辦
-- 一律只推給建立者本人（僅限自己），不做 audience_mode/audience_user_ids 那一套。
--
-- 待辦事項是一次性（非每年重複）事件，不像生日有「年份」概念，所以不能沿用
-- `important_notifications_log`（以 notification_key + year 去重）這套年度去重機制；改成直接在
-- todos 這張表自己記錄「這一筆待辦、哪些 offset 已經推播過」：
-- `reminded_offsets_sent INTEGER[] NOT NULL DEFAULT '{}'`，取代舊的單一時間戳 `reminded_sent_at`
-- （已確認 `reminded_sent_at` 純粹是內部去重用途，沒有任何 API/Mobile 端讀取，可以安全汰換）。
--
-- 既有資料預設 `remind_offsets = '{0}'`（只在當天推播，等同目前行為，不改變既有使用者體感）。

BEGIN;

ALTER TABLE todos
ADD COLUMN IF NOT EXISTS remind_offsets INTEGER[] NOT NULL DEFAULT '{0}';

ALTER TABLE todos
ADD COLUMN IF NOT EXISTS reminded_offsets_sent INTEGER[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN todos.remind_offsets IS
'提前提醒天數複選，只允許 {0,3,7,14} 的非空子集合；0=當天。待辦一律僅推播給建立者本人';

COMMENT ON COLUMN todos.reminded_offsets_sent IS
'這筆待辦已經推播過的 offset 清單，取代舊的 reminded_sent_at；待辦是一次性事件，不像生日有年度去重需求';

ALTER TABLE todos DROP COLUMN IF EXISTS reminded_sent_at;

COMMIT;
