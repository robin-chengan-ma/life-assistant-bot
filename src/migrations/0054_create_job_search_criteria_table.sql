-- Step 4.1（FR-33，見 docs/specs/robinson/SPEC.md ADR-24 決策 3）：求職搜尋條件表，支援同時存
-- 多組條件（不限單組覆蓋），每組各自獨立生效，每週排程對每組條件各自送出查詢。
-- Robin 於 2026-08-09 核准此 CREATE TABLE SQL。
CREATE TABLE job_search_criteria (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    keyword TEXT NOT NULL,
    region TEXT,
    salary_min INT,
    salary_max INT,
    industry TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_search_criteria_user_id ON job_search_criteria (user_id);

COMMENT ON TABLE job_search_criteria IS 'Step 4.1：求職搜尋條件（FR-33），一位使用者可同時存多組，各自獨立生效';
COMMENT ON COLUMN job_search_criteria.keyword IS '關鍵字，104 職缺搜尋 API 必要參數';
COMMENT ON COLUMN job_search_criteria.region IS '地區，允許 NULL 代表不限地區';
COMMENT ON COLUMN job_search_criteria.salary_min IS '薪資下限，允許 NULL 代表不限';
COMMENT ON COLUMN job_search_criteria.salary_max IS '薪資上限，允許 NULL 代表不限';
COMMENT ON COLUMN job_search_criteria.industry IS '產業別，允許 NULL 代表不限';
