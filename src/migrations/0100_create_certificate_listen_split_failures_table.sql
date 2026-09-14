-- 2026-09-13（Robin 明確要求，見 docs/ADR/discuss/robinson.md 對應日期條目）：整包聽力音檔
-- 依「Number N」題號標記切割時，若某一題無法 100% 確定切割邊界（見 src/bot/toeic.py
-- split_audio_by_question_count()），該題這次會被跳過、不寫入 certificate_questions。
-- Robin 反饋：同一份錄音的轉錄結果基本上是固定的，週週重試注定週週失敗，純粹浪費時間與
-- Groq API 額度，要求「失敗過的題目不必再跑」——因此新增這張表，記錄「已經確認切不出來、
-- 放棄這一題」的紀錄，`_process_listen_questions()` 掃描時會先檢查這張表，已經記錄過的
-- 題號直接略過、不會再嘗試下載/轉錄/切割。
--
-- 這是「永久跳過」，不是「下次自動重試」：Robin 明確表示「反正就是失敗的就不必再跑了」，
-- 如果之後真的要重新嘗試（例如發現這份錄音本身有問題、重新上傳/修正），需要手動從這張表
-- 刪除對應紀錄，程式不會自動判斷「素材是否已經被修正過」。
CREATE TABLE certificate_listen_split_failures (
    id BIGSERIAL PRIMARY KEY,
    exam_type TEXT NOT NULL,
    test_id TEXT NOT NULL,
    question_number INT NOT NULL,
    source_image_filename TEXT NOT NULL,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exam_type, test_id, question_number)
);

COMMENT ON TABLE certificate_listen_split_failures IS '記錄整包聽力音檔切割時，某一題「找不到 100% 確定的切割邊界、確認放棄」的題目；一旦記錄，之後排程掃描到同一題不會再嘗試切割，除非手動刪除這筆紀錄';
COMMENT ON COLUMN certificate_listen_split_failures.source_image_filename IS '這一題的聽力解答照片檔名（跟 certificate_questions.source_image_filename 同一套命名規則），純粹留作排查依據，不是去重比對的主鍵';
