-- Mobile App 每日體態紀錄：在體重紀錄保存當日腰圍，供腰圍趨勢使用。
-- 腰圍為選填，Mobile App 合理範圍為 50.0～150.0 公分。
ALTER TABLE body_weight_logs
    ADD COLUMN waist_cm NUMERIC(5,1) CHECK (waist_cm BETWEEN 50 AND 150);

COMMENT ON COLUMN body_weight_logs.waist_cm IS
    'Mobile App 每日體態紀錄腰圍（公分，選填），合理範圍 50.0～150.0；與 users.waist_cm 個人設定互不覆蓋';
