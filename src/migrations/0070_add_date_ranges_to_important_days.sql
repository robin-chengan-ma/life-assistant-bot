ALTER TABLE important_days ADD COLUMN event_end_date DATE;
ALTER TABLE important_days ADD COLUMN event_end_month SMALLINT CHECK (event_end_month BETWEEN 1 AND 12);
ALTER TABLE important_days ADD COLUMN event_end_day SMALLINT CHECK (event_end_day BETWEEN 1 AND 31);
ALTER TABLE important_day_occurrences ADD COLUMN occurrence_end_date DATE;

UPDATE important_days SET event_end_date = event_date, event_end_month = event_month, event_end_day = event_day;
UPDATE important_day_occurrences SET occurrence_end_date = occurrence_date;

ALTER TABLE important_days DROP CONSTRAINT important_days_check;
ALTER TABLE important_days ADD CHECK (
    (recurrence_type = 'fixed_annual' AND event_date IS NULL AND event_month IS NOT NULL AND event_day IS NOT NULL
        AND event_end_date IS NULL AND event_end_month IS NOT NULL AND event_end_day IS NOT NULL)
    OR (recurrence_type = 'flexible_annual' AND event_date IS NULL AND event_month IS NULL AND event_day IS NULL
        AND event_end_date IS NULL AND event_end_month IS NULL AND event_end_day IS NULL)
    OR (recurrence_type = 'one_time' AND event_date IS NOT NULL AND event_month IS NULL AND event_day IS NULL
        AND event_end_date IS NOT NULL AND event_end_month IS NULL AND event_end_day IS NULL)
);
