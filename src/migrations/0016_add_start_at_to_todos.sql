-- 待辦事項新增可選的區間起始時間，對應 docs/specs/robinson/SPEC.md FR-31b（時間區間待辦事項）。
-- Robin 於 2026-08-02 核准此 ALTER TABLE SQL。
ALTER TABLE todos ADD COLUMN start_at TIMESTAMPTZ;

COMMENT ON COLUMN todos.start_at IS '區間待辦事項的起始時間；NULL 代表這是單一時間點待辦（沿用原本 due_at 語意），非 NULL 時 due_at 代表區間的結束/截止時間';
