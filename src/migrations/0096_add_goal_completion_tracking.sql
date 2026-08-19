ALTER TABLE body_goals
ADD COLUMN completed_at TIMESTAMPTZ,
ADD COLUMN progress_type TEXT;

ALTER TABLE module_goals
ADD COLUMN completed_at TIMESTAMPTZ;

ALTER TABLE certificate_goals
ADD COLUMN status TEXT NOT NULL DEFAULT 'active',
ADD COLUMN completed_at TIMESTAMPTZ;

UPDATE body_goals
SET completed_at = COALESCE(updated_at, created_at, now())
WHERE status = 'achieved';

UPDATE module_goals
SET completed_at = COALESCE(updated_at, created_at, now())
WHERE status = 'achieved';

UPDATE body_goals
SET progress_type = CASE
    WHEN goal_type = 'exercise' AND target_value IS NULL THEN 'milestone'
    WHEN goal_type = 'weight'
         AND target_value IS NOT NULL
         AND baseline_value IS NOT NULL THEN 'numeric'
    WHEN goal_type = 'exercise' AND target_value IS NOT NULL THEN 'numeric'
    WHEN goal_type = 'diet'
         AND target_value IS NOT NULL
         AND target_direction IS NOT NULL THEN 'numeric'
    ELSE 'unquantified'
END;

ALTER TABLE body_goals
ALTER COLUMN progress_type SET NOT NULL,
ADD CONSTRAINT body_goals_progress_type_check
CHECK (progress_type IN ('numeric', 'milestone', 'unquantified')),
ADD CONSTRAINT body_goals_milestone_type_check
CHECK (progress_type <> 'milestone' OR goal_type = 'exercise'),
ADD CONSTRAINT body_goals_completed_at_check
CHECK (
    (status = 'achieved' AND completed_at IS NOT NULL)
    OR (status <> 'achieved' AND completed_at IS NULL)
);

ALTER TABLE module_goals
ADD CONSTRAINT module_goals_completed_at_check
CHECK (
    (status = 'achieved' AND completed_at IS NOT NULL)
    OR (status <> 'achieved' AND completed_at IS NULL)
);

ALTER TABLE certificate_goals
ADD CONSTRAINT certificate_goals_status_check
CHECK (status IN ('active', 'achieved', 'cancelled')),
ADD CONSTRAINT certificate_goals_completed_at_check
CHECK (
    (status = 'achieved' AND completed_at IS NOT NULL)
    OR (status <> 'achieved' AND completed_at IS NULL)
);

CREATE OR REPLACE FUNCTION update_goal_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_body_goals_updated_at
BEFORE UPDATE ON body_goals
FOR EACH ROW EXECUTE FUNCTION update_goal_updated_at();

CREATE TRIGGER trg_module_goals_updated_at
BEFORE UPDATE ON module_goals
FOR EACH ROW EXECUTE FUNCTION update_goal_updated_at();

CREATE TRIGGER trg_certificate_goals_updated_at
BEFORE UPDATE ON certificate_goals
FOR EACH ROW EXECUTE FUNCTION update_goal_updated_at();

COMMENT ON COLUMN body_goals.completed_at IS
'目標達成時間；進行中或已取消時為 NULL。';
COMMENT ON COLUMN body_goals.progress_type IS
'進度類型：numeric=數值型、milestone=一次性運動里程碑、unquantified=無法量化。';
COMMENT ON COLUMN module_goals.completed_at IS
'目標達成時間；進行中或已取消時為 NULL。';
COMMENT ON COLUMN certificate_goals.status IS
'目標狀態：active=進行中、achieved=已達成、cancelled=已取消。';
COMMENT ON COLUMN certificate_goals.completed_at IS
'目標達成時間；進行中或已取消時為 NULL。';
