ALTER TABLE youtube_pushed_videos
    ADD COLUMN title TEXT,
    ADD COLUMN recommend_reason TEXT;

COMMENT ON COLUMN youtube_pushed_videos.title IS
    'FR-64 Mobile App 技術分享頁顯示用的推播當下影片標題；既有歷史資料允許為 NULL';
COMMENT ON COLUMN youtube_pushed_videos.recommend_reason IS
    'FR-64 Mobile App 技術分享頁顯示用的推薦理由摘要；既有歷史資料允許為 NULL';
