-- 批次3（🎯 目標追蹤新選單，FR-45a）：每日排程（統一凌晨 01:00）產生的目標摘要快取，
-- Telegram 端只顯示最新一份、不即時生成。`goal_id` 依 `goal_source` 對應不同來源表（body_goals／
-- module_goals／certificate_goals），三張表結構不同無法共用一個 FK，正確性由寫入端
-- （src/services/goal_summary_job.py，唯一寫入者）保證。Robin 於 2026-08-17 核准此
-- CREATE TABLE SQL（見 docs/ADR/discuss/robinson.md 2026-08-17「批次3 開工前 SDD 計畫確認」）。
CREATE TABLE goal_summaries (
    id BIGSERIAL PRIMARY KEY,
    goal_source TEXT NOT NULL CHECK (goal_source IN ('body_goals', 'module_goals', 'certificate_goals')),
    goal_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id),
    summary_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    generated_on DATE NOT NULL,
    UNIQUE (goal_source, goal_id, generated_on)
);

CREATE INDEX idx_goal_summaries_lookup ON goal_summaries (goal_source, goal_id, generated_on DESC);

COMMENT ON TABLE goal_summaries IS '🎯 目標追蹤新選單（FR-45a）每日排程快取的目標摘要，只保留寫入紀錄、不主動清舊資料，查詢一律取 generated_on 最新一筆';
COMMENT ON COLUMN goal_summaries.goal_source IS '目標來源表：body_goals（體態/運動/飲食）／module_goals（記帳/收藏清單）／certificate_goals（考試）';
COMMENT ON COLUMN goal_summaries.goal_id IS '對應來源表的 id，不設 FK（三張來源表結構不同無法共用），正確性由 goal_summary_job.py 保證';
COMMENT ON COLUMN goal_summaries.summary_text IS '依「過去一週」「過去一個月」紀錄生成的建議與方向、距離截止日還有多久（無期限目標不含這段）、加油打氣文字，整段存成一個字串，Telegram 端直接顯示';
COMMENT ON COLUMN goal_summaries.generated_on IS '台灣時區日期，UNIQUE 去重鍵之一，確保同一小時內 /healthz 被 cron-job.org 打好幾次也不會重複產生';
