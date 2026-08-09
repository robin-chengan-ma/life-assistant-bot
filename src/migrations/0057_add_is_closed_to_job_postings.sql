-- Step 4.1 追加（FR-34d，見 docs/specs/robinson/SPEC.md ADR-26 決策 5）：2026-08-09 Robin 透過
-- 瀏覽器 DevTools 實測確認 104 API 列表／詳情回應皆含 jobSwitch／switch 欄位（"on" 代表職缺仍
-- 開放），可自動判斷職缺是否已關閉，不需要如 ADR-26 決策 5 原訂備案「無法自動判斷才用人工 Excel
-- 標記」——這一欄從一開始就走自動化路線，FR-38b 的 Excel「是否關閉」欄位因此不會出現。
-- is_unliked／score／rank／recommend_reason／skill_gap_note 等 Step 4.2 才會用到的欄位仍不在此
-- 建立（`is_unliked` 是 Robin 主觀偏好，沒有自動化替代方案，留待 Step 4.2 開工時另開 migration）。
-- Robin 於 2026-08-09 核准此 ALTER TABLE SQL。
ALTER TABLE job_postings ADD COLUMN is_closed BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN job_postings.is_closed IS '職缺是否已關閉，依 104 API 回應的 jobSwitch／switch 欄位自動判斷（非 "on" 視為已關閉），每次爬蟲重新爬到既有職缺時同步更新，FR-38a 排名時排除 is_closed = TRUE 的職缺';
