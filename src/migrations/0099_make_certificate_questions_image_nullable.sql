-- 2026-08-25（Robin 核准，聽力題目庫改版：軌道一聽力題內容改由「解答照片」統一驅動，
-- 見 docs/ADR/discuss/skill-growth.md 對應日期條目）：
-- Part 2（純聽力、無印刷內容）沒有題目照片可拍，`image_gdrive_url` 不能再是 NOT NULL，
-- 否則這類題目永遠無法建立。改為 nullable；NULL 代表這題沒有題目圖片（例如 Part 2），
-- 呈現邏輯（src/bot/certificate_answer.py）已同步處理「沒有圖片就不顯示圖片」。
ALTER TABLE certificate_questions ALTER COLUMN image_gdrive_url DROP NOT NULL;

COMMENT ON COLUMN certificate_questions.image_gdrive_url IS
'題目圖片連結；聽力題可能為 NULL（例如 Part 2 沒有題目照片，內容完全來自解答照片＋音檔），
閱讀題與有題目照片的聽力題（例如 Part 1）維持有值';
