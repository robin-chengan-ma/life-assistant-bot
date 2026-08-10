-- FR-19j（見 docs/specs/robinson/SPEC.md，同步規劃於 docs/specs/mobile-app/SPEC.md ADR-1）：
-- 讓 FR-19b 既有的「私訊 Robin ＋ Google Drive log 連結」錯誤通知機制，額外落地一份可查詢、
-- 可補記解法的紀錄，供 Telegram「錯誤ID=N 已處理：...」指令與 Mobile App 客訴回饋頁的
-- 「系統錯誤回報」區塊共用讀寫。與使用者主動送出的 complaints 表無關，刻意分開兩張表。
-- Robin 於 2026-08-09 核准此 CREATE TABLE SQL。
CREATE TABLE system_error_reports (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity TEXT NOT NULL,
    triggering_feature TEXT,
    error_summary TEXT NOT NULL,
    drive_log_url TEXT,
    resolution TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE system_error_reports IS 'FR-19j：系統例外自動記錄，讓既有的私訊 Robin＋Drive log 通知機制額外落地一份可查詢、可補記解法的紀錄';
COMMENT ON COLUMN system_error_reports.occurred_at IS '例外實際發生的時間';
COMMENT ON COLUMN system_error_reports.severity IS '例外分級：general（一般感冒級，FR-19f）／critical（重大疾病級，FR-19g）';
COMMENT ON COLUMN system_error_reports.triggering_feature IS '觸發功能（例如 photo/voice/text），對應 webhook.py 既有的 error_feature 變數';
COMMENT ON COLUMN system_error_reports.error_summary IS '簡短錯誤描述，已先去除 URL 查詢字串再落地（避免例外訊息裡若帶金鑰的 URL 外洩）；完整原始 Traceback 仍只透過 drive_log_url 取得，不重複落地未經處理的版本';
COMMENT ON COLUMN system_error_reports.drive_log_url IS 'FR-19b 既有的 Google Drive 完整 log 連結，上傳失敗時可為 NULL（優雅降級，見 FR-19b）';
COMMENT ON COLUMN system_error_reports.resolution IS 'Robin 事後記錄的解法，尚未處理則為 NULL；可透過 Telegram「錯誤ID=N 已處理：...」指令或 Mobile App 編輯，兩個入口共用同一支 service 函式';
COMMENT ON COLUMN system_error_reports.created_at IS '這筆紀錄寫入資料庫的時間';
