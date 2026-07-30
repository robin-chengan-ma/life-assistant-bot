import logging
import os

from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("robinson.main")

app = Flask(__name__)


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
    """
    return jsonify({"status": "ok"}), 200


_run_startup_migrations()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)