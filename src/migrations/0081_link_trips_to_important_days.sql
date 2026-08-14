-- FR-74b：旅遊行程與一次性重要日子穩定連動。

ALTER TABLE trips
ADD COLUMN IF NOT EXISTS sync_to_important_day BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE trips
ADD COLUMN IF NOT EXISTS important_day_id BIGINT
REFERENCES important_days(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_trips_important_day
ON trips (important_day_id) WHERE important_day_id IS NOT NULL;

COMMENT ON COLUMN trips.sync_to_important_day IS '是否將有日期的行程同步為一次性重要日子';
COMMENT ON COLUMN trips.important_day_id IS 'FR-74b 連動的重要日子；行程停用時保留關聯並將事件設為 inactive';
