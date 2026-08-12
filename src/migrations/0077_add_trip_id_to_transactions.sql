-- 既有記帳與旅遊行程關聯。Robin 於 2026-08-12 核准。
ALTER TABLE transactions
ADD COLUMN trip_id BIGINT REFERENCES trips(id) ON DELETE SET NULL;

CREATE INDEX idx_transactions_trip_id ON transactions (trip_id);

COMMENT ON COLUMN transactions.trip_id IS '選填的旅遊行程；刪除行程只解除關聯，不刪除原始記帳';
