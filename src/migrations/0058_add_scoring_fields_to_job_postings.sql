-- Step 4.2（FR-37、FR-38，見 docs/specs/robinson/SPEC.md ADR-26）：Gemini 契合度評分＋技能缺口
-- 分析所需的職缺欄位。刻意不加 `rank` 欄位——FR-38a 要求「全庫排名」與「本週新職缺排名」兩種
-- 排名同時存在，一個職缺在兩種排名裡的名次不同，存成單一欄位語意衝突；排名改在產生 Excel 的
-- 當下依 `score` 動態計算，不持久化。Robin 於 2026-08-09 核准此 ALTER TABLE SQL。
ALTER TABLE job_postings ADD COLUMN score NUMERIC(5,2);
ALTER TABLE job_postings ADD COLUMN recommend_reason TEXT;
ALTER TABLE job_postings ADD COLUMN skill_gap_note TEXT;
ALTER TABLE job_postings ADD COLUMN is_unliked BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN job_postings.score IS 'FR-37：Gemini 契合度評分（0～100），尚未評分過的職缺（例如所屬公司背景還沒回填）維持 NULL';
COMMENT ON COLUMN job_postings.recommend_reason IS 'FR-37：Gemini 針對這筆職缺產生的推薦原因文字，隨 score 一起更新';
COMMENT ON COLUMN job_postings.skill_gap_note IS 'FR-38：Gemini 針對這筆職缺產生的技能缺口說明，隨 score 一起更新';
COMMENT ON COLUMN job_postings.is_unliked IS 'FR-38d：Robin 於推薦 Excel 人工標記「不喜歡」後回填，FR-38a 排名時排除 is_unliked = TRUE 的職缺，預設 FALSE（尚未標記＝視為喜歡）';
