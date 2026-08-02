"""submodules/cloudsql/client.py 的單元測試。

2026-08-02（Step 1.6，見 robinson SPEC.md FR-21）：cloudsql 的既有方法（select/insert/
update/delete/execute）仍如 submodules-core SPEC.md Step S.6 所述「待對應功能實際串接時
補上」，這裡只補新增的 `execute_query()`（`src/bot/monitoring.py` 監控 Neon 容量會用到），
不回頭補齊既有方法的測試，範圍對應本次實際新增的程式碼。

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
    fake_cursor.execute.assert_called_once_with(
        "SELECT pg_database_size(current_database()) AS size_bytes", ()
    )


def test_execute_query_passes_params(monkeypatch):
    client, fake_cursor, _ = _make_client(monkeypatch, fetch_result=[])

    client.execute_query("SELECT 1 WHERE %s = %s", params=(1, 1))

    fake_cursor.execute.assert_called_once_with("SELECT 1 WHERE %s = %s", (1, 1))


def test_execute_query_commits_and_returns_connection(monkeypatch):
    client, _, fake_conn = _make_client(monkeypatch, fetch_result=[])

    client.execute_query("SELECT 1")

    fake_conn.commit.assert_called_once()
