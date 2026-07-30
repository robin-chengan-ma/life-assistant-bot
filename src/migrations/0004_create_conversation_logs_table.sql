CREATE TABLE conversation_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_conversation_logs_user_id_created_at ON conversation_logs (user_id, created_at);

COMMENT ON TABLE conversation_logs IS '對話紀錄表：對應 FR-9 第④類，個人化的完整對話歷史';
COMMENT ON COLUMN conversation_logs.id IS '內部主鍵';
COMMENT ON COLUMN conversation_logs.user_id IS '這則訊息屬於哪位使用者，對應 users.id';
COMMENT ON COLUMN conversation_logs.role IS '訊息角色：user=使用者傳送, assistant=Robinson回覆';
COMMENT ON COLUMN conversation_logs.content IS '訊息內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN conversation_logs.created_at IS '訊息發生時間';
COMMENT ON COLUMN conversation_logs.deleted_at IS '軟刪除時間戳記；FR-13 觸發個資清除機制時，將該筆設為此欄位而非真的砍掉資料列，查詢時需排除 deleted_at IS NOT NULL 的記錄';
