-- Step 4.3（FR-39c，見 docs/specs/robinson/SPEC.md ADR-27）：應徵狀態歷程記錄，append-only
-- （每次狀態變更新增一筆，不覆蓋既有紀錄），保留完整時間軸供未來統計「平均幾天收到回覆」之類
-- 的成效指標；同一 job_id_104 的「目前狀態」＝最新一筆（依 created_at 排序）。
-- Robin 於 2026-08-09 核准此 CREATE TABLE SQL。
CREATE TABLE job_applications (
    id BIGSERIAL PRIMARY KEY,
    job_id_104 TEXT NOT NULL REFERENCES job_postings (job_id_104),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_applications_job_id_104 ON job_applications (job_id_104);

COMMENT ON TABLE job_applications IS 'FR-39c：應徵狀態歷程記錄，每次狀態變更新增一筆（不覆蓋），保留完整時間軸；同一 job_id_104 的目前狀態＝最新一筆';
COMMENT ON COLUMN job_applications.status IS '應徵狀態：applied／interview／offer／rejected 四種，任意狀態可直接設定，不強制順序（見 FR-39b）';
