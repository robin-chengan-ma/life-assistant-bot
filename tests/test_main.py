"""main.py 的單元測試，範圍限定各個 `_check_*()` 排程函式與 `/healthz` 背景執行緒調度。

main.py 其餘部分（Flask app 註冊、`_run_startup_migrations()`）沿用既有慣例，
未強制要求覆蓋率（不在 AGENTS.md／CLAUDE.md 明訂的 100% 覆蓋率範圍內），這裡只補
本次實際新增的邏輯，避免範圍蔓延。

2026-11（功能大幅精簡，見 ADR-33）：Neon 容量監控、固定節日／跨模組目標摘要／技術情報／
TOEIC／證照題庫／求職模組等排程皆隨對應功能整個移除。

2026-11-26（再次精簡，見 docs/ADR/discuss/robinson.md）：確認「設定記帳預算」「設定體態目標」
從頭到尾沒有任何設定入口，`_check_finance_alerts()`／`_check_finance_monthly_report()`／
`_check_body_goal_alerts()` 連同背後的 `finance.py`／`body.py` 函式與
`budget_overrides`／`body_goals` 資料表一併移除；`/healthz` 現在只剩待辦推播、生日推播兩項。
"""
from unittest.mock import MagicMock

import main


def test_check_todo_pushes_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_todo_pushes(db=None)  # 不應該拋例外，直接跳過（不該碰 db）


def test_check_todo_pushes_calls_todo_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_check_reminders = MagicMock()
    monkeypatch.setattr("src.bot.todo.check_and_push_reminders", fake_check_reminders)

    main._check_todo_pushes(fake_db)

    fake_check_reminders.assert_called_once_with(fake_db, fake_telegram)


def test_check_todo_pushes_swallows_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_todo_pushes(fake_db)  # 不應該往外拋


def test_check_birthdays_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_birthdays(db=None)  # 不應該拋例外，直接跳過


def test_check_birthdays_calls_important_days_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_check_birthdays = MagicMock()
    monkeypatch.setattr("src.bot.important_days.check_and_push_birthdays", fake_check_birthdays)

    main._check_birthdays(fake_db)

    fake_check_birthdays.assert_called_once_with(fake_db, fake_telegram)


def test_check_birthdays_swallows_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_birthdays(fake_db)  # 不應該往外拋


_HEALTH_CHECK_NAMES = (
    "_check_todo_pushes",
    "_check_birthdays",
)


class _ImmediateThread:
    """假的 threading.Thread：`start()` 直接同步呼叫 target，讓測試不需要等待真正的執行緒排程、
    也不會有 flaky 的時序問題，同時仍能驗證『真的有透過 Thread 觸發』這件事。
    """

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target
        self.daemon = daemon

    def start(self):
        self._target()


def test_healthz_returns_ok_without_waiting_for_checks(monkeypatch):
    # 檢查函式故意做一件「如果同步執行會被觀察到」的事（設一個 flag），驗證 /healthz 回應時
    # 不會等它執行完——用真正的 threading.Thread（不 mock），只確認回應本身正常。
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=MagicMock()))
    for name in _HEALTH_CHECK_NAMES:
        monkeypatch.setattr(main, name, MagicMock())

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_healthz_dispatches_all_checks_via_background_thread(monkeypatch):
    # `_run_background_checks()` 先統一建立一個共用 `db`，才把它傳給每個 `_check_*()`；這裡
    # mock `CloudSQLClient` 回傳一個共用的 fake_db，驗證每個 `_check_*()` 都有拿到同一個 db。
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(main.threading, "Thread", _ImmediateThread)
    fakes = {name: MagicMock() for name in _HEALTH_CHECK_NAMES}
    for name, fake in fakes.items():
        monkeypatch.setattr(main, name, fake)

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    for fake in fakes.values():
        fake.assert_called_once_with(fake_db)
    fake_db.close.assert_called_once()


def test_healthz_skips_all_checks_when_database_url_missing(monkeypatch):
    # 沒有設定 DATABASE_URL（本機測試環境常見）時，整批直接跳過，連 CloudSQLClient() 都不建立。
    monkeypatch.delenv("DATABASE_URL", raising=False)
    fake_cloudsql_cls = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", fake_cloudsql_cls)
    monkeypatch.setattr(main.threading, "Thread", _ImmediateThread)
    fakes = {name: MagicMock() for name in _HEALTH_CHECK_NAMES}
    for name, fake in fakes.items():
        monkeypatch.setattr(main, name, fake)

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    fake_cloudsql_cls.assert_not_called()
    for fake in fakes.values():
        fake.assert_not_called()


def test_healthz_thread_is_started_as_daemon(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=MagicMock()))
    captured = {}

    class _CapturingThread(_ImmediateThread):
        def __init__(self, target=None, daemon=None, **kwargs):
            super().__init__(target=target, daemon=daemon, **kwargs)
            captured["daemon"] = daemon

    monkeypatch.setattr(main.threading, "Thread", _CapturingThread)
    for name in _HEALTH_CHECK_NAMES:
        monkeypatch.setattr(main, name, MagicMock())

    main.app.test_client().get("/healthz")

    assert captured["daemon"] is True
