"""共用測試替身（Test Double），模擬 submodules.cloudsql.client.CloudSQLClient 的介面，
不需要真的連線 Neon，讓 src/bot/ 底下的單元測試可以純函式方式驗證邏輯。
"""
import itertools

import pytest


class FakeCloudSQLClient:
    """記憶體版的假 DB client，只實作 src/bot/ 目前會用到的 select/insert/update 行為。"""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {"users": [], "invite_codes": []}
        self._id_counter = itertools.count(1)

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = [row for row in self._tables[table] if self._matches(row, where, params)]
        if fetch_one:
            return dict(rows[0]) if rows else None
        return [dict(row) for row in rows]

    def insert(self, table, data, returning="id"):
        row = dict(data)
        row.setdefault("id", next(self._id_counter))
        self._tables[table].append(row)
        return row[returning]

    def update(self, table, data, where, params):
        if not where:
            raise ValueError("update() 必須提供 where 條件")
        affected = 0
        for row in self._tables[table]:
            if self._matches(row, where, params):
                row.update(data)
                affected += 1
        return affected

    def close(self):
        pass

    # --- 測試用的極簡 where 解析：只支援本專案實際會用到的幾種寫法 ---
    def _matches(self, row, where, params):
        if not where:
            return True
        params = params or ()

        if where == "telegram_user_id = %s":
            return row.get("telegram_user_id") == params[0]
        if where == "code = %s AND is_used = FALSE":
            return row.get("code") == params[0] and row.get("is_used") is False
        if where == "id = %s AND is_used = FALSE":
            return row.get("id") == params[0] and row.get("is_used") is False
        if where == "id = %s":
            return row.get("id") == params[0]

        raise NotImplementedError(f"FakeCloudSQLClient 尚未支援這個 where 條件：{where}")


@pytest.fixture
def fake_db():
    return FakeCloudSQLClient()
