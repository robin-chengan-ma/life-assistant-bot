-- 圖片/語音上傳的 Google Drive 網址記錄表，對應 docs/specs/robinson/SPEC.md ADR-13。
-- Robin 於 2026-07-31 核准建表 SQL（含中文欄位說明）；Step 1.3b（影像）與 Step 1.4（語音）共用此表。
CREATE TABLE media_uploads (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'audio')),
    gdrive_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_media_uploads_user_id ON media_uploads (user_id);

COMMENT ON TABLE media_uploads IS '使用者上傳的圖片/語音檔案 Google Drive 網址記錄，對應 ADR-13';
COMMENT ON COLUMN media_uploads.id IS '內部主鍵';
COMMENT ON COLUMN media_uploads.user_id IS '上傳者，對應 users.id';
COMMENT ON COLUMN media_uploads.media_type IS '檔案類型：image（圖片）或 audio（語音），Step 1.4 語音功能上線後會共用這張表';
COMMENT ON COLUMN media_uploads.gdrive_url IS '原始檔案的 Google Drive 網址（圖片壓縮只在辨識前即時處理，不另外存壓縮版）';
COMMENT ON COLUMN media_uploads.created_at IS '上傳時間';
