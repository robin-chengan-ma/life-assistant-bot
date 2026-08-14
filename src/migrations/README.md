# src/migrations/

依 [ADR-11](../../docs/ADR/discuss/robinson.md)（ADR-10「先審核後執行」的執行機制改為「Migration 檔案＋開機自動套用」取代人工貼 SQL）建立的資料庫 migration 機制，取代「人工連 Neon 主控台貼 SQL」。

## 流程

1. Claude 提出 `CREATE TABLE`／`ALTER TABLE` 等 SQL 草案 + 設計理由（依 [ADR-10](../../docs/ADR/discuss/robinson.md)：資料庫 Schema 建立採「先審核後執行」流程，並統一記錄於參考文件，執行前一定要先給 Robin 審核）
2. Robin 同意後，Claude 把該筆 SQL 存成本資料夾底下的 `.sql` 檔案
3. Claude commit + push 到 GitHub main 分支
4. Render 偵測到 push，自動重新部署
5. `main.py` 啟動時呼叫 `run_pending_migrations()`，依編號順序執行尚未套用過的檔案，並記錄到資料庫的 `schema_migrations` 追蹤表
6. Claude 把該次變更同步記錄到 [`docs/reference/db_schema.md`](../../docs/reference/db_schema.md)

## 命名規則

`NNNN_說明.sql`，四位數字編號 + 底線 + 簡短說明，例如：

```
0001_create_users_table.sql
0002_create_invite_codes_table.sql
```

編號依序遞增，不可跳號、不可重複。**已經套用過的檔案內容不可再修改**——如果要調整既有資料表，另開一個新編號的檔案（例如寫一段 `ALTER TABLE`），讓每個檔案都代表「一次已經發生過的變更」，維持歷史可追溯。

## 追蹤機制

資料庫裡會自動建立一張 `schema_migrations` 表（`filename` 為主鍵、`applied_at` 記錄套用時間），`run_pending_migrations()` 每次啟動都會先確保這張表存在，再比對哪些檔案還沒套用過。這張表的建立本身已隨 ADR-11 的核准一併授權，不需要再走一次 ADR-10 個別審核。

## 失敗處理

任一檔案執行失敗會中止整個流程並往外拋出例外，不會跳過繼續執行下一個檔案，避免 schema 停在「跑到一半」的不確定狀態。
