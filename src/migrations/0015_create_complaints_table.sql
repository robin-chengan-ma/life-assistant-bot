-- 客訴收集表，對應 docs/specs/robinson/SPEC.md FR-60～FR-63（Step 1.9）。
-- Robin 於 2026-08-02 核准建表 SQL（含中文欄位說明）。
CREATE TABLE complaints (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_complaints_user_id ON complaints (user_id);

COMMENT ON TABLE complaints IS '客訴/意見回饋收集表：對應 FR-60～FR-63';
COMMENT ON COLUMN complaints.id IS '內部主鍵';
COMMENT ON COLUMN complaints.user_id IS '提出客訴的使用者，對應 users.id';
COMMENT ON COLUMN complaints.content IS '客訴原始內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN complaints.created_at IS '這筆客訴建立的時間';
