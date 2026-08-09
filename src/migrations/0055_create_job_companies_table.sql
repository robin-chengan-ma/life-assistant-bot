-- Step 4.1（FR-35，見 docs/specs/robinson/SPEC.md ADR-24 決策 1）：104 公司背景資料表，公司背景改採
-- Email＋CSV＋Google Drive 人力協作機制回填（不使用 Gemini Web Search，該能力已因 grounding 失效被
-- 移除，見 chat-core SPEC.md ADR-5）。Robin 於 2026-08-09 核准此 CREATE TABLE SQL。
CREATE TABLE job_companies (
    id BIGSERIAL PRIMARY KEY,
    company_id_104 TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    region TEXT,
    industry TEXT,
    background TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE job_companies IS 'Step 4.1：104 公司背景資料（FR-35），background 留空代表尚待 Robin 人工查詢回填（FR-35a～FR-35e）';
COMMENT ON COLUMN job_companies.company_id_104 IS '104 公司 ID，作為是否已建檔的判斷鍵值與 job_postings 外鍵';
COMMENT ON COLUMN job_companies.background IS '公司背景描述，NULL 代表尚未回填；FR-35a 用「是否為 NULL」判斷這批公司是否需要走 Email/CSV 協作流程';
