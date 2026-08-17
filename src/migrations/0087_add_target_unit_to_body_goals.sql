-- 批次3（FR-48 方案A：飲食目標「結構化為主、LLM 輔助解析」）：body_goals 補一個 target_unit
-- 欄位給飲食目標使用（例如「大卡」「次」），體重/運動兩種既有 goal_type 的判斷邏輯只看
-- goal_type 不看這欄，不受影響、既有資料維持 NULL。Robin 於 2026-08-17 核准（見
-- docs/ADR/discuss/robinson.md 2026-08-17「批次3 開工前 SDD 計畫確認」）。
ALTER TABLE body_goals ADD COLUMN target_unit TEXT;

COMMENT ON COLUMN body_goals.target_unit IS '批次3新增：目標數值單位，目前只有 goal_type=diet 且 LLM 解析出結構化數值時才會有值（例如「大卡」「次」）；weight／exercise 的 target_value 語意固定，不使用這欄，維持 NULL';
