-- 體態管理模組：體態目標表（身高體重/運動/飲食三個子功能共用一張），對應
-- docs/specs/robinson/SPEC.md FR-46～FR-48。Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
CREATE TABLE body_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    goal_type TEXT NOT NULL CHECK (goal_type IN ('weight', 'exercise', 'diet')),
    target_description TEXT NOT NULL,
    target_value NUMERIC(6,2),
    baseline_value NUMERIC(6,2),
    target_date DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'achieved', 'cancelled')),
    achieved_notified BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_body_goals_user_id ON body_goals (user_id);

COMMENT ON TABLE body_goals IS '體態目標表：身高體重/運動/飲食三個子功能共用一張，用 goal_type 區分（比照 budget_overrides 精神），FR-45 三種預警情境的判斷依據';
COMMENT ON COLUMN body_goals.id IS '內部主鍵';
COMMENT ON COLUMN body_goals.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN body_goals.goal_type IS '目標類型：weight=體重, exercise=運動, diet=飲食';
COMMENT ON COLUMN body_goals.target_description IS '目標的自由文字敘述，用於回覆展示（例如「三個月內瘦到 60 KG」）';
COMMENT ON COLUMN body_goals.target_value IS '目標數值：weight 為目標體重(kg)，exercise 為目標累積運動分鐘數；diet 目標太主觀無法量化，此欄位為 NULL';
COMMENT ON COLUMN body_goals.baseline_value IS '設定目標當下的基準值，只有 goal_type=weight 使用，用來判斷要瘦還是要增（見 src/bot/body.py check_weight_goal_achieved()）';
COMMENT ON COLUMN body_goals.target_date IS '預計完成期限，選填；有值時才會觸發 FR-45 期限將近提醒';
COMMENT ON COLUMN body_goals.status IS '目標狀態：active=進行中, achieved=已達成, cancelled=已取消';
COMMENT ON COLUMN body_goals.achieved_notified IS '是否已推播過達成通知，避免重複推播';
COMMENT ON COLUMN body_goals.deadline_reminder_sent IS '是否已推播過期限將近提醒（每個目標最多推播一次）';
COMMENT ON COLUMN body_goals.created_at IS '這筆目標建立的時間，運動目標的累積分鐘數從這個時間點（換算台灣時區日期）開始計算';
COMMENT ON COLUMN body_goals.updated_at IS '最後變更時間';
