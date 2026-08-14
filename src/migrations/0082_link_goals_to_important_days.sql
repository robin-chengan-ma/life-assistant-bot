ALTER TABLE body_goals
ADD COLUMN IF NOT EXISTS important_day_id BIGINT
REFERENCES important_days(id) ON DELETE SET NULL;

ALTER TABLE certificate_goals
ADD COLUMN IF NOT EXISTS important_day_id BIGINT
REFERENCES important_days(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_body_goals_important_day
ON body_goals (important_day_id) WHERE important_day_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_certificate_goals_important_day
ON certificate_goals (important_day_id) WHERE important_day_id IS NOT NULL;

COMMENT ON COLUMN body_goals.important_day_id IS
'有明確期限時自動同步的重要日子；目標達成或取消時停用事件';

COMMENT ON COLUMN certificate_goals.important_day_id IS
'有明確考試日期時自動同步的重要日子；日期清除時停用事件';

DO $$
DECLARE
    goal RECORD;
    event_id BIGINT;
BEGIN
    FOR goal IN
        SELECT id, user_id, target_description, target_date
        FROM body_goals
        WHERE target_date IS NOT NULL AND status = 'active' AND important_day_id IS NULL
    LOOP
        INSERT INTO important_days (
            owner_user_id, title, recurrence_type, event_date, event_end_date,
            is_all_day, reminder_days_before, notes, audience_mode,
            show_on_todo_calendar, is_active
        ) VALUES (
            goal.user_id, '體態目標：' || goal.target_description, 'one_time',
            goal.target_date, goal.target_date, TRUE, 1, '由體態目標自動同步',
            'self', TRUE, TRUE
        ) RETURNING id INTO event_id;
        INSERT INTO important_day_recipients (important_day_id, user_id)
        VALUES (event_id, goal.user_id) ON CONFLICT DO NOTHING;
        UPDATE body_goals SET important_day_id = event_id WHERE id = goal.id;
    END LOOP;

    FOR goal IN
        SELECT id, user_id, exam_type, target_score, target_date
        FROM certificate_goals
        WHERE target_date IS NOT NULL AND important_day_id IS NULL
    LOOP
        INSERT INTO important_days (
            owner_user_id, title, recurrence_type, event_date, event_end_date,
            is_all_day, reminder_days_before, notes, audience_mode,
            show_on_todo_calendar, is_active
        ) VALUES (
            goal.user_id,
            goal.exam_type || ' 考試目標' || CASE WHEN goal.target_score IS NULL THEN '' ELSE '（目標：' || goal.target_score || '）' END,
            'one_time', goal.target_date, goal.target_date, TRUE, 1,
            '由考試／證照目標自動同步', 'self', TRUE, TRUE
        ) RETURNING id INTO event_id;
        INSERT INTO important_day_recipients (important_day_id, user_id)
        VALUES (event_id, goal.user_id) ON CONFLICT DO NOTHING;
        UPDATE certificate_goals SET important_day_id = event_id WHERE id = goal.id;
    END LOOP;
END $$;
