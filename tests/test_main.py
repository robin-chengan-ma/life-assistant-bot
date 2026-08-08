"""main.py 的單元測試，範圍限定 Step 1.6 新增的 `_check_neon_capacity()`（FR-21）與
Step 1.7 新增的 `_check_todo_pushes()`（FR-31a、FR-32）。

main.py 其餘部分（Flask app 註冊、`_run_startup_migrations()`）沿用既有慣例，
未強制要求覆蓋率（不在 AGENTS.md／CLAUDE.md 明訂的 100% 覆蓋率範圍內），這裡只補
本次實際新增的邏輯，避免範圍蔓延。
"""
from unittest.mock import MagicMock

import main


def test_check_neon_capacity_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)

    main._check_neon_capacity()  # 不應該拋例外，直接跳過


def test_check_neon_capacity_calls_monitor_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_monitor = MagicMock()
    monkeypatch.setattr(main, "_neon_capacity_monitor", fake_monitor)

    main._check_neon_capacity()

    fake_monitor.check_and_notify.assert_called_once_with(fake_db, fake_telegram, robin_chat_id="999")
    fake_db.close.assert_called_once()


def test_check_neon_capacity_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_neon_capacity()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_todo_pushes_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_todo_pushes()  # 不應該拋例外，直接跳過


def test_check_todo_pushes_calls_todo_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_mark_overdue = MagicMock()
    fake_check_reminders = MagicMock()
    fake_check_daily = MagicMock()
    monkeypatch.setattr("src.bot.todo.mark_overdue_as_expired", fake_mark_overdue)
    monkeypatch.setattr("src.bot.todo.check_and_push_reminders", fake_check_reminders)
    monkeypatch.setattr("src.bot.todo.check_and_push_daily_digest", fake_check_daily)

    main._check_todo_pushes()

    fake_mark_overdue.assert_called_once_with(fake_db)
    fake_check_reminders.assert_called_once_with(fake_db, fake_telegram)
    fake_check_daily.assert_called_once_with(fake_db, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_todo_pushes_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_todo_pushes()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_body_goal_alerts_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_body_goal_alerts()  # 不應該拋例外，直接跳過


def test_check_body_goal_alerts_calls_body_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_check_exercise = MagicMock()
    fake_check_deadline = MagicMock()
    monkeypatch.setattr("src.bot.body.check_and_push_exercise_goal_achievements", fake_check_exercise)
    monkeypatch.setattr("src.bot.body.check_and_push_goal_deadline_reminders", fake_check_deadline)

    main._check_body_goal_alerts()

    fake_check_exercise.assert_called_once_with(fake_db, fake_telegram, calendar_client=None)
    fake_check_deadline.assert_called_once_with(fake_db, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_body_goal_alerts_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_body_goal_alerts()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_important_notifications_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_important_notifications()  # 不應該拋例外，直接跳過


def test_check_important_notifications_calls_notifications_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_check_notifications = MagicMock()
    monkeypatch.setattr(
        "src.bot.notifications.check_and_push_important_notifications", fake_check_notifications
    )

    main._check_important_notifications()

    fake_check_notifications.assert_called_once_with(fake_db, fake_telegram, calendar_client=None)
    fake_db.close.assert_called_once()


def test_check_important_notifications_passes_calendar_client_when_env_vars_set(monkeypatch):
    # 2026-08-05（FR-66b、ADR-17）：GOOGLE_CALENDAR_* 四個環境變數都設定時，要建立 CalendarClient
    # 並傳給 notifications 模組。
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN", "fake-refresh")
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "fake-calendar-id")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))
    fake_calendar = MagicMock()
    fake_calendar_client_cls = MagicMock(return_value=fake_calendar)
    monkeypatch.setattr("submodules.calendar.client.CalendarClient", fake_calendar_client_cls)

    fake_check_notifications = MagicMock()
    monkeypatch.setattr(
        "src.bot.notifications.check_and_push_important_notifications", fake_check_notifications
    )

    main._check_important_notifications()

    fake_calendar_client_cls.assert_called_once_with(
        refresh_token="fake-refresh", client_id="fake-client-id",
        client_secret="fake-client-secret", calendar_id="fake-calendar-id",
    )
    fake_check_notifications.assert_called_once_with(fake_db, fake_telegram, calendar_client=fake_calendar)


def test_check_important_notifications_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_important_notifications()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_skill_growth_collection_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("GEMINI_API_SKILL_GROWTH_KEY", raising=False)

    main._check_skill_growth_collection()  # 不應該拋例外，直接跳過


def test_check_skill_growth_collection_skips_when_only_gemini_key_missing(monkeypatch):
    # DB/Gmail 都設定齊全，但缺這個功能專屬的 Gemini Key 時，同樣要優雅跳過。
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "fake-app-password")
    monkeypatch.delenv("GEMINI_API_SKILL_GROWTH_KEY", raising=False)

    main._check_skill_growth_collection()  # 不應該拋例外，直接跳過


