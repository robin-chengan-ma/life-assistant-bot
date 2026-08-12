-- Mobile App 探索地圖事件。Robin 於 2026-08-12 核准。
CREATE TABLE exploration_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id BIGINT REFERENCES trips(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'restaurant', 'attraction', 'mountain', 'accommodation', 'activity', 'other'
    )),
    title TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    country_code TEXT,
    country_name TEXT,
    administrative_area TEXT,
    city_name TEXT,
    address TEXT,
    latitude NUMERIC(9,6) CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(9,6) CHECK (longitude BETWEEN -180 AND 180),
    rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
    companions TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date >= start_date)
);

CREATE INDEX idx_exploration_events_user_dates
ON exploration_events (user_id, start_date, end_date);
CREATE INDEX idx_exploration_events_location
ON exploration_events (user_id, country_code, administrative_area, city_name);

COMMENT ON TABLE exploration_events IS 'Mobile App 探索地圖實際事件；同一地點可造訪多次，不設定地點唯一約束';
