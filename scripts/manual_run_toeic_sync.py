"""手動立即觸發 TOEIC 軌道一 Drive 同步（不用等下週日 22:00）。

2026-09-06 新增：Robin 反饋 `_split_whole_audio()` 的裁切順序 bug 修好後，不想等到下週日
（2026-09-13）22:00 排程才知道有沒有真的修好；`run_weekly_pipeline()` 本身有「星期幾＋小時」
與「今天是否已跑過（`toeic_pipeline_last_run_on`）」兩層限制，沒辦法直接呼叫。這支腳本繞開
那兩層限制，直接呼叫 `sync_track1_from_drive()`（跟 `run_weekly_pipeline()` 內部呼叫的是
同一支函式），行為與正式排程完全一致，只是不受時間限制，方便手動重跑驗證。

使用方式（在 Render Dashboard 的 Shell 分頁執行，會沿用正式環境已設定好的環境變數）：

    python3 scripts/manual_run_toeic_sync.py

也可以在本機執行，前提是本機 `.env`／環境變數已經有下列跟正式環境相同的設定：
DATABASE_URL、GDRIVE_OAUTH_REFRESH_TOKEN、GDRIVE_OAUTH_CLIENT_ID、GDRIVE_OAUTH_CLIENT_SECRET、
GDRIVE_FOLDER_ID、GEMINI_API_IMAGE_KEY1、GEMINI_API_IMAGE_KEY2、VOICE_API_KEY。

執行完會印出這次掃到並成功寫入 `certificate_questions` 的聽力/閱讀題目數量摘要，不會動到
軌道二（單字題生成），也不會推播任何訊息給使用者。
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("manual_run_toeic_sync")

_REQUIRED_ENV_VARS = (
    "DATABASE_URL",
    "GDRIVE_OAUTH_REFRESH_TOKEN",
    "GDRIVE_OAUTH_CLIENT_ID",
    "GDRIVE_OAUTH_CLIENT_SECRET",
    "GDRIVE_FOLDER_ID",
    "GEMINI_API_IMAGE_KEY1",
    "GEMINI_API_IMAGE_KEY2",
    "VOICE_API_KEY",
)


def main() -> int:
    missing = [name for name in _REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        logger.error("缺少環境變數，無法執行：%s", ", ".join(missing))
        return 1

    from src.bot import toeic
    from submodules.cloudsql.client import CloudSQLClient
    from submodules.gdrive.client import GDriveClient
    from submodules.llm.client import LLMClient
    from submodules.voice.client import VoiceClient

    db = CloudSQLClient()
    before = db.select("certificate_questions")

    gdrive_client = GDriveClient(
        refresh_token=os.environ["GDRIVE_OAUTH_REFRESH_TOKEN"],
        client_id=os.environ["GDRIVE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["GDRIVE_OAUTH_CLIENT_SECRET"],
        folder_id=os.environ["GDRIVE_FOLDER_ID"],
    )
    image_llm_clients = [
        LLMClient(api_key=os.environ["GEMINI_API_IMAGE_KEY1"]),
        LLMClient(api_key=os.environ["GEMINI_API_IMAGE_KEY2"]),
    ]
    voice_client = VoiceClient(api_key=os.environ["VOICE_API_KEY"])

    logger.info("開始手動同步（等同 run_weekly_pipeline() 內部呼叫的 sync_track1_from_drive()）...")
    toeic.sync_track1_from_drive(db, gdrive_client, image_llm_clients, voice_client)

    after = db.select("certificate_questions")
    new_rows = [row for row in after if row["id"] not in {r["id"] for r in before}]
    by_type: dict[str, int] = {}
    for row in new_rows:
        by_type[row["question_type"]] = by_type.get(row["question_type"], 0) + 1

    logger.info("同步完成，本次新增 %d 題：%s", len(new_rows), by_type or "（無新增，可能是本來就沒有新素材，或又失敗了，請往上翻 log 看有沒有 ERROR）")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
