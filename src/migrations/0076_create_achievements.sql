-- Mobile App 成果展示。Robin 於 2026-08-12 核准。
CREATE TABLE achievements (
    id BIGSERIAL PRIMARY KEY,
    achievement_code TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('goal', 'exploration', 'milestone')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    icon_name TEXT,
    threshold_value INTEGER CHECK (threshold_value > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_achievements (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_id BIGINT REFERENCES achievements(id) ON DELETE SET NULL,
    creation_source TEXT NOT NULL CHECK (creation_source IN ('automatic', 'manual')),
    title TEXT NOT NULL,
    description TEXT,
    unlocked_on DATE NOT NULL,
    cover_image_url TEXT,
    source_type TEXT CHECK (source_type IN (
        'trip', 'exploration', 'body_goal', 'certificate_goal', 'manual'
    )),
    source_id BIGINT,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_user_automatic_achievement
ON user_achievements (user_id, achievement_id)
WHERE achievement_id IS NOT NULL AND creation_source = 'automatic';
CREATE INDEX idx_user_achievements_display
ON user_achievements (user_id, is_hidden, unlocked_on DESC);

COMMENT ON TABLE achievements IS '系統可自動判斷的成果定義';
COMMENT ON TABLE user_achievements IS '使用者成果卡片，包含自動解鎖與手動建立的里程碑';
COMMENT ON COLUMN user_achievements.source_id IS '跨模組來源 ID；來源所有權由 Service 驗證，不建立多型外鍵';
