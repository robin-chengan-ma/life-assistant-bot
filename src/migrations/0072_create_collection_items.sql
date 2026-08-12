-- Mobile App 收藏清單。Robin 於 2026-08-12 核准。
CREATE TABLE collection_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id BIGINT REFERENCES trips(id) ON DELETE SET NULL,
    item_type TEXT NOT NULL CHECK (item_type IN (
        'restaurant', 'attraction', 'mountain', 'accommodation', 'activity', 'other'
    )),
    title TEXT NOT NULL,
    country_code TEXT,
    country_name TEXT,
    administrative_area TEXT,
    city_name TEXT,
    address TEXT,
    latitude NUMERIC(9,6) CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(9,6) CHECK (longitude BETWEEN -180 AND 180),
    source_url TEXT,
    estimated_cost NUMERIC(12,2) CHECK (estimated_cost >= 0),
    currency_code TEXT NOT NULL DEFAULT 'TWD',
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    desired_date DATE,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'saved'
        CHECK (status IN ('saved', 'added_to_trip', 'visited', 'cancelled')),
    visited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_collection_items_user_status ON collection_items (user_id, status);
CREATE INDEX idx_collection_items_location
ON collection_items (user_id, country_code, administrative_area, city_name);

COMMENT ON TABLE collection_items IS 'Mobile App 收藏清單：尚未前往或已完成的餐廳、景點、登山、住宿與活動';
COMMENT ON COLUMN collection_items.trip_id IS '選填的規劃中旅遊行程；刪除行程只解除關聯';
