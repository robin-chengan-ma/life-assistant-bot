"""Owner 專屬「權限管理」對話式流程（對應 docs/specs/platform-auth/SPEC.md FR-4、FR-4a～FR-4d）。

2026-11（功能大幅精簡）：Telegram 機器人拿掉主選單與所有日常紀錄類功能（體態、記帳、待辦
CRUD、心情小記、求職、證照…）之後，`commands.py` 只剩下 Owner 建立使用者／重發通關密碼／
停用／恢復使用者這組流程，直接複用既有 `src/bot/auth.py` 的核心邏輯，本模組只負責 Telegram
對話的提問順序與文字組版。
"""

from src.bot import auth
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_EXIT_PHRASES = {"沒有了", "結束"}

_PERMISSION_ACTION_PROMPTS = {
    "disable": "請問要停用哪一位使用者？請輸入編號：",
    "enable": "請問要恢復哪一位使用者？請輸入編號：",
    "resend": "請問要重發通關密碼給哪一位使用者？請輸入編號：",
}


def start_permission_menu() -> tuple[str, dict]:
    """FR-4：Owner 專屬「權限管理」選單首頁。不需要 db／state_store，純粹回覆固定選單。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ 建立使用者", "callback_data": "permission:create"}],
            [{"text": "⛔ 停用使用者", "callback_data": "permission:disable"}],
            [{"text": "✅ 恢復使用者", "callback_data": "permission:enable"}],
            [{"text": "🔁 重發通關密碼", "callback_data": "permission:resend"}],
            [{"text": "🔓 解鎖 Mobile App 帳號", "callback_data": "permission:unlock_mobile"}],
        ]
    }
    return "請選擇要進行的權限管理操作：", keyboard


def handle_permission_callback(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    action: str,
) -> tuple[str, dict | None]:
    """權限管理選單按下其中一個操作按鈕後的分派，開始對應的引導式流程。

    `unlock_mobile`／`unlock_mobile_confirm:<user_id>`（2026-08-23，見
    docs/ADR/discuss/mobile-app.md）：Mobile App 帳密登入連續錯誤鎖定只能由 Owner 在這裡手動
    解鎖（`auth.unlock_mobile_login()`），跟通關密碼鎖定（`auth.py` 的 `_verification_attempts`，
    30 分鐘後自動解除）是兩套獨立機制。全程按鈕操作，不走打字輸入，所以不需要經過
    `handle_permission_step()` 的對話狀態機。
    """
    if action == "create":
        state_store.set(telegram_user_id, {"flow": "permission_create", "step": "awaiting_family_title"})
        return "請問要新增哪一位家人？請輸入家庭稱謂（例如：爸爸）：", None

    if action == "unlock_mobile":
        locked_users = auth.list_mobile_login_locked_users(db)
        if not locked_users:
            return "目前沒有帳號被鎖定喔！", {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "permission:menu"}]]}
        buttons = []
        lines = ["以下帳號 Mobile App 登入被鎖定，請選擇要解鎖的對象：", ""]
        for user in locked_users:
            display_name = user.get("nickname") or user.get("family_title") or user["role"]
            lines.append(f"- {display_name}")
            buttons.append(
                [{"text": f"🔓 解鎖 {display_name}", "callback_data": f"permission:unlock_mobile_confirm:{user['id']}"}]
            )
        return "\n".join(lines), {"inline_keyboard": buttons}

    if action.startswith("unlock_mobile_confirm:"):
        target_user_id = int(action[len("unlock_mobile_confirm:") :])
        auth.unlock_mobile_login(db, target_user_id)
        return "已解鎖該使用者的 Mobile App 帳號，可以重新登入了。", {
            "inline_keyboard": [[{"text": "🔙 返回", "callback_data": "permission:menu"}]]
        }

    if action in ("disable", "enable", "resend"):
        candidates = [u for u in db.select("users") if not u["is_owner"]]
        if not candidates:
            return "目前還沒有任何一般使用者，沒有可以操作的對象喔！", None

        state_store.set(
            telegram_user_id,
            {"flow": f"permission_{action}", "step": "awaiting_target", "candidates": [u["id"] for u in candidates]},
        )
        lines = [_PERMISSION_ACTION_PROMPTS[action], ""]
        for index, user in enumerate(candidates, start=1):
            status = "啟用中" if user.get("is_active", True) else "已停用"
            display_name = user.get("nickname") or user.get("family_title") or user["role"]
            lines.append(f"{index}. {display_name}（{status}）")
        return "\n".join(lines), None

    raise ValueError(f"未知的權限管理操作：{action}")


def handle_permission_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """依目前對話狀態處理權限管理流程中輸入的下一句話。"""
    state = state_store.get(telegram_user_id)
    flow = state.get("flow") if state else None
    step = state.get("step") if state else None

    if flow == "permission_create":
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束權限管理模式！"

        if step == "awaiting_family_title":
            state_store.set(
                telegram_user_id,
                {"flow": "permission_create", "step": "awaiting_full_name", "family_title": text},
            )
            return f"收到，請問「{text}」的全名是？（用於生日推播等需要分辨身份的地方，必填）"

        if step == "awaiting_full_name":
            full_name = text.strip()
            if not full_name:
                return "全名不能是空白，請重新輸入："
            state_store.set(
                telegram_user_id,
                {**state, "step": "awaiting_nickname", "full_name": full_name},
            )
            return f"收到，請問「{state['family_title']}」的暱稱是？（不需要的話輸入「略過」）"

        if step == "awaiting_nickname":
            family_title = state["family_title"]
            full_name = state["full_name"]
            nickname = None if text in {"略過", "skip"} else text
            result = auth.create_user_and_invite(db, family_title=family_title, full_name=full_name, nickname=nickname)
            state_store.clear(telegram_user_id)
            nickname_line = f"暱稱：{result['nickname']}\n" if result["nickname"] else ""
            return (
                f"已建立「{family_title}」！\n"
                f"全名：{full_name}\n"
                f"{nickname_line}"
                f"使用者 ID：{result['mobile_user_id']}\n"
                f"通關密碼：{result['passcode']}\n"
                "（此密碼僅能使用一次，24 小時內有效，請盡快提供給本人）"
            )

    if flow in ("permission_disable", "permission_enable", "permission_resend"):
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束權限管理模式！"

        candidates = state["candidates"]
        if not text.isdigit() or not (1 <= int(text) <= len(candidates)):
            return f"請輸入 1～{len(candidates)} 之間的編號喔！"

        target_user_id = candidates[int(text) - 1]
        state_store.clear(telegram_user_id)

        if flow == "permission_disable":
            auth.set_user_active(db, target_user_id, active=False)
            return "已停用該使用者，Mobile Refresh Token 也一併撤銷了。"
        if flow == "permission_enable":
            auth.set_user_active(db, target_user_id, active=True)
            return "已恢復該使用者，對方需要重新登入或重新綁定。"
        new_code = auth.resend_passcode(db, target_user_id)
        return f"已重發通關密碼：{new_code}\n（舊密碼已立即失效，此密碼僅能使用一次，24 小時內有效）"

    raise ValueError(f"未知的對話狀態：{state}")
