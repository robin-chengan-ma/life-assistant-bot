"""共用測試替身（Test Double），模擬 submodules.cloudsql.client.CloudSQLClient 的介面，
不需要真的連線 Neon，讓 src/bot/ 底下的單元測試可以純函式方式驗證邏輯。
"""
import itertools

import pytest


class FakeCloudSQLClient:
    """記憶體版的假 DB client，只實作 src/bot/ 目前會用到的 select/insert/update 行為。"""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {
            "users": [],
            "invite_codes": [],
            "feature_toggles": [],
            "knowledge_base": [],
            "conversation_logs": [],
            "conversation_summaries": [],
            "media_uploads": [],
            "todos": [],
            "mood_journals": [],
        }
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

    def delete(self, table, where, params):
        if not where:
            raise ValueError("delete() 必須提供 where 條件")
        before = len(self._tables[table])
        self._tables[table] = [row for row in self._tables[table] if not self._matches(row, where, params)]
        return before - len(self._tables[table])

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
        if where == "user_id = %s":
            return row.get("user_id") == params[0]
        if where == "user_id = %s AND deleted_at IS NULL":
            return row.get("user_id") == params[0] and row.get("deleted_at") is None
        if where == "user_id = %s AND feature_key = %s":
            return row.get("user_id") == params[0] and row.get("feature_key") == params[1]
        if where == "category = %s":
            return row.get("category") == params[0]
        if where == "category = %s AND user_id = %s":
            return row.get("category") == params[0] and row.get("user_id") == params[1]
        if where == "user_id = %s AND media_type = %s":
            return row.get("user_id") == params[0] and row.get("media_type") == params[1]
        if where == "telegram_user_id IS NOT NULL AND is_owner = FALSE":
            return row.get("telegram_user_id") is not None and row.get("is_owner") is False
        # 2026-08-02（Step 1.7，見 robinson SPEC.md FR-31/FR-31a/FR-32）：待辦事項模組的查詢條件。
        if where == "user_id = %s AND status = %s":
            return row.get("user_id") == params[0] and row.get("status") == params[1]
        if where == "status = %s AND due_at < %s":
            return row.get("status") == params[0] and row.get("due_at") < params[1]
        if where == (
            "status = %s AND remind_before_30min = %s AND reminded_30min_sent_at IS NULL "
            "AND due_at > %s AND due_at <= %s"
        ):
            return (
                row.get("status") == params[0]
                and row.get("remind_before_30min") == params[1]
                and row.get("reminded_30min_sent_at") is None
                and row.get("due_at") > params[2]
                and row.get("due_at") <= params[3]
            )
        if where == "status = %s AND due_at >= %s AND due_at < %s AND daily_pushed_on IS NULL":
            return (
                row.get("status") == params[0]
                and row.get("due_at") >= params[1]
                and row.get("due_at") < params[2]
                and row.get("daily_pushed_on") is None
            )
        # 2026-08-02（Step 1.8，見 robinson SPEC.md FR-49/FR-50）：心情小記查詢條件，只有測試用得到
        # （正式程式碼路徑只用 insert()／id 查詢，不需要這個 where，但整合測試需要驗證寫入結果）。
        if where == "user_id = %s AND mood_category = %s":
            return row.get("user_id") == params[0] and row.get("mood_category") == params[1]

        raise NotImplementedError(f"FakeCloudSQLClient 尚未支援這個 where 條件：{where}")


@pytest.fixture
def fake_db():
    return FakeCloudSQLClient()
