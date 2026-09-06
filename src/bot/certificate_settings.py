"""Owner 專屬考試設定選單（FR-30a／FR-30b）。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.bot import (
    certificate_exam_scores,
    certificate_goals,
    certificate_quiz,
    certificate_schedule,
)
from src.bot.state import ConversationStateStore


def _keyboard(rows):
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data}] for text, data in rows
        ]
    }


def _profiles(db, user_id, active_only=True):
    rows = db.select("certificate_profiles", where="user_id = %s", params=(user_id,))
    rows = [row for row in rows if not active_only or row.get("is_active")]
    return sorted(rows, key=lambda row: row["display_name"].lower())


def start_menu():
    return "📖 考試設定，請選擇項目：", _keyboard(
        [
            ("證照設定", "certificate_settings:profiles"),
            ("目標", "certificate_settings:goals"),
            ("每日題數設定", "certificate_settings:daily"),
            ("實際考試紀錄", "certificate_settings:scores"),
            ("🔙 返回主選單", "menu:main"),
        ]
    )


def start_profiles(db, user_id):
    rows = _profiles(db, user_id, active_only=False)
    buttons = [
        (
            f"{'✅' if row.get('is_active') else '⏸'} {row['display_name']}",
            f"certificate_settings:profile:{row['id']}",
        )
        for row in rows
    ]
    buttons += [
        ("➕ 新增其他證照", "certificate_settings:profile:add"),
        ("🔙 返回考試設定", "certificate_settings:menu"),
    ]
    return "證照設定：", _keyboard(buttons)


def start_profile_add(store: ConversationStateStore, telegram_user_id, user_id):
    store.set(telegram_user_id, {"flow": "certificate_profile_add", "user_id": user_id})
    return "請輸入證照名稱："


def handle_profile_add_text(store: ConversationStateStore, telegram_user_id, text):
    name = " ".join(text.split())
    if not name or len(name) > 80:
        return "證照名稱不可空白，且最多 80 個字。"
    state = store.get(telegram_user_id)
    store.set(
        telegram_user_id,
        {
            **state,
            "name": name,
            "key": name.lower(),
            "flow": "certificate_profile_add_confirm",
        },
    )
    return f"準備新增「{name}」。確認新增嗎？", _keyboard(
        [
            ("✅ 確認新增", "certificate_settings:profile:confirm_add"),
            ("❌ 取消", "certificate_settings:profiles"),
        ]
    )


def confirm_profile_add(db, store, telegram_user_id):
    state = store.get(telegram_user_id)
    if not state or state.get("flow") != "certificate_profile_add_confirm":
        return "這個操作已失效，請重新開始。", None
    existing = db.select(
        "certificate_profiles", where="user_id = %s", params=(state["user_id"],)
    )
    if any(row["certificate_key"] == state["key"] for row in existing):
        store.clear(telegram_user_id)
        return "此證照已存在。", None
    db.insert(
        "certificate_profiles",
        {
            "user_id": state["user_id"],
            "certificate_key": state["key"],
            "display_name": state["name"],
            "is_active": True,
            "is_builtin": False,
        },
    )
    store.clear(telegram_user_id)
    return "已新增證照。", None


def start_profile_detail(db, user_id, profile_id):
    profile = db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )
    if not profile or profile["user_id"] != user_id:
        return "找不到這張證照設定。", _keyboard(
            [("🔙 返回證照設定", "certificate_settings:profiles")]
        )
    if profile.get("is_builtin"):
        rows = [("🔙 返回證照設定", "certificate_settings:profiles")]
    else:
        action = "停用" if profile.get("is_active") else "啟用"
        rows = [
            (action, f"certificate_settings:profile:toggle:{profile_id}"),
            ("🔙 返回證照設定", "certificate_settings:profiles"),
        ]
    return (
        f"{profile['display_name']}（{'啟用中' if profile.get('is_active') else '已停用'}）",
        _keyboard(rows),
    )


def start_profile_toggle(db, store, telegram_user_id, user_id, profile_id):
    profile = db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )
    if not profile or profile["user_id"] != user_id or profile.get("is_builtin"):
        return "無法變更這張證照設定。", None
    new_active = not profile.get("is_active")
    store.set(
        telegram_user_id,
        {
            "flow": "certificate_profile_toggle_confirm",
            "user_id": user_id,
            "profile_id": profile_id,
            "new_active": new_active,
        },
    )
    action = "啟用" if new_active else "停用"
    return f"確認要{action}「{profile['display_name']}」嗎？", _keyboard(
        [
            (
                f"✅ 確認{action}",
                f"certificate_settings:profile:confirm_toggle:{profile_id}",
            ),
            ("❌ 取消", f"certificate_settings:profile:{profile_id}"),
        ]
    )


def confirm_profile_toggle(db, store, telegram_user_id, user_id, profile_id):
    state = store.get(telegram_user_id)
    if (
        not state
        or state.get("flow") != "certificate_profile_toggle_confirm"
        or state.get("user_id") != user_id
        or state.get("profile_id") != profile_id
    ):
        return "這個操作已失效，請重新開始。", None
    profile = db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )
    if not profile or profile["user_id"] != user_id or profile.get("is_builtin"):
        store.clear(telegram_user_id)
        return "無法變更這張證照設定。", None
    db.update(
        "certificate_profiles",
        {"is_active": state["new_active"]},
        where="id = %s",
        params=(profile_id,),
    )
    store.clear(telegram_user_id)
    return "已更新證照狀態。", None


def _choice(db, user_id, prefix, include_inactive=False):
    rows = _profiles(db, user_id, active_only=not include_inactive)
    return _keyboard(
        [
            (row["display_name"], f"certificate_settings:{prefix}:{row['id']}")
            for row in rows
        ]
        + [("🔙 返回考試設定", "certificate_settings:menu")]
    )


def start_goals(db, user_id):
    return "選擇要設定目標的證照：", _choice(db, user_id, "goal")


def start_goal_set(store, telegram_user_id, user_id, profile):
    store.set(
        telegram_user_id,
        {"flow": "certificate_goal_date", "user_id": user_id, "profile": profile},
    )
    return "請輸入目標考試日期（YYYY-MM-DD；不設定請輸入「跳過」）："


def handle_goal_text(store, telegram_user_id, text):
    state = store.get(telegram_user_id)
    if state["flow"] == "certificate_goal_date":
        if text.strip() in {"跳過", "無"}:
            target_date = None
        else:
            try:
                target_date = date.fromisoformat(text.strip())
            except ValueError:
                return "日期格式不正確，請輸入 YYYY-MM-DD，或輸入「跳過」。"
        store.set(
            telegram_user_id,
            {**state, "flow": "certificate_goal_score", "target_date": target_date},
        )
        return "請輸入目標分數或結果（不設定請輸入「跳過」）："
    score = None if text.strip() in {"跳過", "無"} else text.strip()
    state = {**state, "flow": "certificate_goal_confirm", "target_score": score}
    store.set(telegram_user_id, state)
    return (
        f"確認目標：{state['profile']['display_name']}／日期 {state['target_date'] or '未設定'}／分數 {score or '未設定'}",
        _keyboard(
            [
                ("✅ 確認儲存", "certificate_settings:goal:confirm"),
                ("❌ 取消", "certificate_settings:goals"),
            ]
        ),
    )


def confirm_goal(db, store, telegram_user_id):
    state = store.get(telegram_user_id)
    if not state or state.get("flow") != "certificate_goal_confirm":
        return "這個操作已失效，請重新開始。", None
    profile = state["profile"]
    certificate_goals.set_goal(
        db,
        state["user_id"],
        profile["certificate_key"],
        state["target_date"],
        state["target_score"],
    )
    store.clear(telegram_user_id)
    return "已儲存證照目標。", None


def start_scores(db, user_id):
    return "選擇證照以新增或查看實際考試紀錄：", _choice(
        db, user_id, "score", include_inactive=True
    )


def start_daily(db, user_id):
    return "選擇要設定每日題數的證照：", _choice(db, user_id, "daily")


def profile_by_id(db, user_id, profile_id):
    profile = db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )
    return profile if profile and profile["user_id"] == user_id else None


def daily_summary(db, user_id, profile):
    has_questions = profile[
        "certificate_key"
    ] in certificate_quiz.distinct_exam_types_with_questions(db)
    settings = db.select(
        "certificate_daily_settings",
        where="user_id = %s AND exam_type = %s",
        params=(user_id, profile["certificate_key"]),
        fetch_one=True,
    )
    if not has_questions:
        return (
            f"{profile['display_name']} 目前尚無題庫，設定後不會推播題目。",
            _keyboard(
                [
                    ("✏️ 設定", f"certificate_settings:daily:set:{profile['id']}"),
                    ("📅 日期區間設定", f"certificate_settings:range:{profile['id']}"),
                    ("🔙 返回考試設定", "certificate_settings:menu"),
                ]
            ),
        )
    if (
        profile["certificate_key"] == "toeic"
        and settings
        and settings.get("toeic_listen_count") is not None
    ):
        detail = f"聽力 {settings['toeic_listen_count']}／讀寫 {settings['toeic_write_count']}／單字 {settings['toeic_vocab_count']}"
    else:
        detail = f"每日 {settings.get('daily_question_count', 6) if settings else 6} 題"
    # 2026-09-06（見 docs/ADR/discuss/robinson.md 對應日期條目）：「▶️ 開始作答」已移到主選單
    # 獨立項目（見 menu.py `quiz` key），這裡不再重複提供入口——原本這顆按鈕點下去其實不分證照、
    # 一次抓出所有證照當天待答的題目，放在單一證照的頁面底下反而讓人誤以為只會作答這個證照。
    return f"{profile['display_name']} 每日題數：{detail}", _keyboard(
        [
            ("✏️ 設定", f"certificate_settings:daily:set:{profile['id']}"),
            ("📅 日期區間設定", f"certificate_settings:range:{profile['id']}"),
            ("🔙 返回考試設定", "certificate_settings:menu"),
        ]
    )


def start_daily_set(store, telegram_user_id, user_id, profile):
    flow = (
        "certificate_daily_toeic_listen"
        if profile["certificate_key"] == "toeic"
        else "certificate_daily_count"
    )
    store.set(telegram_user_id, {"flow": flow, "user_id": user_id, "profile": profile})
    return (
        "請輸入聽力題數（可為 0）："
        if profile["certificate_key"] == "toeic"
        else "請輸入每日總題數（可為 0）："
    )


def handle_daily_text(store, telegram_user_id, text):
    state = store.get(telegram_user_id)
    try:
        count = int(text.strip())
    except ValueError:
        return "請輸入非負整數。"
    if not 0 <= count <= 100:
        return "題數限 0～100。"
    flow = state["flow"]
    if flow == "certificate_daily_count":
        state = {
            **state,
            "daily_question_count": count,
            "flow": "certificate_daily_confirm",
        }
    elif flow == "certificate_daily_toeic_listen":
        state = {**state, "listen": count, "flow": "certificate_daily_toeic_write"}
        store.set(telegram_user_id, state)
        return "請輸入讀寫題數（可為 0）："
    elif flow == "certificate_daily_toeic_write":
        state = {**state, "write": count, "flow": "certificate_daily_toeic_vocab"}
        store.set(telegram_user_id, state)
        return "請輸入單字題數（可為 0）："
    else:
        state = {
            **state,
            "vocab": count,
            "daily_question_count": state["listen"] + state["write"] + count,
            "flow": "certificate_daily_confirm",
        }
    store.set(telegram_user_id, state)
    return f"確認每日出題共 {state['daily_question_count']} 題嗎？", _keyboard(
        [
            ("✅ 確認儲存", "certificate_settings:daily:confirm"),
            ("❌ 取消", "certificate_settings:daily"),
        ]
    )


def confirm_daily(db, store, telegram_user_id):
    state = store.get(telegram_user_id)
    if not state or state.get("flow") != "certificate_daily_confirm":
        return "這個操作已失效，請重新開始。", None
    profile = state["profile"]
    existing = db.select(
        "certificate_daily_settings",
        where="user_id = %s AND exam_type = %s",
        params=(state["user_id"], profile["certificate_key"]),
        fetch_one=True,
    )
    data = {"daily_question_count": state["daily_question_count"]}
    if profile["certificate_key"] == "toeic":
        data |= {
            "toeic_listen_count": state["listen"],
            "toeic_write_count": state["write"],
            "toeic_vocab_count": state["vocab"],
        }
    if existing:
        db.update(
            "certificate_daily_settings",
            data,
            where="id = %s",
            params=(existing["id"],),
        )
    else:
        db.insert(
            "certificate_daily_settings",
            {
                "user_id": state["user_id"],
                "exam_type": profile["certificate_key"],
                "review_ratio_new": 7,
                "review_ratio_review": 3,
                **data,
            },
        )
    store.clear(telegram_user_id)
    return "已儲存每日題數設定。", None


def start_range_list(db, user_id, profile):
    rows = certificate_schedule.list_range_overrides(
        db, user_id, profile["certificate_key"]
    )
    lines = [f"📅 {profile['display_name']} 日期區間設定"]
    buttons = [("➕ 新增區間", f"certificate_settings:range:add:{profile['id']}")]
    for row in rows:
        lines.append(
            f"・{row['start_date']}～{row['end_date']}：每日 {row['daily_question_count']} 題"
        )
        buttons.extend(
            [
                (
                    f"✏️ 編輯 {row['start_date']}～{row['end_date']}",
                    f"certificate_settings:range:edit:{profile['id']}:{row['id']}",
                ),
                (
                    f"🗑 刪除 {row['start_date']}～{row['end_date']}",
                    f"certificate_settings:range:delete:{profile['id']}:{row['id']}",
                ),
            ]
        )
    if not rows:
        lines.append("目前沒有日期區間設定。")
    buttons.append(("🔙 返回每日題數", f"certificate_settings:daily:{profile['id']}"))
    return "\n".join(lines), _keyboard(buttons)


def start_range_edit(db, store, telegram_user_id, user_id, profile, override_id=None):
    if override_id is not None:
        row = db.select(
            "certificate_daily_schedule_overrides",
            where="id = %s",
            params=(override_id,),
            fetch_one=True,
        )
        if (
            not row
            or row["user_id"] != user_id
            or row["exam_type"] != profile["certificate_key"]
        ):
            return "找不到這筆日期區間設定。"
    store.set(
        telegram_user_id,
        {
            "flow": "certificate_range_start",
            "user_id": user_id,
            "profile": profile,
            "override_id": override_id,
        },
    )
    return "請輸入區間開始日期（YYYY-MM-DD）："


def handle_range_text(db, store, telegram_user_id, text):
    state = store.get(telegram_user_id)
    flow = state["flow"]
    if flow in {"certificate_range_start", "certificate_range_end"}:
        try:
            value = date.fromisoformat(text.strip())
        except ValueError:
            return "日期格式不正確，請輸入 YYYY-MM-DD。"
        if flow == "certificate_range_start":
            store.set(
                telegram_user_id,
                {**state, "flow": "certificate_range_end", "start_date": value},
            )
            return "請輸入區間結束日期（YYYY-MM-DD）："
        if value < state["start_date"]:
            return "結束日期不可早於開始日期。"
        profile = state["profile"]
        if certificate_schedule.has_overlapping_override(
            db,
            state["user_id"],
            profile["certificate_key"],
            state["start_date"],
            value,
            state.get("override_id"),
        ):
            return "此日期區間與既有設定重疊，請重新輸入結束日期或取消後重設。"
        next_flow = (
            "certificate_range_toeic_listen"
            if profile["certificate_key"] == "toeic"
            else "certificate_range_count"
        )
        store.set(telegram_user_id, {**state, "flow": next_flow, "end_date": value})
        return (
            "請輸入聽力題數（可為 0）："
            if next_flow.endswith("listen")
            else "請輸入這段期間每天的總題數（0～100）："
        )

    try:
        count = int(text.strip())
    except ValueError:
        return "請輸入 0～100 的整數。"
    if not 0 <= count <= 100:
        return "題數限 0～100。"
    if flow == "certificate_range_toeic_listen":
        store.set(
            telegram_user_id,
            {**state, "flow": "certificate_range_toeic_write", "listen": count},
        )
        return "請輸入讀寫題數（可為 0）："
    if flow == "certificate_range_toeic_write":
        store.set(
            telegram_user_id,
            {**state, "flow": "certificate_range_toeic_vocab", "write": count},
        )
        return "請輸入單字題數（可為 0）："
    if flow == "certificate_range_toeic_vocab":
        state = {
            **state,
            "vocab": count,
            "daily_question_count": state["listen"] + state["write"] + count,
        }
    else:
        state = {**state, "daily_question_count": count}
    state["flow"] = "certificate_range_confirm"
    store.set(telegram_user_id, state)
    return (
        f"確認區間：{state['start_date']}～{state['end_date']}，每天 {state['daily_question_count']} 題？",
        _keyboard(
            [
                ("✅ 確認儲存", "certificate_settings:range:confirm"),
                ("❌ 取消", f"certificate_settings:range:{state['profile']['id']}"),
            ]
        ),
    )


def confirm_range(db, store, telegram_user_id):
    state = store.get(telegram_user_id)
    if not state or state.get("flow") != "certificate_range_confirm":
        return "這個操作已失效，請重新開始。", None
    profile = state["profile"]
    if certificate_schedule.has_overlapping_override(
        db,
        state["user_id"],
        profile["certificate_key"],
        state["start_date"],
        state["end_date"],
        state.get("override_id"),
    ):
        store.clear(telegram_user_id)
        return "此日期區間已與其他設定重疊，請重新設定。", None
    data = {
        "user_id": state["user_id"],
        "exam_type": profile["certificate_key"],
        "start_date": state["start_date"],
        "end_date": state["end_date"],
        "daily_question_count": state["daily_question_count"],
    }
    if profile["certificate_key"] == "toeic":
        data |= {
            "toeic_listen_count": state["listen"],
            "toeic_write_count": state["write"],
            "toeic_vocab_count": state["vocab"],
        }
    if state.get("override_id") is None:
        db.insert("certificate_daily_schedule_overrides", data)
    else:
        data.pop("user_id")
        data.pop("exam_type")
        db.update(
            "certificate_daily_schedule_overrides",
            data,
            where="id = %s",
            params=(state["override_id"],),
        )
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    if state["start_date"] <= today <= state["end_date"]:
        certificate_schedule.delete_unanswered_assignments(
            db, state["user_id"], profile["certificate_key"], today
        )
    store.clear(telegram_user_id)
    return "已儲存日期區間設定。", None


def start_range_delete(db, store, telegram_user_id, user_id, profile, override_id):
    row = db.select(
        "certificate_daily_schedule_overrides",
        where="id = %s",
        params=(override_id,),
        fetch_one=True,
    )
    if (
        not row
        or row["user_id"] != user_id
        or row["exam_type"] != profile["certificate_key"]
    ):
        return "找不到這筆日期區間設定。", None
    store.set(
        telegram_user_id,
        {
            "flow": "certificate_range_delete_confirm",
            "user_id": user_id,
            "profile": profile,
            "override_id": override_id,
        },
    )
    return f"確定刪除 {row['start_date']}～{row['end_date']} 的設定嗎？", _keyboard(
        [
            (
                "✅ 確認刪除",
                f"certificate_settings:range:confirm_delete:{profile['id']}:{override_id}",
            ),
            ("❌ 取消", f"certificate_settings:range:{profile['id']}"),
        ]
    )


def confirm_range_delete(db, store, telegram_user_id, user_id, profile, override_id):
    state = store.get(telegram_user_id)
    if (
        not state
        or state.get("flow") != "certificate_range_delete_confirm"
        or state.get("override_id") != override_id
    ):
        return "這個刪除操作已失效，請重新開始。", None
    row = db.select(
        "certificate_daily_schedule_overrides",
        where="id = %s",
        params=(override_id,),
        fetch_one=True,
    )
    if (
        not row
        or row["user_id"] != user_id
        or row["exam_type"] != profile["certificate_key"]
    ):
        return "找不到這筆日期區間設定。", None
    db.delete(
        "certificate_daily_schedule_overrides", where="id = %s", params=(override_id,)
    )
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    if row["start_date"] <= today <= row["end_date"]:
        certificate_schedule.delete_unanswered_assignments(
            db, user_id, profile["certificate_key"], today
        )
    store.clear(telegram_user_id)
    return "已刪除日期區間設定。", None


def score_list(db, user_id, profile):
    return certificate_exam_scores.format_scores_summary(
        profile["certificate_key"],
        certificate_exam_scores.list_scores(db, user_id, profile["certificate_key"]),
    ), _keyboard(
        [
            ("➕ 新增紀錄", f"certificate_settings:score:add:{profile['id']}"),
            ("🔙 返回考試設定", "certificate_settings:menu"),
        ]
    )


def start_score_add(store, telegram_user_id, user_id, profile):
    store.set(
        telegram_user_id,
        {"flow": "certificate_score_date", "user_id": user_id, "profile": profile},
    )
    return "請輸入應考日期（YYYY-MM-DD，不可為未來日期）："


def handle_score_text(store, telegram_user_id, text):
    state = store.get(telegram_user_id)
    flow = state["flow"]
    if flow == "certificate_score_date":
        try:
            value = date.fromisoformat(text.strip())
        except ValueError:
            return "日期格式不正確，請輸入 YYYY-MM-DD。"
        if value > datetime.now(ZoneInfo("Asia/Taipei")).date():
            return "應考日期不可晚於今天。"
        store.set(
            telegram_user_id,
            {**state, "flow": "certificate_score_value", "exam_date": value},
        )
        return "請輸入分數或結果："
    if flow == "certificate_score_value":
        if not text.strip():
            return "分數或結果不可空白。"
        store.set(
            telegram_user_id,
            {**state, "flow": "certificate_score_note", "score": text.strip()},
        )
        return "請輸入補充內容；若沒有，請輸入「跳過」。"
    note = None if text.strip() in {"跳過", "無"} else text.strip()
    state = {**state, "flow": "certificate_score_confirm", "note": note}
    store.set(telegram_user_id, state)
    return (
        f"確認記錄：{state['profile']['display_name']}／{state['exam_date']}／{state['score']}／{note or '無'}",
        _keyboard(
            [
                ("✅ 確認儲存", "certificate_settings:score:confirm"),
                ("❌ 取消", "certificate_settings:scores"),
            ]
        ),
    )


def confirm_score(db, store, telegram_user_id):
    state = store.get(telegram_user_id)
    if not state or state.get("flow") != "certificate_score_confirm":
        return "這個操作已失效，請重新開始。", None
    profile = state["profile"]
    certificate_exam_scores.record_score(
        db,
        state["user_id"],
        profile["certificate_key"],
        state["exam_date"],
        state["score"],
        state["note"],
    )
    achievement = certificate_goals.check_score_achievement(
        db, state["user_id"], profile["certificate_key"], state["score"]
    )
    store.clear(telegram_user_id)
    reply = "已儲存實際考試紀錄。"
    if achievement:
        reply += f"\n{achievement}"
    return reply, None
