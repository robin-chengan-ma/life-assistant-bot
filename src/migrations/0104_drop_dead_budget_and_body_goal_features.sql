-- 2026-11-26（ADR 再修正，見 docs/ADR/discuss/robinson.md）：Robin 實際使用陽春版後發現「設定
-- 記帳預算」「設定體態目標」兩個功能背後其實已經沒有任何設定入口可用（Telegram 機器人已於
-- 0101/0102/0103 大幅精簡成只剩權限管理與推播提醒，Mobile App 也從未實作對應畫面）；對應的
-- `set_monthly_budget`／`set_budget_override`／`create_goal`／`update_goal`／`cancel_goal` 等
-- 函式與本檔移除的資料表／欄位經確認後一併砍除。
--
-- 同時移除 `users.birthday`（migration 0028，FR-53 舊設計）：這個欄位早已沒有任何寫入路徑，但
-- `src/services/app_analytics.py` 的首頁摘要查詢仍會多查這個欄位，把「所有人」的生日混進每個人
-- 的首頁清單，造成生日隱私外洩；已於程式碼移除對應查詢，這裡一併刪除死欄位。

BEGIN;

-- 記帳預算：先刪有外鍵/相依指向 budget_overrides 的查詢用不到，直接刪表即可。
DROP TABLE IF EXISTS budget_overrides;

-- 體態目標。
DROP TABLE IF EXISTS body_goals;

-- users 表上隨對應功能一併刪除的欄位。
ALTER TABLE users DROP COLUMN IF EXISTS monthly_budget;
ALTER TABLE users DROP COLUMN IF EXISTS budget_alert_50_sent_month;
ALTER TABLE users DROP COLUMN IF EXISTS budget_alert_80_sent_month;
ALTER TABLE users DROP COLUMN IF EXISTS finance_monthly_report_sent_month;
ALTER TABLE users DROP COLUMN IF EXISTS birthday;

COMMIT;
