-- 記帳模組：支出/收入交易紀錄，對應 docs/specs/robinson/SPEC.md FR-42。
-- Robin 於 2026-08-04 核准此 CREATE TABLE SQL。
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
    category TEXT NOT NULL CHECK (category IN (
        '餐飲', '交通', '購物', '居住', '娛樂', '醫療', '薪資', '獎金', '其他'
    )),
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    note TEXT,
    transaction_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transactions_user_id ON transactions (user_id);

COMMENT ON TABLE transactions IS '記帳交易表：對應 FR-42，使用者的支出/收入紀錄，支援補記/更新/刪除';
COMMENT ON COLUMN transactions.id IS '內部主鍵';
COMMENT ON COLUMN transactions.user_id IS '所屬使用者，對應 users.id';
COMMENT ON COLUMN transactions.type IS '交易類型：expense=支出, income=收入';
COMMENT ON COLUMN transactions.category IS '交易分類（固定清單）：餐飲/交通/購物/居住/娛樂/醫療三類屬於支出常見分類，薪資/獎金屬於收入常見分類，其他兩種皆可用；分類與 type 的合理搭配由應用層驗證，不由資料庫層限制';
COMMENT ON COLUMN transactions.amount IS '交易金額，一律為正數，方向由 type 決定';
COMMENT ON COLUMN transactions.note IS '備註，可能含個資，已經過 FR-13 個資遮蔽處理，選填';
COMMENT ON COLUMN transactions.transaction_date IS '這筆交易實際發生的日期（可補記過去日期）；一律由 app 端依台灣時區算好日期後寫入，不依賴資料庫預設值，設計比照 mood_journals.entry_date';
COMMENT ON COLUMN transactions.created_at IS '這筆交易記錄建立的時間';
