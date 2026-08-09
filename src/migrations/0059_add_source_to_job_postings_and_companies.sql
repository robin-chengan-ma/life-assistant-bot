-- Step 4.3（FR-39、FR-40，見 docs/specs/robinson/SPEC.md ADR-27）：外部管道職缺（LinkedIn／Cake
-- 等）與 104 職缺共用同一張 job_postings／job_companies，用 source 欄位區分來源，取代原本
-- 「外部職缺另建獨立表」的提案（Robin 指出應以擴充性為優先，見 ADR-27 決策 5）。統一表之後，
-- 外部職缺可直接沿用既有 FR-37／FR-38a 評分與排名邏輯，不需要另外開發一套批次流程。
-- Robin 於 2026-08-09 核准此 ALTER TABLE SQL。
ALTER TABLE job_postings ADD COLUMN source TEXT NOT NULL DEFAULT '104';
ALTER TABLE job_companies ADD COLUMN source TEXT NOT NULL DEFAULT '104';

COMMENT ON COLUMN job_postings.source IS '職缺來源：104（爬蟲）／linkedin／cake 等，預設 104，見 ADR-27 決策 5';
COMMENT ON COLUMN job_companies.source IS '公司來源，同 job_postings.source，見 ADR-27 決策 5';
COMMENT ON COLUMN job_postings.job_id_104 IS '職缺唯一識別碼；104 來源為官方職缺 ID，其他來源為系統配發的合成 ID（格式 EXT-<內部序號>），見 ADR-27 決策 5';
COMMENT ON COLUMN job_companies.company_id_104 IS '公司唯一識別碼；104 來源為官方公司 ID，其他來源為系統配發的合成 ID，見 ADR-27 決策 5';
