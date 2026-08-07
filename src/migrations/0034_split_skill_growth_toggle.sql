-- 功能開關拆分：Robin 認為 TOEIC（未來也可能有其他證照）跟「技術情報」（新聞/電子報、
-- 未來 YouTube 技術情報）性質不同，一個是硬實力學習追蹤、一個是資訊訂閱推播，希望開關能
-- 各自獨立；另外語言學習（英文口說、其他語言，尚未開發）也希望獨立於證照準備之外，三者各自
-- 開關。對應 docs/specs/robinson/SPEC.md FR-22/FR-23/FR-24~30/FR-57~59、
-- docs/specs/feature-toggles/SPEC.md FR-3。
-- Robin 於 2026-08-07 核准此 ALTER TABLE SQL。

-- 動態尋找 feature_key 現有的 CHECK 約束並移除（不假設 Postgres 自動命名一定是
-- feature_toggles_feature_key_check，改用 pg_constraint 查詢實際約束名稱，較穩健）。
DO $$
DECLARE
    existing_check_name TEXT;
BEGIN
    SELECT con.conname INTO existing_check_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'feature_toggles'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%feature_key%';

    IF existing_check_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE feature_toggles DROP CONSTRAINT %I', existing_check_name);
    END IF;
END $$;

ALTER TABLE feature_toggles ADD CONSTRAINT feature_toggles_feature_key_check CHECK (feature_key IN (
    'todo', 'job_search', 'budget', 'body', 'tech_intel', 'certificate', 'language',
    'mood_journal', 'friend_mode', 'important_notify'
));

-- 既有的 'skill_growth' 開關資料搬移到新的 'tech_intel'（技術情報：目前為每日技術新聞/電子報
-- 摘要，FR-22/23；未來 YouTube 技術情報 FR-57~59 也會共用這把開關），保留原本的開關狀態；
-- 'certificate'（證照準備，如 TOEIC，FR-24~30）與 'language'（語言學習，尚未開發）等到對應
-- 功能實際開工、使用者觸發「我的功能設定」時，由既有的 toggles.ensure_default_toggles()
-- 自動補上預設值（TRUE），不需要在這裡預先塞資料。
UPDATE feature_toggles SET feature_key = 'tech_intel' WHERE feature_key = 'skill_growth';

COMMENT ON COLUMN feature_toggles.feature_key IS '功能代號：todo=待辦, job_search=求職, budget=記帳, body=體態管理, tech_intel=技術情報（新聞/電子報/YouTube）, certificate=證照準備（TOEIC等）, language=語言學習, mood_journal=心情小記, friend_mode=好友模式, important_notify=重要通知';
