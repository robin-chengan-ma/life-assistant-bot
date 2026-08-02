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
    """
    _check_neon_capacity()
    return jsonify({"status": "ok"}), 200


_run_startup_migrations()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)