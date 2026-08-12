ALTER TABLE users
    ADD COLUMN theme_preference TEXT NOT NULL DEFAULT 'light',
    ADD COLUMN font_size_preference TEXT NOT NULL DEFAULT 'medium',
    ADD COLUMN privacy_mask_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT users_theme_preference_check
        CHECK (theme_preference IN ('light', 'dark')),
    ADD CONSTRAINT users_font_size_preference_check
        CHECK (font_size_preference IN ('small', 'medium', 'large'));

COMMENT ON COLUMN users.theme_preference IS 'FR-72 Mobile App 顯示主題：light 或 dark';
COMMENT ON COLUMN users.font_size_preference IS 'FR-72 Mobile App 字體大小：small、medium 或 large';
COMMENT ON COLUMN users.privacy_mask_enabled IS 'FR-72 Mobile App 敏感數字遮罩是否啟用';
