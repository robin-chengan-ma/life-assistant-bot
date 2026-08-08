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
            "complaints": [],
            "transactions": [],
            "budget_overrides": [],
            "body_weight_logs": [],
            "exercise_logs": [],
            "diet_logs": [],
            "body_goals": [],
            "important_notifications_log": [],
            "skill_growth_digests": [],
            "certificate_questions": [],
            "toeic_vocab_questions": [],
            "answer_logs": [],
            "certificate_goals": [],
            "exam_official_scores": [],
            "certificate_daily_settings": [],
            "certificate_daily_schedule_overrides": [],
            "certificate_daily_assignments": [],
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
        # 2026-08-02 追加（見 robinson SPEC.md FR-31b，區間待辦事項）：提醒基準時間改用
        # COALESCE(start_at, due_at)，區間待辦以 start_at 為準、單一時間點待辦仍以 due_at 為準。
        if where == (
            "status = %s AND remind_before_30min = %s AND reminded_30min_sent_at IS NULL "
            "AND COALESCE(start_at, due_at) > %s AND COALESCE(start_at, due_at) <= %s"
        ):
            anchor = row.get("start_at") or row.get("due_at")
            return (
                row.get("status") == params[0]
                and row.get("remind_before_30min") == params[1]
                and row.get("reminded_30min_sent_at") is None
                and anchor > params[2]
                and anchor <= params[3]
            )
        # 2026-08-02 追加（見 robinson SPEC.md FR-31b）：每日摘要改為「今天到期」或「今天開始」皆算，
        # 去重也從「曾經推播過」改為「今天是否已推播過」，讓區間待辦能在開始日/結束日各推播一次。
        if where == (
            "status = %s AND ((due_at >= %s AND due_at < %s) OR (start_at >= %s AND start_at < %s)) "
            "AND (daily_pushed_on IS NULL OR daily_pushed_on != %s)"
        ):
            due_at = row.get("due_at")
            start_at = row.get("start_at")
            due_today = due_at is not None and params[1] <= due_at < params[2]
            starts_today = start_at is not None and params[3] <= start_at < params[4]
            pushed_today = row.get("daily_pushed_on") is not None and row.get("daily_pushed_on") == params[5]
            return row.get("status") == params[0] and (due_today or starts_today) and not pushed_today
        # 2026-08-02（Step 1.8，見 robinson SPEC.md FR-49/FR-50）：心情小記查詢條件，只有測試用得到
        # （正式程式碼路徑只用 insert()／id 查詢，不需要這個 where，但整合測試需要驗證寫入結果）。
        if where == "user_id = %s AND mood_category = %s":
            return row.get("user_id") == params[0] and row.get("mood_category") == params[1]
        # 2026-08-02（Step 1.9，見 robinson SPEC.md FR-60~FR-63）：客訴流程查 Robin 的 users 記錄。
        if where == "is_owner = %s":
            return row.get("is_owner") == params[0]
        # 2026-08-04（Step 2.1，見 robinson SPEC.md FR-42/FR-43/FR-44）：記帳模組的月加總查詢。
        if where == "user_id = %s AND type = %s AND transaction_date >= %s AND transaction_date < %s":
            return (
                row.get("user_id") == params[0]
                and row.get("type") == params[1]
                and row.get("transaction_date") >= params[2]
                and row.get("transaction_date") < params[3]
            )
        # 2026-08-04（Step 2.1，見 robinson SPEC.md FR-43）：找出所有已設定預算上限的使用者。
        if where == "monthly_budget IS NOT NULL":
            return row.get("monthly_budget") is not None
        # 2026-08-04 追加（記帳擴充，見 robinson SPEC.md FR-41a）：預算特殊月份覆蓋查詢。
        if where == "user_id = %s AND year = %s AND month = %s":
            return row.get("user_id") == params[0] and row.get("year") == params[1] and row.get("month") == params[2]
        if where == "year = %s AND month = %s":
            return row.get("year") == params[0] and row.get("month") == params[1]
        # 2026-08-04 追加（記帳擴充，見 robinson SPEC.md FR-42a）：查詢某使用者今天是否已有支出紀錄。
        if where == "user_id = %s AND type = %s AND transaction_date = %s":
            return (
                row.get("user_id") == params[0]
                and row.get("type") == params[1]
                and row.get("transaction_date") == params[2]
            )
        # 2026-08-04 追加（記帳擴充，見 robinson SPEC.md FR-44a）：查詢這個月所有記帳交易（不篩 user_id），
        # 供月報推播找出「這個月有記帳」的候選使用者。
        if where == "transaction_date >= %s AND transaction_date < %s":
            return row.get("transaction_date") >= params[0] and row.get("transaction_date") < params[1]
        # 2026-08-04（Step 2.2，見 robinson SPEC.md FR-45~FR-48）：體態管理模組的查詢條件。
        if where == "user_id = %s AND goal_type = %s AND status = %s":
            return (
                row.get("user_id") == params[0]
                and row.get("goal_type") == params[1]
                and row.get("status") == params[2]
            )
        if where == "goal_type = %s AND status = %s":
            return row.get("goal_type") == params[0] and row.get("status") == params[1]
        if where == "user_id = %s AND entry_date >= %s":
            return row.get("user_id") == params[0] and row.get("entry_date") >= params[1]
        if where == "status = %s AND target_date IS NOT NULL":
            return row.get("status") == params[0] and row.get("target_date") is not None
        # 2026-08-04（Step 2.3，見 robinson SPEC.md FR-53）：重要通知模組的查詢條件。
        if where == "telegram_user_id IS NOT NULL":
            return row.get("telegram_user_id") is not None
        if where == "birthday IS NOT NULL":
            return row.get("birthday") is not None
        if where == "notification_key = %s AND year = %s":
            return row.get("notification_key") == params[0] and row.get("year") == params[1]
        # 2026-08-07（Step 3.1，見 robinson SPEC.md FR-22）：每日技術摘要查 Robin 的 users 記錄。
        if where == "is_owner = %s AND telegram_user_id IS NOT NULL":
            return row.get("is_owner") == params[0] and row.get("telegram_user_id") is not None
        # 2026-08-07（Step 3.1 修正，見 robinson SPEC.md FR-22/FR-23）：每日技術摘要收集/推播查詢。
        if where == "digest_date = %s":
            return row.get("digest_date") == params[0]
        # 2026-08-07（Step 3.2，見 robinson SPEC.md FR-25a~FR-25f）：TOEIC 題庫 Pipeline 去重查詢。
        if where == "source_image_filename = %s":
            return row.get("source_image_filename") == params[0]
        # 2026-08-07（Step 3.3，見 robinson SPEC.md FR-27、ADR-19）：答案照片比對與去重查詢。
        if where == "answer_source_filename = %s":
            return row.get("answer_source_filename") == params[0]
        if where == "exam_type = %s AND test_id = %s AND question_type = %s AND question_number = %s":
            return (
                row.get("exam_type") == params[0]
                and row.get("test_id") == params[1]
                and row.get("question_type") == params[2]
                and row.get("question_number") == params[3]
            )
        # 2026-08-08（Step 3.3，見 robinson SPEC.md FR-26~FR-28、ADR-20）：每日推播出題查詢。
        if where == "user_id = %s AND exam_type = %s":
            return row.get("user_id") == params[0] and row.get("exam_type") == params[1]
        if where == "user_id = %s AND exam_type = %s AND assigned_date = %s":
            return (
                row.get("user_id") == params[0]
                and row.get("exam_type") == params[1]
                and row.get("assigned_date") == params[2]
            )
        if where == "user_id = %s AND exam_type = %s AND correct_answer IS NOT NULL":
            return (
                row.get("user_id") == params[0]
                and row.get("exam_type") == params[1]
                and row.get("correct_answer") is not None
            )
        if where == "exam_type = %s AND correct_answer IS NOT NULL":
            return row.get("exam_type") == params[0] and row.get("correct_answer") is not None
        if where == "exam_type = %s AND question_type = %s AND correct_answer IS NOT NULL":
            return (
                row.get("exam_type") == params[0]
                and row.get("question_type") == params[1]
                and row.get("correct_answer") is not None
            )
        if where == "user_id = %s AND exam_type = %s AND certificate_question_id IS NOT NULL":
            return (
                row.get("user_id") == params[0]
                and row.get("exam_type") == params[1]
                and row.get("certificate_question_id") is not None
            )
        if where == "user_id = %s AND exam_type = %s AND question_type = %s AND certificate_question_id IS NOT NULL":
            return (
                row.get("user_id") == params[0]
                and row.get("exam_type") == params[1]
                and row.get("question_type") == params[2]
                and row.get("certificate_question_id") is not None
            )
        if where == "user_id = %s AND exam_type = %s AND question_type = %s AND vocab_question_id IS NOT NULL":
            return (
                row.get("user_id") == params[0]
                and row.get("exam_type") == params[1]
                and row.get("question_type") == params[2]
                and row.get("vocab_question_id") is not None
            )

        raise NotImplementedError(f"FakeCloudSQLClient 尚未支援這個 where 條件：{where}")


@pytest.fixture
def fake_db():
    return FakeCloudSQLClient()
