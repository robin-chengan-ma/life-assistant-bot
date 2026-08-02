-- 心情小記新增可補記的實際發生日期，對應 docs/specs/robinson/SPEC.md FR-49（心情小記補記/更新/刪除）。
-- Robin 於 2026-08-02 核准此 ALTER TABLE SQL。
ALTER TABLE mood_journals ADD COLUMN entry_date DATE;

COMMENT ON COLUMN mood_journals.entry_date IS '這筆心情小記實際對應的日期（可補記過去日期）；既有舊資料此欄位為 NULL，讀取時 fallback 使用 created_at 的日期部分；一律由 app 端依台灣時區算好日期後寫入，不依賴資料庫預設值';
