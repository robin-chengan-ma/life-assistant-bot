"""Migration 執行機制（ADR-11）。

流程：Claude 提出 CREATE TABLE 草案 + 設計理由 → Robin 同意 → Claude 把該筆 SQL
存成本資料夾底下的 .sql 檔案（檔名格式 NNNN_說明.sql，例如 0001_create_users_table.sql）
並 commit + push 到 GitHub main 分支 → Render 偵測到 push 自動重新部署 → app 開機時
呼叫 run_pending_migrations()，依編號順序執行「尚未套用過」的檔案，並記錄到資料庫的
schema_migrations 追蹤表，避免重複執行。

已套用過的檔案不可回頭修改內容；如需變更既有資料表，另開一個新的編號檔案（例如
ALTER TABLE 語句），維持每個檔案代表「一次已發生過的變更」的不可變（immutable）特性。
"""
import logging
import os
import re

from submodules.cloudsql.client import CloudSQLClient

logger = logging.getLogger("robinson.migrations")

_MIGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
_FILENAME_PATTERN = re.compile(r"^\d{4}_.+\.sql$")

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _list_migration_files(migrations_dir: str) -> list[str]:
    """列出資料夾內所有符合命名規則的 .sql 檔案，依檔名（即編號）排序。"""
    if not os.path.isdir(migrations_dir):
        return []
    filenames = [f for f in os.listdir(migrations_dir) if _FILENAME_PATTERN.match(f)]
    return sorted(filenames)


def run_pending_migrations(db: CloudSQLClient, migrations_dir: str = _MIGRATIONS_DIR) -> list[str]:
    """執行尚未套用過的 migration 檔案，回傳本次實際套用的檔名清單。

    設計刻意保守：任何一個檔案執行失敗就整個中止（不繼續跑後面的檔案），並把例外原樣
    往外拋，交給呼叫端（main.py）決定要不要讓 app 啟動失敗——資料庫結構是核心依賴，
    帶著「跑到一半」的 schema 悄悄啟動風險更高。
    """
    db.execute(_CREATE_TRACKING_TABLE)

    applied_rows = db.select("schema_migrations", columns=("filename",))
    already_applied = {row["filename"] for row in applied_rows}

    newly_applied: list[str] = []
    for filename in _list_migration_files(migrations_dir):
        if filename in already_applied:
            continue

        filepath = os.path.join(migrations_dir, filename)
        with open(filepath, encoding="utf-8") as f:
            sql = f.read()

        logger.info("套用 migration：%s", filename)
        db.execute(sql)
        db.insert("schema_migrations", {"filename": filename}, returning="filename")
        newly_applied.append(filename)
        logger.info("完成 migration：%s", filename)

    if not newly_applied:
        logger.info("沒有待套用的 migration，schema 已是最新狀態")

    return newly_applied