def test_check_skill_growth_collection_calls_skill_growth_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "fake-app-password")
    monkeypatch.setenv("GEMINI_API_SKILL_GROWTH_KEY", "fake-gemini-key")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_email = MagicMock()
    fake_email_cls = MagicMock(return_value=fake_email)
    monkeypatch.setattr("submodules.email.client.EmailClient", fake_email_cls)
    fake_newsfeed = MagicMock()
    monkeypatch.setattr("submodules.newsfeed.client.NewsFeedClient", MagicMock(return_value=fake_newsfeed))
    fake_llm = MagicMock()
    fake_llm_cls = MagicMock(return_value=fake_llm)
    monkeypatch.setattr("submodules.llm.client.LLMClient", fake_llm_cls)

    fake_collect = MagicMock()
    monkeypatch.setattr("src.bot.skill_growth.collect_and_store_daily_digest", fake_collect)

    main._check_skill_growth_collection()

    fake_email_cls.assert_called_once_with(username="you@gmail.com", password="fake-app-password")
    fake_llm_cls.assert_called_once_with(api_key="fake-gemini-key")
    fake_collect.assert_called_once_with(fake_db, fake_email, fake_newsfeed, fake_llm)
    fake_db.close.assert_called_once()


def test_check_skill_growth_collection_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "fake-app-password")
    monkeypatch.setenv("GEMINI_API_SKILL_GROWTH_KEY", "fake-gemini-key")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.email.client.EmailClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_skill_growth_collection()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_skill_growth_push_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_skill_growth_push()  # 不應該拋例外，直接跳過


def test_check_skill_growth_push_calls_skill_growth_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_push = MagicMock()
    monkeypatch.setattr("src.bot.skill_growth.check_and_push_daily_digest", fake_push)

    main._check_skill_growth_push()

    fake_push.assert_called_once_with(fake_db, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_skill_growth_push_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_skill_growth_push()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_certificate_daily_quiz_push_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_certificate_daily_quiz_push()  # 不應該拋例外，直接跳過


def test_check_certificate_daily_quiz_push_calls_certificate_quiz_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_push = MagicMock()
    monkeypatch.setattr("src.bot.certificate_quiz.check_and_push_daily_quiz", fake_push)

    main._check_certificate_daily_quiz_push()

    fake_push.assert_called_once_with(fake_db, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_certificate_daily_quiz_push_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_certificate_daily_quiz_push()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_certificate_answer_reminder_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    main._check_certificate_answer_reminder()  # 不應該拋例外，直接跳過


def test_check_certificate_answer_reminder_calls_certificate_answer_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_check = MagicMock()
    monkeypatch.setattr("src.bot.certificate_answer.check_and_push_answer_reminders", fake_check)

    main._check_certificate_answer_reminder()

    fake_check.assert_called_once_with(fake_db, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_certificate_answer_reminder_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.telegram.client.TelegramClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_certificate_answer_reminder()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_check_youtube_weekly_push_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_SKILL_GROWTH_KEY", raising=False)

    main._check_youtube_weekly_push()  # 不應該拋例外，直接跳過


def test_check_youtube_weekly_push_calls_youtube_module_when_env_vars_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-youtube-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_SKILL_GROWTH_KEY", "fake-gemini-key")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    fake_youtube_client = MagicMock()
    monkeypatch.setattr("submodules.youtube.client.YouTubeClient", MagicMock(return_value=fake_youtube_client))
    fake_llm_client = MagicMock()
    monkeypatch.setattr("submodules.llm.client.LLMClient", MagicMock(return_value=fake_llm_client))
    fake_telegram = MagicMock()
    monkeypatch.setattr("submodules.telegram.client.TelegramClient", MagicMock(return_value=fake_telegram))

    fake_push = MagicMock()
    monkeypatch.setattr("src.bot.youtube.check_and_push_weekly_youtube", fake_push)

    main._check_youtube_weekly_push()

    fake_push.assert_called_once_with(fake_db, fake_youtube_client, fake_llm_client, fake_telegram)
    fake_db.close.assert_called_once()


def test_check_youtube_weekly_push_swallows_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-youtube-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_SKILL_GROWTH_KEY", "fake-gemini-key")

    fake_db = MagicMock()
    monkeypatch.setattr("submodules.cloudsql.client.CloudSQLClient", MagicMock(return_value=fake_db))
    monkeypatch.setattr(
        "submodules.youtube.client.YouTubeClient", MagicMock(side_effect=RuntimeError("boom"))
    )

    main._check_youtube_weekly_push()  # 不應該往外拋

    fake_db.close.assert_called_once()


def test_healthz_endpoint_still_returns_ok(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("GEMINI_API_SKILL_GROWTH_KEY", raising=False)

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


# --- 2026-08-08（production 事故修復）：/healthz 改成背景執行緒跑檢查，不阻塞 HTTP 回應 ---

_HEALTH_CHECK_NAMES = (
    "_check_neon_capacity",
    "_check_todo_pushes",
    "_check_finance_alerts",
    "_check_finance_reminders",
    "_check_finance_monthly_report",
    "_check_body_goal_alerts",
    "_check_important_notifications",
    "_check_skill_growth_collection",
    "_check_toeic_pipeline",
    "_check_skill_growth_push",
    "_check_certificate_daily_quiz_push",
    "_check_certificate_answer_reminder",
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
    for name in _HEALTH_CHECK_NAMES:
        monkeypatch.setattr(main, name, MagicMock())

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_healthz_dispatches_all_checks_via_background_thread(monkeypatch):
    monkeypatch.setattr(main.threading, "Thread", _ImmediateThread)
    fakes = {name: MagicMock() for name in _HEALTH_CHECK_NAMES}
    for name, fake in fakes.items():
        monkeypatch.setattr(main, name, fake)

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    for fake in fakes.values():
        fake.assert_called_once()


def test_healthz_thread_is_started_as_daemon(monkeypatch):
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
