-- FR-77：移除已正式取消的客訴、持久化知識庫、逐則對話與長期對話摘要資料表。
-- 2026-08-18 正式環境盤點：complaints=0、knowledge_base=5、conversation_logs=180、
-- conversation_summaries=1；四張表均只有指向 users(id) 的外鍵，沒有其他資料表引用。
-- 刻意不使用 CASCADE：若部署時發現未盤點依賴，migration 必須失敗並停止，不可連帶刪除。
-- 回滾：以 0003／0004／0007／0015 的最終 schema 重建四表，再匯入部署前匯出資料。

BEGIN;

DROP TABLE conversation_summaries;
DROP TABLE conversation_logs;
DROP TABLE complaints;
DROP TABLE knowledge_base;

COMMIT;
