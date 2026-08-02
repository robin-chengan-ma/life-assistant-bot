-- 心情小記表，對應 docs/specs/robinson/SPEC.md FR-49、FR-50（Step 1.8）。
-- Robin 於 2026-08-02 核准建表 SQL（含中文欄位說明）。
CREATE TABLE mood_journals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    mood_category TEXT NOT NULL CHECK (mood_category IN (
        'angry_anxious', 'sad_down', 'tired_burned_out', 'neutral', 'calm_relaxed', 'happy_excited'
    )),
    content TEXT NOT NULL,
    achievement_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mood_journals_user_id ON mood_journals (user_id);

COMMENT ON TABLE mood_journals IS '心情小記表：對應 FR-49／FR-50，使用者每日心情紀錄與隨筆';
COMMENT ON COLUMN mood_journals.id IS '內部主鍵';
COMMENT ON COLUMN mood_journals.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN mood_journals.mood_category IS '心情分類（FR-56h 情境範例六選一）：angry_anxious=生氣/焦慮, sad_down=難過/低落, tired_burned_out=疲倦/厭世, neutral=普通/平淡, calm_relaxed=平靜/放鬆, happy_excited=高興/興奮';
COMMENT ON COLUMN mood_journals.content IS '完整日記內容（已經過 FR-13 個資遮蔽處理，不存未遮蔽的原文）';
COMMENT ON COLUMN mood_journals.achievement_note IS 'FR-50 個人成就三選一提示的回答（今天完成了什麼一句話總結／挑一件有感覺的事／寫下啟發或下次想改變的地方，僅需一項）；使用者選擇跳過時為 NULL，同樣已經過 FR-13 個資遮蔽處理';
COMMENT ON COLUMN mood_journals.created_at IS '這筆心情小記建立的時間';
