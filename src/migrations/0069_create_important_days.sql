CREATE TABLE important_days (
    id BIGSERIAL PRIMARY KEY,
    owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    recurrence_type TEXT NOT NULL CHECK (recurrence_type IN ('fixed_annual', 'flexible_annual', 'one_time')),
    event_date DATE,
    event_month SMALLINT CHECK (event_month BETWEEN 1 AND 12),
    event_day SMALLINT CHECK (event_day BETWEEN 1 AND 31),
    event_time TIME,
    is_all_day BOOLEAN NOT NULL DEFAULT TRUE,
    reminder_days_before INTEGER NOT NULL DEFAULT 0 CHECK (reminder_days_before BETWEEN 0 AND 365),
    notes TEXT,
    audience_mode TEXT NOT NULL DEFAULT 'self' CHECK (audience_mode IN ('self', 'specific', 'all')),
    show_on_todo_calendar BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (recurrence_type = 'fixed_annual' AND event_date IS NULL AND event_month IS NOT NULL AND event_day IS NOT NULL)
        OR (recurrence_type = 'flexible_annual' AND event_date IS NULL AND event_month IS NULL AND event_day IS NULL)
        OR (recurrence_type = 'one_time' AND event_date IS NOT NULL AND event_month IS NULL AND event_day IS NULL)
    )
);

CREATE TABLE important_day_occurrences (
    id BIGSERIAL PRIMARY KEY,
    important_day_id BIGINT NOT NULL REFERENCES important_days(id) ON DELETE CASCADE,
    occurrence_year INTEGER NOT NULL,
    occurrence_date DATE NOT NULL,
    UNIQUE (important_day_id, occurrence_year)
);

CREATE TABLE important_day_recipients (
    important_day_id BIGINT NOT NULL REFERENCES important_days(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (important_day_id, user_id)
);

CREATE INDEX idx_important_days_owner ON important_days(owner_user_id);
CREATE INDEX idx_important_day_occurrences_date ON important_day_occurrences(occurrence_date);
CREATE INDEX idx_important_day_recipients_user ON important_day_recipients(user_id);

COMMENT ON TABLE important_days IS 'Mobile App 重要日子事件範本及通知對象規則';
COMMENT ON TABLE important_day_occurrences IS '每年日期不同事件的年度實際日期';
COMMENT ON TABLE important_day_recipients IS '指定家人通知對象；self/all 模式不需寫入';
