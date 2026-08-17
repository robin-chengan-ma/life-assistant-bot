"""CloudSQL 通用 Client：目前串接 Neon PostgreSQL，封裝連線池與泛用 CRUD。

命名為 cloudsql 而不是 neon，是為了讓對外呼叫介面（select / insert /
update / delete）維持穩定；未來若要換成其他 PostgreSQL 相容服務
（例如 GCP Cloud SQL），呼叫端的程式碼不需要跟著改。

連線字串不寫死在程式碼中，一律由呼叫端傳入 dsn，或讀環境變數 DATABASE_URL。

安全注意事項：
- table / columns 名稱無法被參數化（PostgreSQL 語法限制），一律只能傳入
  程式內部信任的字串常數，絕對不可以把使用者輸入直接當成 table/column 帶進來。
- where 條件的「值」一律透過 params 參數傳入，交由 psycopg2 做參數化處理，
  不要用字串格式化（f-string）把值拼進 SQL。
- update() / delete() 都強制要求 where，禁止無條件更新或刪除整張表。
"""
import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from psycopg2 import pool as pg_pool
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor


class CloudSQLClient:
    """連線池管理 + 泛用 CRUD。"""

    def __init__(self, dsn: str | None = None, min_conn: int = 1, max_conn: int = 5):
        dsn = dsn or os.environ.get("DATABASE_URL")
        if not dsn:
            raise ValueError("dsn 不可為空，請傳入或設定環境變數 DATABASE_URL")
        # Neon 提供的連線字串預設已包含 sslmode=require，不需要額外指定。
        # max_conn 刻意設低，避免耗盡 Neon 免費方案的連線數上限。
        self._pool = pg_pool.ThreadedConnectionPool(min_conn, max_conn, dsn=dsn)

    @contextmanager
    def _get_connection(self) -> Iterator[PgConnection]:
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def close(self) -> None:
        """關閉連線池內所有連線，通常只在應用程式關閉（graceful shutdown）時呼叫一次。"""
        self._pool.closeall()

    def select(
        self,
        table: str,
        columns: Iterable[str] = ("*",),
        where: str | None = None,
        params: tuple | None = None,
        fetch_one: bool = False,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """查詢資料。範例：client.select("todos", where="user_id = %s", params=(1,))"""
        column_clause = ", ".join(columns)
        query = f"SELECT {column_clause} FROM {table}"
        if where:
            query += f" WHERE {where}"

        with self._get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params or ())
            if fetch_one:
                row = cursor.fetchone()
                return dict(row) if row else None
            return [dict(row) for row in cursor.fetchall()]

    def insert(self, table: str, data: dict[str, Any], returning: str = "id") -> Any:
        """新增一筆資料，回傳 returning 欄位的值（預設回傳主鍵 id）。"""
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ", ".join(["%s"] * len(columns))
        column_clause = ", ".join(columns)
        query = (
            f"INSERT INTO {table} ({column_clause}) VALUES ({placeholders}) "
            f"RETURNING {returning}"
        )

        with self._get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(query, values)
            result = cursor.fetchone()
            return result[0] if result else None

    def update(self, table: str, data: dict[str, Any], where: str, params: tuple) -> int:
        """更新資料，回傳受影響的資料筆數；where 必填，避免整張表被誤改。"""
        if not where:
            raise ValueError("update() 必須提供 where 條件，禁止無條件更新整張表")

        set_clause = ", ".join([f"{column} = %s" for column in data])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        values = list(data.values()) + list(params)

        with self._get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(query, values)
            return cursor.rowcount

    def delete(self, table: str, where: str, params: tuple) -> int:
        """刪除資料，回傳受影響的資料筆數；where 必填，避免整張表被清空。"""
        if not where:
            raise ValueError("delete() 必須提供 where 條件，禁止無條件刪除整張表")

        query = f"DELETE FROM {table} WHERE {where}"

        with self._get_connection() as conn, conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def execute(self, query: str, params: tuple | None = None) -> None:
        """執行任意 SQL 語句（不回傳資料列），主要供 DDL 使用（CREATE TABLE / ALTER TABLE 等）。

        安全注意事項：這是繞過 select/insert/update/delete 參數化保護的逃生口，query 內容
        一律只能是程式內部信任的字串常數（例如 migration 檔案內容），絕對不可以把使用者輸入
        直接拼進 query。目前用於 src/migrations/runner.py 的 migration 執行機制（見 ADR-11）。

        **2026-08-08（production 事故修復）**：`params` 為 `None`（沒有要參數化的值，本來就是
        `execute()` 呼叫端的大宗用法，例如 migration 檔案的原始 DDL）時，一律呼叫
        `cursor.execute(query)`（不帶第二個參數），而不是像過去那樣退回傳一個空 tuple `()`。
        原因：psycopg2 只要 `execute()` 收到「非 None」的第二個參數（即使是空 tuple），就會
        對整個 query 字串套用 Python `%`-style 格式化解析，此時 query 內容裡任何字面上的 `%`
        字元（例如 migration 檔案裡 `COMMENT ON COLUMN ... IS 'FR-43 50% 門檻...'` 這種註解
        文字，或 `LIKE '%xxx%'`／PostgreSQL `format()` 的 `%I`）都會被誤判成參數佔位符，因為
        沒有對應的參數可以代入而丟出 `IndexError: tuple index out of range`——這正是 Robin
        2026-08-08 回報的 production 事故根因（migration `0018_add_budget_fields_to_users.sql`
        卡住，導致 Phase 2／3 所有後續 migration 都沒套用到 Neon）。不帶第二個參數呼叫
        `cursor.execute()` 時，psycopg2 完全不解析 `%`，query 會被當成純字串原封不動送出，
        這才是「執行任意信任字串常數」該有的行為。
        """
        with self._get_connection() as conn, conn.cursor() as cursor:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """執行任意「會回傳資料列」的 SQL 語句（SELECT 類），回傳結果列。

        跟 execute() 一樣是繞過 select() 的 table/columns/where 介面的逃生口，用於 select()
        無法表達的查詢（例如 `SELECT pg_database_size(current_database())` 這種沒有實體
        table 可對應的系統函式呼叫）。2026-08-02（Step 1.6，見 robinson SPEC.md FR-21）：
        `src/bot/monitoring.py` 用這個方法查詢 Neon 資料庫目前佔用容量。

        安全注意事項：跟 execute() 一樣，query 內容一律只能是程式內部信任的字串常數，絕對不可以
        把使用者輸入直接拼進 query。

        **2026-08-08**：`params` 為 `None` 時同樣不帶第二個參數呼叫 `cursor.execute()`，理由
        同 `execute()` 的說明——避免字面 `%` 字元被誤判成參數佔位符。
        """
        with self._get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
