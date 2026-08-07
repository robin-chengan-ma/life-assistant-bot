-- 個人技能成長模組：每日技術摘要的收集與推播狀態（FR-22、FR-23），對應 docs/specs/robinson/SPEC.md。
-- Robin 於 2026-08-07 核准此 CREATE TABLE SQL（設計於同日經 Robin 回饋修正為「23:00 收集、
-- 隔天 08:00 推播」兩階段排程後，改用這張表取代原本規劃的 users.skill_growth_pushed_on 欄位）。
CREATE TABLE skill_growth_digests (
    id BIGSERIAL PRIMARY KEY,
    digest_date DATE NOT NULL UNIQUE,
    summary_text TEXT,
    pushed_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE skill_growth_digests IS '個人技能成長模組：每日技術摘要的收集與推播狀態（FR-22、FR-23）。固定台灣時間 23:00 收集當天 TLDR 電子報＋IThome／TechCrunch 新聞並經 Gemini 產出摘要，寫入一筆；隔天固定台灣時間 08:00 讀取「昨天」那筆資料推播給 Robin';
COMMENT ON COLUMN skill_growth_digests.digest_date IS '收集內容所屬的日期（23:00 收集當下的「今天」）；UNIQUE 確保同一天只會收集一次，避免 23:00 那個小時內 /healthz 多次觸發重複收集與重複呼叫 Gemini';
COMMENT ON COLUMN skill_growth_digests.summary_text IS 'Gemini 產出的中文重點摘要與總結分享；NULL 代表當天 TLDR 電子報／IThome／TechCrunch 三個來源皆無內容';
COMMENT ON COLUMN skill_growth_digests.pushed_on IS '這筆摘要推播給 Robin 的日期（收集隔天的 08:00）；避免同一天 08:00 那個小時內 /healthz 多次觸發重複推播；NULL 代表尚未推播';
COMMENT ON COLUMN skill_growth_digests.created_at IS '這筆收集結果建立的時間';
