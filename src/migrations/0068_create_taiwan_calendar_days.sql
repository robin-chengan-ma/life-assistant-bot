CREATE TABLE taiwan_calendar_days (
    calendar_date DATE PRIMARY KEY,
    year INTEGER NOT NULL,
    name TEXT,
    is_holiday BOOLEAN NOT NULL,
    holiday_category TEXT,
    description TEXT,
    source_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_taiwan_calendar_days_year ON taiwan_calendar_days (year);

COMMENT ON TABLE taiwan_calendar_days IS 'Mobile 待辦行事曆使用的政府行政機關辦公日曆年度快取';
COMMENT ON COLUMN taiwan_calendar_days.calendar_date IS '西元日期，來源為政府資料開放平臺辦公日曆 CSV';
COMMENT ON COLUMN taiwan_calendar_days.name IS '官方節日或紀念日名稱；一般週末可能為 NULL';
COMMENT ON COLUMN taiwan_calendar_days.is_holiday IS '官方資料標示是否放假';
