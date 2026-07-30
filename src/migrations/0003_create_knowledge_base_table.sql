CREATE TABLE knowledge_base (
    id BIGSERIAL PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('general_persona', 'general_family', 'custom')),
    user_id BIGINT REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_base_user_id ON knowledge_base (user_id);

COMMENT ON TABLE knowledge_base IS '知識庫表：對應 FR-9 前三類（人格背景／家人背景故事／使用者自建知識庫）';
COMMENT ON COLUMN knowledge_base.id IS '內部主鍵';
COMMENT ON COLUMN knowledge_base.category IS '知識庫類別：general_persona=Robinson人格背景, general_family=Robin與家人的共同背景故事, custom=特定使用者自建的客製知識庫';
COMMENT ON COLUMN knowledge_base.user_id IS '所屬使用者；general_persona/general_family 為全體共用固定 NULL，custom 才會指向對應 users.id';
COMMENT ON COLUMN knowledge_base.content IS '知識庫內容文字';
COMMENT ON COLUMN knowledge_base.created_at IS '建立時間';
COMMENT ON COLUMN knowledge_base.updated_at IS '最後更新時間';
