-- 批次3（六模組目標泛化，FR-45a）：記帳／收藏清單兩個新模組的目標表，用 module_key 區分
-- （比照 body_goals 用 goal_type 區分的精神）。體態/運動/飲食沿用既有 body_goals，考試沿用既有
-- certificate_goals，這兩個舊表不搬進來，避免動到已上線功能。Robin 於 2026-08-17 核准此
-- CREATE TABLE SQL（見 docs/ADR/discuss/robinson.md 2026-08-17「批次3 開工前 SDD 計畫確認」）。
CREATE TABLE module_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    module_key TEXT NOT NULL CHECK (module_key IN ('finance', 'collections')),
    target_description TEXT NOT NULL,
    target_value NUMERIC(12,2),
    target_unit TEXT,
    baseline_value NUMERIC(12,2),
    target_date DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'achieved', 'cancelled')),
    achieved_notified BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    important_day_id BIGINT REFERENCES important_days(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_module_goals_user_id ON module_goals (user_id);
CREATE INDEX idx_module_goals_important_day ON module_goals (important_day_id) WHERE important_day_id IS NOT NULL;

COMMENT ON TABLE module_goals IS '批次3新增模組（記帳／收藏清單）的目標表，用 module_key 區分，比照 body_goals 精神；體態/運動/飲食/考試沿用各自既有的 body_goals／certificate_goals，不搬進這張表';
COMMENT ON COLUMN module_goals.module_key IS '目標所屬模組：finance=記帳（儲蓄/淨結餘目標）, collections=收藏清單（清單完成度目標）';
COMMENT ON COLUMN module_goals.target_description IS '目標的自由文字敘述，用於回覆展示，永遠保留（方案A：LLM 解析失敗時的 fallback 顯示來源）';
COMMENT ON COLUMN module_goals.target_value IS '方案A（FR-45a）結構化抽出的目標數值；finance 為淨結餘變化金額(TWD)，collections 為新完成收藏項目數；LLM 抽不出來時為 NULL，此目標退化為純文字目標，只能手動標記完成';
COMMENT ON COLUMN module_goals.target_unit IS '目標數值的單位；finance 固定 TWD，collections 固定 count；target_value 為 NULL 時本欄也是 NULL';
COMMENT ON COLUMN module_goals.baseline_value IS '設定目標當下的基準值；finance 固定為 0（達成判斷用「目標建立後累計淨結餘變化」而非絕對值，見 src/bot/goals.py）；collections 為建立當下已標記 visited 的收藏項目數';
COMMENT ON COLUMN module_goals.target_date IS '預計完成期限，選填';
COMMENT ON COLUMN module_goals.status IS '目標狀態：active=進行中, achieved=已達成, cancelled=已取消';
COMMENT ON COLUMN module_goals.achieved_notified IS '是否已推播過達成通知，避免重複推播';
COMMENT ON COLUMN module_goals.deadline_reminder_sent IS '是否已推播過期限將近提醒（每個目標最多推播一次）';
COMMENT ON COLUMN module_goals.created_at IS '這筆目標建立的時間，finance 目標的累計淨結餘變化從這個時間點（換算台灣時區日期）開始計算';
COMMENT ON COLUMN module_goals.updated_at IS '最後變更時間';
COMMENT ON COLUMN module_goals.important_day_id IS '有明確期限時自動同步的重要日子；目標達成或取消時停用事件，比照 body_goals.important_day_id（0082 migration）精神';
