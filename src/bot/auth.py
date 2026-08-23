"""身分判斷與通關密碼綁定邏輯（對應 docs/specs/SPEC.md FR-2、FR-3、FR-4、FR-4a～FR-4d）。"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from submodules.cloudsql.client import CloudSQLClient

PASSCODE_TTL = timedelta(hours=24)
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=30)

# FR-4b／FR-4c：通關密碼連續錯誤鎖定，比照既有「Owner 設定對話流狀態存 process 記憶體」
# 的簡化原則（見 SPEC.md NFR-2）——鎖定狀態存在記憶體，服務重啟會遺失，刻意簡化。
# 綁定成功前系統還不知道這個 Telegram 使用者對應哪個 users.id，因此鎖定狀態只能以
# telegram_user_id（Telegram 平台身分，綁定前就存在）為 key，不能存在 invite_codes 或 users。
_verification_attempts: dict[int, dict] = {}


def is_owner(telegram_user_id: int) -> bool:
    """比對 telegram_user_id 是否等於環境變數 ROBIN_TELEGRAM_TOKEN（Robin 的 Telegram 使用者 ID）。

    環境變數未設定時一律視為「不是 Owner」，避免因設定缺漏而誤判任何人為管理者。
    """
    owner_id = os.environ.get("ROBIN_TELEGRAM_TOKEN")
    if not owner_id:
        return False
    return str(telegram_user_id) == str(owner_id)


def find_user_by_telegram_id(db: CloudSQLClient, telegram_user_id: int) -> dict | None:
    """依 telegram_user_id 查詢 users 表，查無則回傳 None。"""
    return db.select(
        "users",
        where="telegram_user_id = %s",
        params=(telegram_user_id,),
        fetch_one=True,
    )


def get_or_create_owner(db: CloudSQLClient, telegram_user_id: int) -> dict:
    """Robin 第一次互動時，若 users 表還沒有他的記錄就建立一筆（FR-5：Robin 免通關密碼）。"""
    existing = find_user_by_telegram_id(db, telegram_user_id)
    if existing:
        return existing

    new_id = db.insert(
        "users",
        {
            "telegram_user_id": telegram_user_id,
            "role": "Robin",
            "is_owner": True,
            "nickname": "Robin",
            "is_active": True,
        },
    )
    return db.select("users", where="id = %s", params=(new_id,), fetch_one=True)


def _mobile_user_id(user_id: int) -> str:
    """FR-4：Mobile App 使用者 ID，依 users.id 動態產生（不落地保存），格式 user + 至少兩位數流水號。"""
    return f"user{user_id:02d}"


def generate_passcode() -> str:
    """產生 6 位數一次性數字通關密碼（使用 secrets 模組確保不可預測）。"""
    return f"{secrets.randbelow(1_000_000):06d}"


def create_user_and_invite(db: CloudSQLClient, family_title: str, nickname: str | None = None) -> dict:
    """FR-4：Owner 專屬「權限管理」建立一般使用者。

    先建立 users 取得主鍵，再產生唯一的一次性通關密碼並寫入 invite_codes；
    回傳給呼叫端（未來的選單流程）用來組出「暱稱、使用者 ID、通關密碼」回覆內容。
    """
    user_id = db.insert(
        "users",
        {
            "telegram_user_id": None,
            "role": family_title,  # 沿用舊欄位維持相容，family_title 才是正式來源
            "family_title": family_title,
            "nickname": nickname,
            "is_owner": False,
            "is_active": True,
        },
    )

    now = datetime.now(timezone.utc)
    code = generate_passcode()
    for _ in range(5):  # 極低機率撞號重試，避免 UNIQUE 違反讓整個流程失敗
        existing = db.select("invite_codes", where="code = %s", params=(code,), fetch_one=True)
        if not existing:
            break
        code = generate_passcode()

    db.insert(
        "invite_codes",
        {
            "code": code,
            "is_used": False,
            "user_id": user_id,
            "expires_at": now + PASSCODE_TTL,
        },
    )

    return {
        "user_id": user_id,
        "mobile_user_id": _mobile_user_id(user_id),
        "nickname": nickname,
        "family_title": family_title,
        "passcode": code,
    }


def resend_passcode(db: CloudSQLClient, user_id: int) -> str:
    """FR-4c：Owner 重發通關密碼；舊的未使用密碼立即失效，產生新密碼。"""
    db.update(
        "invite_codes",
        {"is_used": True},
        where="user_id = %s AND is_used = FALSE",
        params=(user_id,),
    )

    now = datetime.now(timezone.utc)
    code = generate_passcode()
    db.insert(
        "invite_codes",
        {
            "code": code,
            "is_used": False,
            "user_id": user_id,
            "expires_at": now + PASSCODE_TTL,
        },
    )
    return code


def _is_locked(telegram_user_id: int) -> bool:
    entry = _verification_attempts.get(telegram_user_id)
    if not entry or not entry.get("locked_until"):
        return False
    return datetime.now(timezone.utc) < entry["locked_until"]


def _record_failed_attempt(telegram_user_id: int) -> None:
    entry = _verification_attempts.setdefault(telegram_user_id, {"failed_attempts": 0, "locked_until": None})
    entry["failed_attempts"] += 1
    if entry["failed_attempts"] >= LOCKOUT_THRESHOLD:
        entry["locked_until"] = datetime.now(timezone.utc) + LOCKOUT_DURATION


def _clear_attempts(telegram_user_id: int) -> None:
    _verification_attempts.pop(telegram_user_id, None)


def try_bind_invite_code(db: CloudSQLClient, telegram_user_id: int, code: str | None) -> bool:
    """嘗試用通關密碼綁定使用者身分，成功回傳 True，失敗（密碼不存在/已被使用/已過期/
    空輸入/目前鎖定中）回傳 False。

    綁定分兩步但避免 race condition：先用 `code + is_used=FALSE` 找出候選列，
    再用 `id + is_used=FALSE` 做一次原子性 UPDATE——如果密碼在這兩步之間被別的請求搶先綁定，
    第二次 UPDATE 會影響 0 筆，直接視為綁定失敗，不會有兩個人綁到同一組密碼的情況。

    FR-4b／FR-4c：連續輸入錯誤 5 次後鎖定 30 分鐘，鎖定期間直接拒絕、不再查詢資料庫。
    輸入正確但已過期的密碼視為失敗，但不計入錯誤次數（不是「猜錯」，是密碼本身失效）。
    """
    if _is_locked(telegram_user_id):
        return False

    if not code:
        return False

    invite = db.select(
        "invite_codes",
        columns=("id", "user_id", "expires_at"),
        where="code = %s AND is_used = FALSE",
        params=(code,),
        fetch_one=True,
    )
    if not invite:
        _record_failed_attempt(telegram_user_id)
        return False

    expires_at = invite.get("expires_at")
    if expires_at is not None and datetime.now(timezone.utc) > expires_at:
        return False

    affected = db.update(
        "invite_codes",
        {"is_used": True, "updated_at": datetime.now(timezone.utc)},
        where="id = %s AND is_used = FALSE",
        params=(invite["id"],),
    )
    if affected == 0:
        _record_failed_attempt(telegram_user_id)
        return False

    db.update(
        "users",
        {"telegram_user_id": telegram_user_id},
        where="id = %s",
        params=(invite["user_id"],),
    )
    _clear_attempts(telegram_user_id)
    return True


def set_user_active(db: CloudSQLClient, user_id: int, active: bool) -> None:
    """FR-4d：停用／恢復使用者，不刪除帳號。停用時一併撤銷 Mobile Refresh Token；
    恢復後仍須重新登入或重新綁定（不主動恢復 Token）。
    """
    data: dict = {"is_active": active}
    if not active:
        data["refresh_token_hash"] = None
        data["refresh_token_expires_at"] = None
    db.update("users", data, where="id = %s", params=(user_id,))


def list_mobile_login_locked_users(db: CloudSQLClient) -> list[dict]:
    """（2026-08-23，Mobile App 帳密登入鎖定）列出目前被鎖定的使用者，依鎖定時間排序。"""
    users = [u for u in db.select("users") if u.get("mobile_login_locked_at") is not None]
    return sorted(users, key=lambda u: u["mobile_login_locked_at"])


def unlock_mobile_login(db: CloudSQLClient, user_id: int) -> None:
    """（2026-08-23，Mobile App 帳密登入鎖定）Owner 手動解鎖，錯誤次數一併歸零。"""
    db.update(
        "users",
        {"mobile_login_locked_at": None, "mobile_login_failed_attempts": 0},
        where="id = %s",
        params=(user_id,),
    )
