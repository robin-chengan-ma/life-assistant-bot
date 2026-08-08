"""submodules/cloudsql/client.py 的單元測試。

2026-08-02（Step 1.6，見 robinson SPEC.md FR-21）：cloudsql 的既有方法（select/insert/
update/delete/execute）仍如 submodules-core SPEC.md Step S.6 所述「待對應功能實際串接時
補上」，這裡只補新增的 `execute_query()`（`src/bot/monitoring.py` 監控 Neon 容量會用到），
不回頭補齊既有方法的測試，範圍對應本次實際新增的程式碼。

**2026-08-08（production 事故修復）**：補上 `execute()`／`execute_query()` 在 `params=None`
時的回歸測試——Robin 回報 production migration `0018_add_budget_fields_to_users.sql` 執行時
拋出 `IndexError: tuple index out of range`，根因是舊版 `execute()` 對沒有參數的呼叫也會傳一個
空 tuple `()` 給 `cursor.execute()`，觸發 psycopg2 對 query 字串做 `%`-style 格式化解析，讓
migration 檔案裡字面的 `%` 字元（例如 COMMENT 註解文字「50%」）被誤判成參數佔位符。修正為
`params is None` 時完全不帶第二個參數呼叫 `cursor.execute()`。

不連線真正的 Neon，mock `psycopg2.pool.ThreadedConnectionPool` 與連線/cursor。
"""
from unittest.mock import MagicMock

from submodules.cloudsql.client import CloudSQLClient


def _make_client(monkeypatch, fetch_result):
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False
    fake_cursor.fetchall.return_value = fetch_result

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    fake_pool = MagicMock()
    fake_pool.getconn.return_value = fake_conn

    monkeypatch.setattr(
        "submodules.cloudsql.client.pg_pool.ThreadedConnectionPool", lambda *a, **kw: fake_pool
    )

    client = CloudSQLClient(dsn="postgresql://fake")
    return client, fake_cursor, fake_conn


def test_execute_query_returns_rows_as_dicts(monkeypatch):
    client, fake_cursor, _ = _make_client(monkeypatch, fetch_result=[{"size_bytes": 12345}])

    rows = client.execute_query("SELECT pg_database_size(current_database()) AS size_bytes")

    assert rows == [{"size_bytes": 12345}]
    # 2026-08-08 修正：params=None 時不帶第二個參數呼叫 cursor.execute()，避免 query 字串裡
    # 字面的 % 字元被 psycopg2 誤判成參數佔位符（見模組 docstring、production 事故根因）。
    fake_cursor.execute.assert_called_once_with(
        "SELECT pg_database_size(current_database()) AS size_bytes"
    )


def test_execute_query_passes_params(monkeypatch):
    client, fake_cursor, _ = _make_client(monkeypatch, fetch_result=[])

    client.execute_query("SELECT 1 WHERE %s = %s", params=(1, 1))

    fake_cursor.execute.assert_called_once_with("SELECT 1 WHERE %s = %s", (1, 1))


def test_execute_query_commits_and_returns_connection(monkeypatch):
    client, _, fake_conn = _make_client(monkeypatch, fetch_result=[])

    client.execute_query("SELECT 1")

    fake_conn.commit.assert_called_once()


# --- execute()（2026-08-08 production 事故修復：見模組 docstring 根因說明） ---


def _make_execute_client(monkeypatch):
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    fake_pool = MagicMock()
    fake_pool.getconn.return_value = fake_conn

    monkeypatch.setattr(
        "submodules.cloudsql.client.pg_pool.ThreadedConnectionPool", lambda *a, **kw: fake_pool
    )

    client = CloudSQLClient(dsn="postgresql://fake")
    return client, fake_cursor, fake_conn


def test_execute_without_params_does_not_pass_empty_tuple(monkeypatch):
    """回歸測試：這是 production 事故的根因——舊版會呼叫 cursor.execute(query, ())，讓 query
    字串裡字面的 % 字元（migration 檔案常見於 COMMENT 註解，例如「50%」）被 psycopg2 誤判成
    參數佔位符，丟出 IndexError。修正後不帶第二個參數呼叫，query 完全不被 % 格式化解析。
    """
    client, fake_cursor, _ = _make_execute_client(monkeypatch)

    client.execute("COMMENT ON COLUMN users.x IS 'FR-43 50% 門檻預警去重用'")

    fake_cursor.execute.assert_called_once_with(
        "COMMENT ON COLUMN users.x IS 'FR-43 50% 門檻預警去重用'"
    )


def test_execute_passes_params_when_provided(monkeypatch):
    client, fake_cursor, _ = _make_execute_client(monkeypatch)

    client.execute("DELETE FROM todos WHERE id = %s", params=(1,))

    fake_cursor.execute.assert_called_once_with("DELETE FROM todos WHERE id = %s", (1,))


def test_execute_commits_connection(monkeypatch):
    client, _, fake_conn = _make_execute_client(monkeypatch)

    client.execute("CREATE TABLE IF NOT EXISTS x (id serial primary key)")

    fake_conn.commit.assert_called_once()
