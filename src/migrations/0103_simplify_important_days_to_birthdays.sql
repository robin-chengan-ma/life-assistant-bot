-- 2026-11 功能大幅精簡（Robin 明確決策）：「重要日子」改名為「生日設定」，Telegram 端只剩
-- 每年固定（國曆）月/日重複一次的生日，拿掉單次事件／浮動（農曆）日期／通知對象／備註／跟
-- 行程或目標連動等等（見 src/bot/important_days.py 檔頭欄位假設）。新增/編輯/查詢改到 Mobile App，
-- 這裡只需確保 DB 欄位符合該模組期待的最小形狀。
--
-- 既有資料保留政策（Robin 核准）：只有「國曆固定每年重複」（recurrence_type = 'fixed_annual'）
-- 的既有資料視為生日予以保留並轉換；'flexible_annual'（農曆浮動）與 'one_time'（單次事件，
-- 多半是行程／目標自動同步產生的一次性提醒，例如 0082 migration 寫入的「體態目標」「考試目標」）
-- 判斷為「不是生日」，依「既有的一次性重要日子資料如果不是生日，不在保留範圍內，可以捨棄」此一
-- 已核准規則捨棄。此假設為本次遷移唯一需要人工判斷之處，若日後發現有「假借 one_time 記錄、
-- 實際上是生日」的既有資料，不在本次轉換範圍內。
--
-- 去重用的 important_notifications_log 表本次不變動（舊的節日/行程/目標相關 notification_key
-- 會成為永遠不會再比對到的孤兒紀錄，不影響新版 `birthday_important_day_{id}` key 的比對邏輯，
-- 故不需要特別清理）。

BEGIN;

-- 只跟 important_days 相依、本次精簡後不再使用的輔助表（多組通知對象／每年實際日期快取）；
-- 新版生日用 birth_month/birth_day 即時計算，不需要這兩張表。
DROP TABLE IF EXISTS important_day_occurrences;
DROP TABLE IF EXISTS important_day_recipients;

-- 捨棄非「國曆固定每年重複」的既有資料（農曆浮動／單次事件，詳見檔頭說明）。
DELETE FROM important_days WHERE recurrence_type <> 'fixed_annual';

ALTER TABLE important_days RENAME COLUMN owner_user_id TO user_id;
ALTER TABLE important_days RENAME COLUMN title TO name;

ALTER TABLE important_days ADD COLUMN birth_month SMALLINT;
ALTER TABLE important_days ADD COLUMN birth_day SMALLINT;
UPDATE important_days SET birth_month = event_month, birth_day = event_day;

ALTER TABLE important_days ALTER COLUMN birth_month SET NOT NULL;
ALTER TABLE important_days ALTER COLUMN birth_day SET NOT NULL;
ALTER TABLE important_days ADD CONSTRAINT important_days_birth_month_check CHECK (birth_month BETWEEN 1 AND 12);
ALTER TABLE important_days ADD CONSTRAINT important_days_birth_day_check CHECK (birth_day BETWEEN 1 AND 31);

ALTER TABLE important_days DROP CONSTRAINT IF EXISTS important_days_check;
ALTER TABLE important_days DROP COLUMN IF EXISTS recurrence_type;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_date;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_month;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_day;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_time;
ALTER TABLE important_days DROP COLUMN IF EXISTS is_all_day;
ALTER TABLE important_days DROP COLUMN IF EXISTS reminder_days_before;
ALTER TABLE important_days DROP COLUMN IF EXISTS notes;
ALTER TABLE important_days DROP COLUMN IF EXISTS audience_mode;
ALTER TABLE important_days DROP COLUMN IF EXISTS show_on_todo_calendar;
ALTER TABLE important_days DROP COLUMN IF EXISTS is_active;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_end_date;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_end_month;
ALTER TABLE important_days DROP COLUMN IF EXISTS event_end_day;

COMMENT ON TABLE important_days IS '生日設定：每年固定（國曆）月/日重複一次的生日（2026-11 精簡，原「重要日子」）';
COMMENT ON COLUMN important_days.user_id IS '建立者（owner），對應 users.id（原 owner_user_id）';
COMMENT ON COLUMN important_days.name IS '誰的生日，例如「媽媽」（原 title）';
COMMENT ON COLUMN important_days.birth_month IS '國曆月份，1~12';
COMMENT ON COLUMN important_days.birth_day IS '國曆日期，1~31（依月份有效範圍，未額外檢查月份天數上限）';

COMMIT;
