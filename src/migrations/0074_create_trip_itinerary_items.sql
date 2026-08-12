-- Mobile App 旅遊每日行程。Robin 於 2026-08-12 核准。
CREATE TABLE trip_itinerary_items (
    id BIGSERIAL PRIMARY KEY,
    trip_id BIGINT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    collection_item_id BIGINT REFERENCES collection_items(id) ON DELETE SET NULL,
    exploration_event_id BIGINT REFERENCES exploration_events(id) ON DELETE SET NULL,
    item_type TEXT NOT NULL CHECK (item_type IN (
        'flight', 'transport', 'accommodation', 'restaurant', 'attraction',
        'mountain', 'activity', 'other'
    )),
    title TEXT NOT NULL,
    itinerary_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    country_name TEXT,
    city_name TEXT,
    address TEXT,
    latitude NUMERIC(9,6) CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(9,6) CHECK (longitude BETWEEN -180 AND 180),
    booking_reference TEXT,
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'completed', 'skipped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (start_time IS NULL OR end_time IS NULL OR end_time >= start_time)
);

CREATE INDEX idx_trip_itinerary_items_trip_date
ON trip_itinerary_items (trip_id, itinerary_date, sort_order);

COMMENT ON TABLE trip_itinerary_items IS '旅遊行程中的每日項目；日期是否落在行程範圍由 Service 驗證';
