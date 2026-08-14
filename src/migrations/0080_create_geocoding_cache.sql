-- FR-75：快取 Nominatim 地址定位結果，避免重複呼叫公開服務。

CREATE TABLE IF NOT EXISTS geocoding_cache (
    id BIGSERIAL PRIMARY KEY,
    query_key TEXT NOT NULL UNIQUE,
    query_text TEXT NOT NULL,
    latitude NUMERIC(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'nominatim'
        CHECK (provider IN ('nominatim')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geocoding_cache_updated_at
ON geocoding_cache (updated_at DESC);

COMMENT ON TABLE geocoding_cache IS 'FR-75：地址轉座標快取，降低 Nominatim 公開服務負載';
