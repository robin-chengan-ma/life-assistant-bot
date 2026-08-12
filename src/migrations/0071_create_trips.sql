-- Mobile App 探索地圖：旅遊行程容器。Robin 於 2026-08-12 核准。
CREATE TABLE trips (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    cover_image_url TEXT,
    companions TEXT,
    budget_amount NUMERIC(12,2) CHECK (budget_amount >= 0),
    currency_code TEXT NOT NULL DEFAULT 'TWD',
    status TEXT NOT NULL DEFAULT 'planning'
        CHECK (status IN ('planning', 'ongoing', 'completed', 'cancelled')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date >= start_date)
);

CREATE INDEX idx_trips_user_dates ON trips (user_id, start_date, end_date);

COMMENT ON TABLE trips IS 'Mobile App 旅遊行程：整合每日行程、探索事件與既有記帳資料';
COMMENT ON COLUMN trips.companions IS '同行者自由文字，寫入前須套用既有個資遮蔽';
COMMENT ON COLUMN trips.budget_amount IS '整趟旅遊預算；實際開銷由 transactions.trip_id 彙總，不重複儲存';
