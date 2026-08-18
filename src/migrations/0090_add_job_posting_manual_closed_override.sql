ALTER TABLE job_postings
ADD COLUMN is_closed_manual_override BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN job_postings.is_closed_manual_override IS
'使用者手動覆寫職缺開關狀態；TRUE 時週爬蟲不得覆寫 is_closed，手動改回開啟時清回 FALSE';
