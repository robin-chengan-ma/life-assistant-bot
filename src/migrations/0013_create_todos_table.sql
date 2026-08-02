-- 待辦事項表，對應 docs/specs/robinson/SPEC.md FR-31、FR-31a、FR-32（Step 1.7）。
-- Robin 於 2026-08-02 核准建表 SQL（含中文欄位說明）。
CREATE TABLE todos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    remind_before_30min BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'expired')),
    reminded_30min_sent_at TIMESTAMPTZ,
    daily_pushed_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_todos_user_id_status ON todos (user_id, status);
CREATE INDEX idx_todos_due_at ON todos (due_at);

COMMENT ON TABLE todos IS '待辦事項表：對應 FR-31／FR-31a／FR-32，使用者以自然語言描述的待辦事項';
COMMENT ON COLUMN todos.id IS '內部主鍵';
COMMENT ON COLUMN todos.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN todos.content IS '待辦事項內容摘要（由 LLM 從使用者自然語言描述中萃取）';
COMMENT ON COLUMN todos.due_at IS '預定執行時間，由 LLM 依對話內容與伺服器當下日期換算成絕對時間';
COMMENT ON COLUMN todos.remind_before_30min IS '使用者記錄當下是否選擇要在預定時間前 30 分鐘收到提醒（FR-32）';
COMMENT ON COLUMN todos.status IS '狀態：pending=待處理, completed=使用者確認已完成, cancelled=使用者確認取消, expired=已超過預定時間仍未處理而自動標記（FR-31a）';
COMMENT ON COLUMN todos.reminded_30min_sent_at IS '「預定時間前 30 分鐘提醒」實際送出的時間戳記；非 NULL 代表已經推播過，避免同一則提醒被重複推播多次';
COMMENT ON COLUMN todos.daily_pushed_on IS '「每日 08:00 固定推播」最後一次把這筆待辦包含在推播內容裡的日期；避免同一天內因排程重複觸發而被重複推播';
COMMENT ON COLUMN todos.created_at IS '這筆待辦事項建立的時間';
