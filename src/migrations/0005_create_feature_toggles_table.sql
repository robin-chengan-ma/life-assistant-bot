CREATE TABLE feature_toggles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    feature_key TEXT NOT NULL CHECK (feature_key IN (
        'todo', 'job_search', 'budget', 'body', 'skill_growth',
        'mood_journal', 'friend_mode', 'important_notify'
    )),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, feature_key)
);

COMMENT ON TABLE feature_toggles IS '功能開關表：對應 FR-2，每位使用者各模組獨立開關';
COMMENT ON COLUMN feature_toggles.id IS '內部主鍵';
COMMENT ON COLUMN feature_toggles.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN feature_toggles.feature_key IS '功能代號：todo=待辦, job_search=求職, budget=記帳, body=體態管理, skill_growth=技能成長, mood_journal=心情小記, friend_mode=好友模式, important_notify=重要通知';
COMMENT ON COLUMN feature_toggles.is_enabled IS '是否開啟此功能';
COMMENT ON COLUMN feature_toggles.updated_at IS '最後變更時間';
