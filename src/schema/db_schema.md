# Robinson 資料庫 Schema

> 本文件記錄 Neon PostgreSQL 上所有資料表的建表 SQL 與設計理由。依 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) 的 ADR-10，任何建表 / 改表操作都必須「先給 Robin 看 SQL 語法 + 說明設計理由 → 取得同意」，不得跳過審核直接執行。
>
> **執行機制（ADR-11）**：同意後，SQL 不是直接對 Neon 執行，而是存成 [`src/migrations/`](../migrations/README.md) 底下的檔案，commit + push 後由 Render 自動部署套用。所以本文件的「記錄時機」是 push 完成當下，實際套用時間以資料庫的 `schema_migrations` 追蹤表為準（下次確認部署成功後可回頭核對）。

## 使用方式

新增一張表時，複製下方樣板，填入實際內容，依「建立時間」由舊到新往下疊加。**不要**回頭修改已核准並執行過的舊紀錄（除非該表結構真的變更，這種情況要新增一筆「變更紀錄」，而不是竄改原始記錄）。

```markdown
### <table_name>

**建立日期**：YYYY-MM-DD
**用途**：<這張表存什麼資料、被哪些 FR 使用>
**Migration 檔案**：`src/migrations/NNNN_xxx.sql`

​```sql
CREATE TABLE ...
​```

**設計理由**：
- <為什麼這樣選型別/欄位/索引/外鍵>

**變更紀錄**（如果有）：
| 日期 | 變更內容 | 原因 | Migration 檔案 |
| --- | --- | --- | --- |
```

---

## 資料表清單

> 目前尚無已核准執行的資料表。Phase 0 Step 0.5 將依 SPEC.md 各功能模組的資料需求，逐一提出 SQL 草案與設計理由供 Robin 審核，核准後存成 `src/migrations/` 檔案並 push，在此處記錄。

<!-- 尚未有資料表，待 Phase 0 Step 0.5 開始建置後於此處新增 -->
