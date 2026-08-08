import logging
import os
import threading

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


def _check_skill_growth_collection() -> None:
    """在 /healthz 被呼叫時順便檢查每日技術摘要的「收集」階段（Step 3.1，見 robinson SPEC.md
    FR-22、FR-23）：固定台灣時間 23:00，讀取 Robin 訂閱的 TLDR 電子報＋IThome／TechCrunch
    「當天」新聞，經 Gemini 產出中文重點摘要寫入 `skill_growth_digests`，詳見
    src/bot/skill_growth.py 模組 docstring（收集與推播分成兩個獨立排程時間點）。

    這個階段不需要 `TELEGRAM_BOT_TOKEN`（不推播，只收集寫入 DB）；需要 `GMAIL_USER`／
    `GMAIL_PASSWORD`（讀信用）與 `GEMINI_API_SKILL_GROWTH_KEY`（獨立一把 Key，避免佔用
    聊天/長記憶/圖片辨識既有 Key 的配額，比照 `GEMINI_API_PRIVACY_KEY` 的既有慣例），
    任一項未設定就直接跳過（本機測試環境或 Robin 尚未申請新 Key 時常見）。
    """
    if not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("GMAIL_USER")
        and os.environ.get("GMAIL_PASSWORD")
        and os.environ.get("GEMINI_API_SKILL_GROWTH_KEY")
    ):
        return

    from src.bot import skill_growth
    from submodules.cloudsql.client import CloudSQLClient
    from submodules.email.client import EmailClient
    from submodules.llm.client import LLMClient
    from submodules.newsfeed.client import NewsFeedClient

    db = CloudSQLClient()
    try:
        email_client = EmailClient(username=os.environ["GMAIL_USER"], password=os.environ["GMAIL_PASSWORD"])
        newsfeed_client = NewsFeedClient()
        llm_client = LLMClient(api_key=os.environ["GEMINI_API_SKILL_GROWTH_KEY"])
        skill_growth.collect_and_store_daily_digest(db, email_client, newsfeed_client, llm_client)
    except Exception:
        logger.exception("每日技術摘要收集失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_skill_growth_push() -> None:
    """在 /healthz 被呼叫時順便檢查每日技術摘要的「推播」階段（Step 3.1，見 robinson SPEC.md
    FR-22、FR-23）：固定台灣時間 08:00，把前一晚 23:00 收集到的技術摘要推播給 Robin，詳見
    src/bot/skill_growth.py 模組 docstring。

    這個階段只需要 `TELEGRAM_BOT_TOKEN`，不需要 Gmail／Gemini 相關金鑰（收集階段已經處理完，
    這裡只是把結果讀出來推播）；收件人是查 `users.is_owner = TRUE` 動態決定，不需要
    `ROBIN_TELEGRAM_TOKEN`。
    """
    if not (os.environ.get("DATABASE_URL") and os.environ.get("TELEGRAM_BOT_TOKEN")):
        return

    from src.bot import skill_growth
    from submodules.cloudsql.client import CloudSQLClient
    from submodules.telegram.client import TelegramClient

    db = CloudSQLClient()
    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        skill_growth.check_and_push_daily_digest(db, telegram_client)
    except Exception:
        logger.exception("每日技術摘要推播失敗，不影響健康檢查端點本身")
    finally:
        db.close()


def _check_toeic_pipeline() -> None:
    """在 /healthz 被呼叫時順便檢查 TOEIC 雙軌題庫 Pipeline（Step 3.2，見 robinson SPEC.md
    FR-24、FR-25a～FR-25f）：固定台灣時間週日 22:00，掃描 Google Drive 資料夾比對/解析軌道一
    題目，並生成軌道二單字題，詳見 src/bot/toeic.py 模組 docstring。這支函式只負責「把題庫
    建好」，不做推播/作答（留待 Step 3.3）。

    需要 `GDRIVE_*`（Drive 掃描/上傳）、`GEMINI_API_IMAGE_KEY1`／`GEMINI_API_IMAGE_KEY2`
    （軌道一圖片解析，隨機擇一，見 ADR-12）、`VOICE_API_KEY`（軌道一整包音檔切割）、
    `GEMINI_API_TEXT_KEY`（軌道二單字題生成）；任一項未設定就直接跳過（本機測試環境或
    Robin 尚未完成 OAuth 重新授權時常見）。
    """
    required_env_vars = (
        "DATABASE_URL",
        "GDRIVE_OAUTH_REFRESH_TOKEN",
        "GDRIVE_OAUTH_CLIENT_ID",
        "GDRIVE_OAUTH_CLIENT_SECRET",
        "GDRIVE_FOLDER_ID",
        "GEMINI_API_IMAGE_KEY1",
        "GEMINI_API_IMAGE_KEY2",
        "VOICE_API_KEY",
        "GEMINI_API_TEXT_KEY",
    )
    if not all(os.environ.get(var) for var in required_env_vars):
        return

    from src.bot import toeic
    from submodules.cloudsql.client import CloudSQLClient
    from submodules.gdrive.client import GDriveClient
    from submodules.llm.client import LLMClient
    from submodules.voice.client import VoiceClient

    db = CloudSQLClient()
    try:
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
        text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
        toeic.run_weekly_pipeline(db, gdrive_client, image_llm_clients, voice_client, text_llm_client)
    except Exception:
        logger.exception("TOEIC 雙軌題庫 Pipeline 執行失敗，不影響健康檢查端點本身")
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


def _run_background_checks() -> None:
    """實際執行 `/healthz` 附掛的 10 個排程檢查，在背景執行緒跑，見 `health_check()`。

    **2026-08-08 追加（production 事故修復）**：這 10 個檢查原本是在 `/healthz` 的 HTTP
    request 裡依序同步執行，平常大部分檢查會因為「還沒到時間」提早 return、很快；但每天台灣
    時間 08:00 這個時間點，待辦每日摘要、重要通知、技術摘要推播三個排程剛好卡在同一小時，會在
    同一次 request 裡真的依序執行完（查 DB、發 Telegram、甚至呼叫 Gemini），Robin 實測發現這
    導致單次 `/healthz` 耗時超過 40 秒，遠超過 cron-job.org 預設的 30 秒逾時，被判定成
    keep-alive 失敗（詳見 PROGRESS.md 事故紀錄）。改成丟進背景執行緒後，HTTP 回應不再等待這些
    檢查跑完，`/healthz` 回應時間跟這 10 個檢查的實際執行時間脫鉤。

    這些檢查函式本來就已經各自做好「同一小時內多次觸發也不會重複推播」的去重設計（例如
    `daily_pushed_on`、`skill_growth_digests.pushed_on` 等欄位，見各自模組 docstring），所以
    背景執行緒偶爾跟下一次 `/healthz` 觸發重疊執行，本身是安全的，不會造成重複推播。
    """
    _check_neon_capacity()
    _check_todo_pushes()
    _check_finance_alerts()
    _check_finance_reminders()
    _check_finance_monthly_report()
    _check_body_goal_alerts()
    _check_important_notifications()
    _check_skill_growth_collection()
    _check_toeic_pipeline()
    _check_skill_growth_push()


@app.route("/healthz")
def health_check():
    """極簡健康檢查端點，供 cron-job.org 每 10 分鐘呼叫一次，避免 Render 免費方案休眠。

    對應 FR-3 / docs/specs/robinson/SPEC.md，路由定義見 src/schema/api_schema.md。

    2026-08-02（Step 1.6，見 FR-21）起，陸續借用這個每 10 分鐘一次的呼叫頻率，順便觸發多項
    排程檢查（Neon 容量、待辦推播、記帳預警/提醒/月報、體態目標預警、重要通知、技術摘要收集/
    推播、TOEIC pipeline），實際清單見 `_run_background_checks()`。

    **2026-08-08 追加（production 事故修復）**：這些檢查改成丟進背景執行緒（daemon thread）
    執行，`/healthz` 本身立即回 200，不等待檢查跑完，避免 cron-job.org 因為單次 request 耗時
    過長（尤其每天 08:00 多個排程同時真的執行時）而誤判逾時，詳見 `_run_background_checks()`
    docstring。
    """
    threading.Thread(target=_run_background_checks, daemon=True).start()
    return jsonify({"status": "ok"}), 200


_run_startup_migrations()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)