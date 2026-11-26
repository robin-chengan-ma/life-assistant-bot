import logging
import os
import threading

from flask import Flask, jsonify

from src.api.app_analytics import app_analytics_bp
from src.api.app_auth import app_bp
from src.api.app_calendar import app_calendar_bp
from src.api.app_important_days import app_important_days_bp
from src.api.app_todo import app_todo_bp
from src.bot.webhook import bot_bp

# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-19a）：加上 asctime，滿足「完整記錄...時間戳記」
# 的要求；原本的預設格式（level+name+message）沒有時間，出事後光看 log 沒辦法知道確切發生時刻。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("robinson.main")

app = Flask(__name__)
app.register_blueprint(app_analytics_bp)
app.register_blueprint(app_bp)
app.register_blueprint(app_calendar_bp)
app.register_blueprint(app_important_days_bp)
app.register_blueprint(app_todo_bp)
app.register_blueprint(bot_bp)


def _check_todo_pushes(db) -> None:
    """在 /healthz 被呼叫時順便推播到期的待辦提醒（2026-11 功能大幅精簡，見 ADR-33、
    robinson SPEC.md FR-31／FR-32）：待辦事項已簡化成純粹的一次性「日期＋文字」提醒，不再有
    pending/expired 狀態、30 分鐘前預告或每日摘要，詳見 src/bot/todo.py 模組 docstring。

    跟其他檢查一樣包一層 try/except，不能因為這裡出錯就讓 `/healthz` 回傳失敗；
    沒設定 TELEGRAM_BOT_TOKEN 時直接跳過（本機測試環境常見）。這裡不像其他檢查需要
    `ROBIN_TELEGRAM_TOKEN`——待辦事項是推播給每一位有待辦的使用者自己（依 todos.user_id 查對應的
    users.telegram_user_id），不是固定通知 Robin。`db` 共用連線，見 `_run_background_checks()`。
    """
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return

    from src.bot import todo
    from submodules.telegram.client import TelegramClient

    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        todo.check_and_push_reminders(db, telegram_client)
    except Exception:
        logger.exception("待辦事項推播檢查失敗，不影響健康檢查端點本身")


# 2026-11-26：`_check_finance_alerts()`／`_check_finance_monthly_report()`／
# `_check_body_goal_alerts()` 已確認背後的「設定記帳預算」「設定體態目標」功能從頭到尾沒有任何
# 設定入口（純死碼），連同 `finance.py`／`body.py` 的對應函式與 `budget_overrides`／`body_goals`
# 資料表一併移除，見 docs/ADR/discuss/robinson.md。


def _check_birthdays(db) -> None:
    """在 /healthz 被呼叫時順便檢查生日推播（2026-11 精簡後「重要日子」改名為「生日設定」，
    取代原本固定節日＋重要日子的 `notifications.py`／`scheduled_notifications.py`），詳見
    src/bot/important_days.py 模組 docstring。

    跟其他檢查一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`（推播對象是所有已綁定的
    使用者）。`db` 共用連線，見 `_run_background_checks()`。
    """
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return

    from src.bot import important_days
    from submodules.telegram.client import TelegramClient

    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        important_days.check_and_push_birthdays(db, telegram_client)
    except Exception:
        logger.exception("生日推播檢查失敗，不影響健康檢查端點本身")


def _check_national_holidays(db) -> None:
    """在 /healthz 被呼叫時順便檢查固定節日推播（2026-11-26，Robin 要求補回父親節／母親節／
    中秋節／端午節提醒，見 src/bot/national_holidays.py 模組 docstring）。

    跟其他檢查一樣包一層 try/except 且不需要 `ROBIN_TELEGRAM_TOKEN`（推播對象是全體已綁定的
    使用者，這些是全家共用的固定節日，不是個人設定）。`db` 共用連線，見 `_run_background_checks()`。
    """
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return

    from src.bot import national_holidays
    from submodules.telegram.client import TelegramClient

    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        national_holidays.check_and_push_fixed_holidays(db, telegram_client)
        national_holidays.check_and_push_lunar_holidays(db, telegram_client)
    except Exception:
        logger.exception("固定節日推播檢查失敗，不影響健康檢查端點本身")


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


def _run_background_checks() -> None:
    """實際執行 `/healthz` 附掛的排程檢查，在背景執行緒跑，
    見 `health_check()`。

    **2026-08-08 追加（production 事故修復）**：這些檢查原本是在 `/healthz` 的 HTTP
    request 裡依序同步執行，平常大部分檢查會因為「還沒到時間」提早 return、很快；但每天台灣
    時間 08:00 這個時間點，多個排程剛好卡在同一小時，會在同一次 request 裡真的依序執行完（查
    DB、發 Telegram），Robin 實測發現這導致單次 `/healthz` 耗時過長，遠超過 cron-job.org 預設
    的 30 秒逾時，被判定成 keep-alive 失敗（詳見 PROGRESS.md 事故紀錄）。改成丟進背景執行緒後，
    HTTP 回應不再等待這些檢查跑完，`/healthz` 回應時間跟這些檢查的實際執行時間脫鉤。

    這些檢查函式本來就已經各自做好「同一小時內多次觸發也不會重複推播」的去重設計，所以背景
    執行緒偶爾跟下一次 `/healthz` 觸發重疊執行，本身是安全的，不會造成重複推播。

    **2026-11（功能大幅精簡）**：Neon 容量監控、固定節日／跨模組目標摘要／技術情報／TOEIC／
    證照題庫／求職模組等排程皆隨對應功能整個移除，這裡統一開一個 `db`、傳給所有檢查共用，跑完
    才在最外層關閉一次。沒有設定 `DATABASE_URL`（本機測試環境常見）時，整批直接跳過，不建立連線。
    """
    if not os.environ.get("DATABASE_URL"):
        return

    from submodules.cloudsql.client import CloudSQLClient

    db = CloudSQLClient()
    try:
        _check_todo_pushes(db)
        _check_birthdays(db)
        _check_national_holidays(db)
    finally:
        db.close()


@app.route("/healthz")
def health_check():
    """極簡健康檢查端點，供 cron-job.org 每 10 分鐘呼叫一次，避免 Render 免費方案休眠。

    對應 FR-3 / docs/specs/robinson/SPEC.md，路由定義見 src/schema/api_schema.md。

    2026-08-02（Step 1.6，見 FR-21）起，陸續借用這個每 10 分鐘一次的呼叫頻率，順便觸發多項
    排程檢查（待辦推播、生日推播），實際清單見
    `_run_background_checks()`。

    **2026-08-08 追加（production 事故修復）**：這些檢查改成丟進背景執行緒（daemon thread）
    執行，`/healthz` 本身立即回 200，不等待檢查跑完，避免 cron-job.org 因為單次 request 耗時
    過長而誤判逾時，詳見 `_run_background_checks()` docstring。
    """
    threading.Thread(target=_run_background_checks, daemon=True).start()
    return jsonify({"status": "ok"}), 200


_run_startup_migrations()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
