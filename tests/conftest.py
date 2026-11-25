"""全專案共用測試設定。

這個 sandbox 的系統 Python 是 3.10（沒有 datetime.UTC，3.11 才新增的別名），但 repo 其餘
程式碼／ruff 設定都假設正式環境是 3.11+，一律用 `datetime.UTC`。補一個相容 shim，讓測試在
這個 sandbox 也能正常 import／執行，不影響正式環境行為（正式環境本來就有 `datetime.UTC`，
這行只是 no-op）。比照 tests/bot/conftest.py 既有做法，搬到頂層讓全專案（不只 tests/bot）
在這個 sandbox 都能正常 collect。
"""
import datetime as _datetime_module

if not hasattr(_datetime_module, "UTC"):
    _datetime_module.UTC = _datetime_module.timezone.utc  # noqa: UP017
