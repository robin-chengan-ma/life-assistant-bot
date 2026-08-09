-- Step 4.1（FR-34，見 docs/specs/robinson/SPEC.md ADR-24 決策 4）：104 職缺資料表，兩階段爬蟲
-- （列表 API 抓清單 → 逐筆打詳情頁補齊完整內容）寫入本表；is_unliked／is_closed／score／rank 等
-- Step 4.2（FR-37／FR-38）用欄位不在本次建立，待 Step 4.2 開工時另開 migration 新增，避免現在猜錯
-- 需求。applicant_count／source_updated_at 是否能從 104 API 取得目前無實測依據，先開欄位允許 NULL，
-- 若確認抓不到則永遠是 NULL，不影響其餘邏輯。Robin 於 2026-08-09 核准此 CREATE TABLE SQL。
CREATE TABLE job_postings (
    id BIGSERIAL PRIMARY KEY,
    job_id_104 TEXT NOT NULL UNIQUE,
    company_id_104 TEXT NOT NULL REFERENCES job_companies (company_id_104),
    title TEXT NOT NULL,
    region TEXT,
    url TEXT NOT NULL,
    salary_min INT,
    salary_max INT,
    content TEXT,
    required_years_experience NUMERIC(4,1),
    applicant_count INT,
    source_updated_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_crawled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_postings_company_id_104 ON job_postings (company_id_104);

COMMENT ON TABLE job_postings IS 'Step 4.1：104 職缺資料（FR-34），以 job_id_104 為 ETL 去重鍵值（FR-34d），已存在則 UPDATE 而非新增';
COMMENT ON COLUMN job_postings.job_id_104 IS '104 職缺唯一 ID，ETL 去重鍵值';
COMMENT ON COLUMN job_postings.content IS '職缺內容／應徵條件／福利，來自 FR-34a 兩階段爬蟲的詳情頁補齊結果';
COMMENT ON COLUMN job_postings.applicant_count IS '應徵人數，若 104 API／頁面無法取得則維持 NULL（FR-37b 評分時略過此維度）';
COMMENT ON COLUMN job_postings.source_updated_at IS '104 職缺本身的更新時間，若 104 API／頁面無法取得則維持 NULL（FR-37b 評分時略過此維度）';
COMMENT ON COLUMN job_postings.first_seen_at IS '這筆職缺第一次被爬到入庫的時間，供 FR-38a「本週新職缺排名」判斷依據';
COMMENT ON COLUMN job_postings.last_crawled_at IS '最後一次被爬蟲更新的時間，每週排程重新爬到既有職缺時更新此欄位';
