-- 新增 knowledge_base.label 欄位：主動新增知識功能（chat-core SPEC.md FR-11）用來存放
-- 使用者自訂或 Robinson 判斷的分類/標籤（例如「SOP」「食譜」「行程」），方便之後依主題查找，
-- 也供 /clean-target-dialog（FR-12）判斷刪除範圍時參考。允許 NULL：既有的 general_persona／
-- general_family／custom 資料都沒有這個欄位，不回填，維持 NULL 即可。
ALTER TABLE knowledge_base ADD COLUMN label TEXT;

COMMENT ON COLUMN knowledge_base.label IS '分類/標籤（例如「SOP」「食譜」「行程」），主動新增知識時由使用者確認或 Robinson 判斷產生；既有資料與大部分 general_persona/general_family 內容不使用此欄位，允許 NULL';
