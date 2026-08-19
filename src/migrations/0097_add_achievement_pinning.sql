-- FR-76b：Mobile App 與 Telegram 共用成果置頂時間與排序。

ALTER TABLE user_achievements
ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_user_achievements_active_pinned
ON user_achievements (user_id, pinned_at DESC, unlocked_on DESC, id DESC)
WHERE deleted_at IS NULL;

COMMENT ON COLUMN user_achievements.pinned_at IS
'成果最後置頂時間；NULL 表示未置頂，Mobile App 與 Telegram 共用此狀態';
