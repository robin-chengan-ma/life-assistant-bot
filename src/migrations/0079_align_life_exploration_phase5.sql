-- Phase 5：依 FR-73～FR-76a 對齊收藏、旅遊行程、探索與成果資料模型。

ALTER TABLE trips ALTER COLUMN start_date DROP NOT NULL;
ALTER TABLE trips ALTER COLUMN end_date DROP NOT NULL;
ALTER TABLE trips DROP CONSTRAINT IF EXISTS trips_status_check;
UPDATE trips SET status = 'confirmed' WHERE status = 'ongoing';
ALTER TABLE trips ADD CONSTRAINT trips_status_check
CHECK (status IN ('planning', 'confirmed', 'completed', 'cancelled'));
ALTER TABLE trips ADD COLUMN IF NOT EXISTS country_name TEXT;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS city_name TEXT;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_transport NUMERIC(12,2) CHECK (estimated_transport >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_accommodation NUMERIC(12,2) CHECK (estimated_accommodation >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_food NUMERIC(12,2) CHECK (estimated_food >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_tickets NUMERIC(12,2) CHECK (estimated_tickets >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_shopping NUMERIC(12,2) CHECK (estimated_shopping >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS estimated_other NUMERIC(12,2) CHECK (estimated_other >= 0);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE trips DROP CONSTRAINT IF EXISTS trips_check;
ALTER TABLE trips ADD CONSTRAINT trips_date_range_check
CHECK (
    (start_date IS NULL AND end_date IS NULL)
    OR (start_date IS NOT NULL AND end_date IS NOT NULL AND end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS trip_collection_items (
    id BIGSERIAL PRIMARY KEY,
    trip_id BIGINT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    collection_item_id BIGINT REFERENCES collection_items(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    visit_status TEXT NOT NULL DEFAULT 'planned'
        CHECK (visit_status IN ('planned', 'visited', 'skipped')),
    visited_event_id BIGINT REFERENCES exploration_events(id) ON DELETE SET NULL,
    title_snapshot TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trip_id, collection_item_id)
);
CREATE INDEX IF NOT EXISTS idx_trip_collection_items_trip
ON trip_collection_items (trip_id, sort_order, id);

ALTER TABLE collection_items ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_collection_items_active
ON collection_items (user_id, updated_at DESC) WHERE deleted_at IS NULL;

ALTER TABLE exploration_events ADD COLUMN IF NOT EXISTS collection_item_id BIGINT
REFERENCES collection_items(id) ON DELETE SET NULL;
ALTER TABLE exploration_events ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE exploration_events ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_exploration_events_collection
ON exploration_events (collection_item_id, start_date DESC);

ALTER TABLE user_achievements DROP CONSTRAINT IF EXISTS user_achievements_creation_source_check;
UPDATE user_achievements SET creation_source = 'suggested' WHERE creation_source = 'automatic';
ALTER TABLE user_achievements ADD CONSTRAINT user_achievements_creation_source_check
CHECK (creation_source IN ('suggested', 'manual'));
ALTER TABLE user_achievements ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'milestone';
ALTER TABLE user_achievements ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE user_achievements DROP CONSTRAINT IF EXISTS user_achievements_source_type_check;
ALTER TABLE user_achievements ADD CONSTRAINT user_achievements_source_type_check
CHECK (source_type IN (
    'trip', 'exploration', 'body_goal', 'certificate_goal', 'exercise', 'todo', 'manual'
));

CREATE TABLE IF NOT EXISTS achievement_candidates (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    candidate_key TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'body', 'exam', 'exercise', 'exploration', 'trip', 'todo'
    )),
    title TEXT NOT NULL,
    description TEXT,
    completed_on DATE NOT NULL,
    source_type TEXT NOT NULL,
    source_id BIGINT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, candidate_key)
);
CREATE INDEX IF NOT EXISTS idx_achievement_candidates_user_status
ON achievement_candidates (user_id, status, completed_on DESC);

COMMENT ON TABLE trip_collection_items IS 'FR-74：收藏與行程多對多關聯及實際造訪確認結果';
COMMENT ON TABLE achievement_candidates IS 'FR-76：系統提出、需由使用者確認或拒絕的成果候選';
COMMENT ON COLUMN trips.budget_amount IS '新台幣預估總額；可由分類預估加總或由使用者只填總額';
