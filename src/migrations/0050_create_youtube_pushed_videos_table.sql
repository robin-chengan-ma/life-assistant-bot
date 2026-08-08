-- Step 3.4（FR-58d、ADR-21）：YouTube 技術情報歷史推播紀錄，供 30 天去重查詢。
-- Robin 於 2026-08-08 核准此 CREATE TABLE SQL。
CREATE TABLE youtube_pushed_videos (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    video_id TEXT NOT NULL,
    topic TEXT,
    pushed_on DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_youtube_pushed_videos_user_pushed_on ON youtube_pushed_videos (user_id, pushed_on);

COMMENT ON TABLE youtube_pushed_videos IS 'Step 3.4：YouTube 技術情報歷史推播紀錄，供 FR-58d 過濾過去 30 天內已推播之 video_id 使用';
COMMENT ON COLUMN youtube_pushed_videos.topic IS '推播當下對應的主題文字，供除錯與統計用，不影響去重邏輯（去重只看 video_id + pushed_on）';
