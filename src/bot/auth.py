"""身分判斷與通關密碼綁定邏輯（對應 docs/specs/platform-auth/SPEC.md FR-2、FR-3）。"""
import os
from datetime import datetime, timezone

from submodules.cloudsql.client import CloudSQLClient


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
        {"telegram_user_id": telegram_user_id, "role": "Robin", "is_owner": True},
    )
    return db.select("users", where="id = %s", params=(new_id,), fetch_one=True)


def try_bind_invite_code(db: CloudSQLClient, telegram_user_id: int, code: str | None) -> bool:
    """嘗試用通關密碼綁定使用者身分，成功回傳 True，失敗（密碼不存在/已被使用/空輸入）回傳 False。

    綁定分兩步但避免 race condition：先用 `code + is_used=FALSE` 找出候選列，
    再用 `id + is_used=FALSE` 做一次原子性 UPDATE——如果密碼在這兩步之間被別的請求搶先綁定，
    第二次 UPDATE 會影響 0 筆，直接視為綁定失敗，不會有兩個人綁到同一組密碼的情況。
    """
    if not code:
        return False

    invite = db.select(
        "invite_codes",
        columns=("id", "user_id"),
        where="code = %s AND is_used = FALSE",
        params=(code,),
        fetch_one=True,
    )
    if not invite:
        return False

    affected = db.update(
        "invite_codes",
        {"is_used": True, "updated_at": datetime.now(timezone.utc)},
        where="id = %s AND is_used = FALSE",
        params=(invite["id"],),
    )
    if affected == 0:
        return False

    db.update(
        "users",
        {"telegram_user_id": telegram_user_id},
        where="id = %s",
        params=(invite["user_id"],),
    )
    return True
