-- 批次3補做（Robin 要求不得漏做）：飲食目標（FR-48 方案A）補上「方向」欄位，讓自動達成判斷能
-- 區分「至少要達到」（MIN，例如每週吃蔬菜5次）跟「不能超過」（MAX，例如熱量控制在14000大卡
-- 以內）兩種相反語意；weight／exercise 兩種既有 goal_type 語意固定，不使用這欄，維持 NULL。
ALTER TABLE body_goals ADD COLUMN target_direction TEXT CHECK (target_direction IN ('min', 'max'));

COMMENT ON COLUMN body_goals.target_direction IS '批次3新增：只有 goal_type=diet 且 LLM 解析出結構化數值時才會有值，min=目標至少要達到這個數值、max=目標不能超過這個數值；決定 check_and_push_diet_goal_achievements() 的判斷方向';
