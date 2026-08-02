"""main.py 的單元測試，範圍限定 Step 1.6 新增的 `_check_neon_capacity()`（FR-21）。

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


def test_healthz_endpoint_still_returns_ok(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)

    client = main.app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
