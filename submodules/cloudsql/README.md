# cloudsql

PostgreSQL 通用 Client，目前串接 Neon PostgreSQL，封裝連線池與泛用 CRUD（select / insert / update / delete）。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 連線字串（例：`postgresql://user:password@host:port/dbname`）。Neon 提供的字串預設已含 `sslmode=require` |

## 安裝

```bash
pip install -r submodules/cloudsql/requirements.txt
```

## 使用範例

```python
from submodules.cloudsql.client import CloudSQLClient

db = CloudSQLClient()  # 預設讀環境變數 DATABASE_URL，也可以 CloudSQLClient(dsn="...")

# 查詢
todos = db.select("todos", columns=["id", "title", "is_done"], where="user_id = %s", params=(1,))

# 新增（回傳新資料的 id）
new_id = db.insert("todos", {"user_id": 1, "title": "倒垃圾", "is_done": False})

# 更新（回傳受影響筆數）
db.update("todos", {"is_done": True}, where="id = %s", params=(new_id,))

# 刪除（回傳受影響筆數，where 必填）
db.delete("todos", where="id = %s", params=(new_id,))

# 應用程式關閉時
db.close()
```

執行任意 SQL（DDL，例如 `CREATE TABLE`）：

```python
db.execute("CREATE TABLE IF NOT EXISTS todos (id serial primary key, title text)")
```

執行任意「會回傳資料列」的 SQL（`select()` 的 table/columns/where 介面無法表達的查詢，例如系統函式）：

```python
rows = db.execute_query("SELECT pg_database_size(current_database()) AS size_bytes")
size_bytes = rows[0]["size_bytes"]
```

## 設計限制（務必遵守）

1. `table` 與 `columns` 只能傳入程式內部信任的字串常數，**絕對不可以**把使用者輸入直接當成 table/column 名稱帶入。
2. `where` 條件的「值」一律透過 `params` 傳入，交由 psycopg2 做參數化處理，不要用 f-string 把值拼進 SQL。
3. `update()` / `delete()` 都要求必填 `where`，避免誤改/誤刪整張表。
4. 連線池上限預設 `max_conn=5`，對應 Neon 免費方案的連線數限制；若升級付費方案可自行調整。
5. `execute()` 是繞過參數化保護的逃生口，只給程式內部信任的 SQL（如 migration 檔案）使用，絕對不可以把使用者輸入拼進去；目前唯一呼叫端是 `src/migrations/runner.py`（見 ADR-11）。
6. `execute_query()` 跟 `execute()` 一樣是逃生口，差別只在於它會回傳資料列，用於系統層級查詢（例如 `src/bot/monitoring.py` 查 Neon 容量），一樣不可以把使用者輸入拼進去。
7. `params is None` 時完全不傳第二參數給 psycopg2（而非傳空 tuple），避免 SQL 內文只要含字面 `%` 字元（例如 migration 的 `COMMENT ON COLUMN` 註解寫「50%」）就被誤判成參數佔位符觸發 `IndexError`；細節見 `docs/ADR/debug/submodules-core.md` 2026-08-08 條目（生產事故）。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md)「Submodules 共用子模組基礎骨架」、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md)、[docs/ADR/debug/submodules-core.md](../../docs/ADR/debug/submodules-core.md)
