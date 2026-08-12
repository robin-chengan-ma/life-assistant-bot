-- Mobile App 探索事件照片索引。Robin 於 2026-08-12 核准。
CREATE TABLE exploration_photos (
    id BIGSERIAL PRIMARY KEY,
    exploration_event_id BIGINT NOT NULL REFERENCES exploration_events(id) ON DELETE CASCADE,
    storage_url TEXT NOT NULL,
    caption TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_exploration_photos_event
ON exploration_photos (exploration_event_id, sort_order);

COMMENT ON TABLE exploration_photos IS '探索照片索引；只保存雲端位置，不把圖片內容寫入資料庫';
