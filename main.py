import logging
import os

from flask import Flask, jsonify

from src.bot import monitoring
from src.bot.webhook import bot_bp

# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-19a）：加上 asctime，滿足「完整記錄...時間戳記」
# 的要求；原本的預設格式（level+name+message）沒有時間，出事後光看 log 沒辦法知道確切發生時刻。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("robinson.main")

app = Flask(__name__)
app.register_blueprint(bot_bp)

# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-21）：Neon 容量監控狀態，process 生命週期內
# 共用一份（比照 webhook.py `_state_store` 的既有慣例），見 src/bot/monitoring.py 模組 docstring。
_neon_capacity_monitor = monitoring.NeonCapacityMonitor()


def _check_neon_capacity() -> None:
    """在 /healthz 被 cron-job.org 呼叫（每 10 分鐘一次）時順便檢查 Neon 容量（FR-21）。

    刻意包一層 try/except：健康檢查端點本身絕對不能因為監控邏輯出錯而回傳失敗，
    否則 cron-job.org 會誤判服務下線；沒設定 DATABASE_URL／TELEGRAM_BOT_TOKEN／
    ROBIN_TELEGRAM_TOKEN（本機測試環境常見）時直接跳過，不視為錯誤。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")
            and os.environ.get("ROBIN_TELEGRAM_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        _neon_capacity_monitor.check_and_notify(
            db, telegram_client, robin_chat_id=os.environ["ROBIN_TELEGRAM_TOKEN"]
        )
    except Exception:
        logger.exception("Neon 容量監控檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_todo_pushes() -> None:
    """在 /healthz 被呼叫時順便處理待辦事項的自動化邏輯（Step 1.7，見 robinson SPEC.md FR-31a、
    FR-32）：①把逾期的 pending 待辦標記為 expired ②推播「預定時間前 30 分鐘」提醒 ③台灣時間
    08 點推播當天待辦摘要，見 src/bot/todo.py 模組 docstring 的完整說明。

    跟 `_check_neon_capacity()` 一樣包一層 try/except，不能因為這裡出錯就讓 `/healthz` 回傳失敗；
    沒設定 DATABASE_URL／TELEGRAM_BOT_TOKEN 時直接跳過（本機測試環境常見）。這裡不像
    `_check_neon_capacity()` 需要 `ROBIN_TELEGRAM_TOKEN`——待辦事項是推播給每一位有待辦的使用者
    自己（依 todos.user_id 查對應的 users.telegram_user_id），不是固定通知 Robin。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import todo

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        todo.mark_overdue_as_expired(db)
        todo.check_and_push_reminders(db, telegram_client)
        todo.check_and_push_daily_digest(db, telegram_client)
    except Exception:
        logger.exception("待辦事項推播檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_finance_alerts() -> None:
    """在 /healthz 被呼叫時順便檢查記帳預算門檻預警（Step 2.1，見 robinson SPEC.md FR-43）：
    50% 門檻只在每月 15 日（含）以前檢查、80% 門檻整月都檢查，各自每月最多推播一次，
    詳見 src/bot/finance.py 模組 docstring 的完整說明。

    跟 `_check_todo_pushes()` 一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`
    （推播對象是每一位有設定預算的使用者自己，不是固定通知 Robin）。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import finance

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        finance.check_and_push_budget_alerts(db, telegram_client)
    except Exception:
        logger.exception("記帳預算門檻預警檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_finance_reminders() -> None:
    """在 /healthz 被呼叫時順便檢查每日記帳提醒（記帳模組擴充，見 robinson SPEC.md FR-42a）：
    台灣時間 23:00，對「這個月有生效預算、今天還沒記過支出、今天還沒推播過」的使用者各推播一次，
    詳見 src/bot/finance.py 模組 docstring 決策⑥。

    跟 `_check_finance_alerts()` 一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import finance

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        finance.check_and_push_finance_reminders(db, telegram_client)
    except Exception:
        logger.exception("每日記帳提醒檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_finance_monthly_report() -> None:
    """在 /healthz 被呼叫時順便檢查月底自動月報推播（記帳模組擴充，見 robinson SPEC.md FR-44a）：
    每月最後一天台灣時間 21:00，對「這個月有生效預算或有記帳」的使用者各推播一次月報，
    詳見 src/bot/finance.py 模組 docstring 決策⑦。

    跟 `_check_finance_reminders()` 一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import finance

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        finance.check_and_push_monthly_report(db, telegram_client)
    except Exception:
        logger.exception("月底記帳月報推播檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_body_goal_alerts() -> None:
    """在 /healthz 被呼叫時順便檢查體態目標的兩種排程型預警（Step 2.2，見 robinson SPEC.md
    FR-45）：①運動目標累積分鐘數達成通知（體重目標則是記錄體重當下即時檢查，不需要排程）
    ②目標期限前 7 天提醒，詳見 src/bot/body.py 模組 docstring 決策③。

    跟 `_check_finance_alerts()` 一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`
    （推播對象是每一位有設定體態目標的使用者自己，不是固定通知 Robin）。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import body

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        body.check_and_push_exercise_goal_achievements(
            db, telegram_client, calendar_client=_build_calendar_client()
        )
        body.check_and_push_goal_deadline_reminders(db, telegram_client)
    except Exception:
        logger.exception("體態目標預警檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _build_calendar_client():
    """建立 Google Calendar 同步用的 CalendarClient（見 robinson SPEC.md FR-66、ADR-17）。

    跟 `src/bot/webhook.py` 的同名 helper 是同一個設計，各自獨立實作一份（比照 `_now()` 等
    小工具函式在多個模組各自定義一份的既有慣例，避免模組間互相依賴對方的私有成員）：
    `GOOGLE_CALENDAR_*` 四個環境變數還沒設定完整時回傳 `None`，
    `notifications.check_and_push_important_notifications()` 會優雅降級成只推播 Telegram、
    不建立 Calendar 事件。
    """
    refresh_token = os.environ.get("GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET")
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not (refresh_token and client_id and client_secret and calendar_id):
        return None

    from submodules.calendar.client import CalendarClient

    return CalendarClient(
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret, calendar_id=calendar_id,
    )


def _check_important_notifications() -> None:
    """在 /healthz 被呼叫時順便檢查重要通知（Step 2.3，見 robinson SPEC.md FR-53）：固定節日
    （元旦/除夕/初一/掃墓提醒/中秋/端午/父親節/母親節）與家人生日，固定台灣時間 08:00 推播，
    詳見 src/bot/notifications.py 模組 docstring。

    跟 `_check_body_goal_alerts()` 一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`
    （推播對象是所有已綁定的使用者，不是固定通知 Robin 一人）。

    2026-08-05（見 FR-66b、ADR-17）：額外注入 `calendar_client`，通過判斷的節日/生日同時建立
    Google Calendar 全天事件，`_build_calendar_client()` 回傳 `None` 時優雅降級。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    from src.bot import notifications

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        notifications.check_and_push_important_notifications(
            db, telegram_client, calendar_client=_build_calendar_client()
        )
    except Exception:
        logger.exception("重要通知檢查失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _run_startup_migrations() -> None:
    """開機自動套用尚未執行過的 DB migration（ADR-11）。

    刻意不讓 migration 失敗直接讓整個 process 掛掉退出：/healthz 必須維持存活讓
    cron-job.org 的 keep-alive 探測不會誤判服務完全down，錯誤改用 log 記錄，等
    Phase 1 Step 1.6 的錯誤通報機制上線後會私訊告知 Robin。若沒有設定 DATABASE_URL
    （例如本機測試環境），直接跳過，不視為錯誤。
    """
    if not os.environ.get("DATABASE_URL"):
        logger.info("未設定 DATABASE_URL，略過 migration 步驟")
        return

    from src.migrations.runner import run_pending_migrations
    from submodules.cloudsql.client import CloudSQLClient

    db = CloudSQLClient()
    try:
        applied = run_pending_migrations(db)
        if applied:
            logger.info("已套用 %d 筆 migration：%s", len(applied), applied)
    except Exception:
        logger.exception("Migration 執行失敗，app 仍會啟動，但資料庫 schema 可能不是最新狀態")
    finally:
        db.close()


@app.route("/")
def root():
    return "Robinson is alive.", 200


@app.route("/healthz")
def health_check():
    """極簡健康檢查端點，供 cron-job.org 每 10 分鐘呼叫一次，避免 Render 免費方案休眠。

    對應 FR-3 / docs/specs/robinson/SPEC.md，路由定義見 src/schema/api_schema.md。

    2026-08-02（Step 1.6，見 FR-21）：順便觸發 Neon 容量檢查，借用 cron-job.org 既有的
    每 10 分鐘呼叫頻率，不需要額外的排程機制。

    2026-08-02（Step 1.7，見 FR-31a、FR-32）：同樣借用這個頻率，順便觸發待辦事項的逾期標記與
    兩種推播檢查，見 `_check_todo_pushes()`。

    2026-08-04（Step 2.1，見 FR-43）：同樣借用這個頻率，順便觸發記帳預算門檻預警檢查，
    見 `_check_finance_alerts()`。

    2026-08-04（記帳模組擴充，見 FR-42a）：同樣借用這個頻率，順便觸發每日記帳提醒檢查，
    見 `_check_finance_reminders()`。

    2026-08-04（記帳模組擴充，見 FR-44a）：同樣借用這個頻率，順便觸發月底記帳月報推播檢查，
    見 `_check_finance_monthly_report()`。

    2026-08-04（Step 2.2，見 FR-45）：同樣借用這個頻率，順便觸發體態目標的運動目標達成通知與
    期限將近提醒檢查，見 `_check_body_goal_alerts()`。

    2026-08-04（Step 2.3，見 FR-53）：同樣借用這個頻率，順便觸發重要通知（固定節日/家人生日）
    檢查，見 `_check_important_notifications()`。
    """
    _check_neon_capacity()
    _check_todo_pushes()
    _check_finance_alerts()
    _check_finance_reminders()
    _check_finance_monthly_report()
    _check_body_goal_alerts()
    _check_important_notifications()
    return jsonify({"status": "ok"}), 200


_run_startup_migrations()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)