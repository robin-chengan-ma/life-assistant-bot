-- 長記憶滾動摘要表，對應 docs/specs/chat-core/SPEC.md ADR-3。
-- Robin 於 2026-07-30 核准建表 SQL（含中文欄位說明）。
CREATE TABLE conversation_summaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    summary TEXT NOT NULL DEFAULT '',
    summarized_up_to_log_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE conversation_summaries IS '長記憶滾動摘要表：每位使用者一筆，對應 chat-core SPEC.md ADR-3';
COMMENT ON COLUMN conversation_summaries.id IS '內部主鍵';
COMMENT ON COLUMN conversation_summaries.user_id IS '所屬使用者，對應 users.id，一人僅一筆（UNIQUE）';
COMMENT ON COLUMN conversation_summaries.summary IS '目前的滾動式摘要內容，新對話會定期融合進來，不是逐字對話紀錄';
COMMENT ON COLUMN conversation_summaries.summarized_up_to_log_id IS '摘要已涵蓋到哪一則 conversation_logs.id，避免同一段對話被重複摘要';
COMMENT ON COLUMN conversation_summaries.updated_at IS '最後一次摘要更新時間';
