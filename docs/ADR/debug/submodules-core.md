# Submodules 共用子模組基礎骨架 修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。
> 本檔初版整併自 `docs/specs/_archive/submodules-core/SPEC.md`「變更記錄」中屬於「問題／修復」性質的段落；決策性質的段落已改放 `docs/ADR/discuss/submodules-core.md`。

## 2026-08-08 `CloudSQLClient.execute()`／`execute_query()` 對含 `%` 字元的 SQL 拋出 `IndexError`（生產事故）

**現象**：`src/migrations/0018_add_budget_fields_to_users.sql` 這支既有 migration 重新套用時，`execute()` 拋出 `IndexError`；migration 本身沒有明顯語法錯誤，過去也曾成功套用過。

**排查過程**：確認錯誤發生在 psycopg2 執行 SQL 字串的階段，而不是連線或 SQL 語法本身；比對這支 migration 的內容，發現其中一則 `COMMENT ON COLUMN` 的註解文字含字面 `%`（例如「50%」）。追加用 `grep -l '%' src/migrations/*.sql` 掃描全部 migration 檔案，確認另有一支（`0034`）同樣含字面 `%`，屬同一類潛在風險。

**根因**：psycopg2 只要收到「非 `None`」的第二參數（即使是空 tuple `()`），就會對整個 query 字串做 `%`-style 格式化解析，把字面 `%` 誤判成參數佔位符；`CloudSQLClient.execute()`／`execute_query()` 原本不論呼叫端有沒有傳 `params`，一律轉成 `params or ()` 再交給 psycopg2，導致任何 SQL 內文只要含字面 `%`（不限於 migration，理論上任何走 `execute()`／`execute_query()` 逃生口的 SQL 都可能中招）都會誤觸發這個解析並拋出 `IndexError`。

**修復方式**：`submodules/cloudsql/client.py`——`execute()`／`execute_query()` 改為 `params is None` 時完全不傳第二參數給 psycopg2（而不是傳空 tuple），只有呼叫端明確傳入 `params` 時才觸發參數化格式化解析。

**驗證方式**：958 個測試全過，新增涵蓋「SQL 內文含字面 `%` 字元且未傳 `params`」情境的測試案例；`0018`／`0034` 兩支既有 migration 重新套用皆正常。
