-- Step 3.4（FR-57a、ADR-21）：YouTube 技術情報多組主題設定，每組主題各自蒐集候選影片。
-- Robin 於 2026-08-08 核准此 CREATE TABLE SQL。
CREATE TABLE youtube_topics (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    topic TEXT NOT NULL,
    last_recommended_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, topic)
);

COMMENT ON TABLE youtube_topics IS 'Step 3.4：YouTube 技術情報多組主題設定（FR-57a），每組主題各自呼叫 search.list 蒐集候選影片';
COMMENT ON COLUMN youtube_topics.topic IS '關鍵字/主題文字，供 search.list 查詢使用';
COMMENT ON COLUMN youtube_topics.last_recommended_on IS '這個主題上次被推播的日期，NULL 代表從未推過；供 FR-58c 輪替公平性判斷「最久沒被推過」使用';
