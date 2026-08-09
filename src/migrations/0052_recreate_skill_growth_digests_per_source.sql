-- 個人技能成長模組：每日技術摘要改成「一天多筆、一筆一個來源管道」的正規化設計，
-- 對應 docs/specs/robinson/SPEC.md FR-22、FR-23（Step 3.1），2026-08-08 生產環境回饋修正，見 ADR-25。
-- Robin 回報現有合併格式（三個來源塞進單一 summary_text）無法分辨哪個來源當天有無內容，
-- 也希望新增來源時不用再改 schema；Robin 核准直接砍掉重建（原表僅有 1 筆資料，重建成本可忽略）。
DROP TABLE IF EXISTS skill_growth_digests;

CREATE TABLE skill_growth_digests (
    id BIGSERIAL PRIMARY KEY,
    digest_date DATE NOT NULL,
    source TEXT,
    summary_text TEXT,
    pushed_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (digest_date, source)
);

COMMENT ON TABLE skill_growth_digests IS '個人技能成長模組：每日技術摘要的收集與推播狀態（FR-22、FR-23）。一天最多三筆，一筆對應一個來源管道（tldr／ithome／techcrunch）；固定台灣時間 23:00 各來源各自收集並產出精簡總結，隔天固定台灣時間 08:00 讀取「昨天」那幾筆資料組成三行式訊息推播給 Robin';
COMMENT ON COLUMN skill_growth_digests.digest_date IS '收集內容所屬的日期（23:00 收集當下的「今天」）';
COMMENT ON COLUMN skill_growth_digests.source IS '這筆摘要屬於哪個技術情報管道：tldr／ithome／techcrunch，未來新增管道只需要寫入新的 source 值，不需要改 schema；NULL 保留給「當天完全沒有任何一筆收集結果」時的去重標記列（見 pushed_on 說明）';
COMMENT ON COLUMN skill_growth_digests.summary_text IS '這個管道當天的精簡總結（100 字內，只給重點結論）；「今日無內容」代表該來源當天確實沒有抓到任何內容（已完成收集但真的沒東西），跟「完全沒有這個 source 的列」（收集當下服務不可用）是兩種不同情境';
COMMENT ON COLUMN skill_growth_digests.pushed_on IS '這筆摘要推播給 Robin 的日期（收集隔天的 08:00）；同一天收集到的幾筆一起標記，避免 08:00 那個小時內 /healthz 多次觸發重複推播；NULL 代表尚未推播';
COMMENT ON COLUMN skill_growth_digests.created_at IS '這筆收集結果建立的時間';
