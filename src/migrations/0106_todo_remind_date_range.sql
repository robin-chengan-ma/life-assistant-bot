-- 2026-11-26（待辦改日期區間＋行事曆，見 docs/ADR/discuss/robinson.md）：待辦事項原本只能設定
-- 單一提醒時間點（`remind_at`，固定 09:00），改成可選「日期區間」＋行事曆 UI，推播固定改成
-- 第一天早上 08:30。既有資料安全回填：先新增 `remind_start_date`，用既有 `remind_at` 的台灣
-- 日期回填，再新增 `remind_end_date`（單日待辦＝跟開始日期相同），最後才移除 `remind_at`，
-- 採三段式寫法而不是直接改欄位型別，避免中途失敗留下半套 schema。

BEGIN;

ALTER TABLE todos ADD COLUMN remind_start_date DATE;
UPDATE todos SET remind_start_date = DATE(remind_at AT TIME ZONE 'Asia/Taipei');
ALTER TABLE todos ALTER COLUMN remind_start_date SET NOT NULL;

ALTER TABLE todos ADD COLUMN remind_end_date DATE;
UPDATE todos SET remind_end_date = remind_start_date;
ALTER TABLE todos ALTER COLUMN remind_end_date SET NOT NULL;

ALTER TABLE todos DROP COLUMN remind_at;

CREATE INDEX idx_todos_remind_start_date ON todos (remind_start_date);

COMMENT ON COLUMN todos.remind_start_date IS '提醒區間的第一天（單日待辦時等於 remind_end_date），推播固定在這天台灣時間 08:30 觸發';
COMMENT ON COLUMN todos.remind_end_date IS '提醒區間的最後一天（單日待辦時等於 remind_start_date），僅用於顯示，不影響推播時機';

COMMIT;
