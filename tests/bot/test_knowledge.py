from datetime import datetime, timedelta, timezone

from src.bot import knowledge


def _seed_general(fake_db):
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "我是羅賓森"})
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "家人背景"})


def test_build_context_includes_general_persona_and_family(fake_db):
    _seed_general(fake_db)

    context = knowledge.build_context(fake_db, user_id=1)

    assert context["persona"] == "我是羅賓森"
    assert context["family"] == "家人背景"


def test_build_context_only_includes_own_custom_knowledge(fake_db):
    _seed_general(fake_db)
    fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "我喜歡打籃球"})
    fake_db.insert("knowledge_base", {"category": "custom", "user_id": 2, "content": "別人的秘密"})

    context = knowledge.build_context(fake_db, user_id=1)

    assert context["custom"] == ["我喜歡打籃球"]


def test_build_context_only_includes_own_recent_logs(fake_db):
    _seed_general(fake_db)
    now = datetime.now(timezone.utc)
    fake_db.insert(
        "conversation_logs",
        {"user_id": 1, "role": "user", "content": "我的訊息", "created_at": now, "deleted_at": None},
    )
    fake_db.insert(
        "conversation_logs",
        {"user_id": 2, "role": "user", "content": "別人的訊息", "created_at": now, "deleted_at": None},
    )

    context = knowledge.build_context(fake_db, user_id=1)

    assert len(context["recent_logs"]) == 1
    assert context["recent_logs"][0]["content"] == "我的訊息"


def test_build_context_excludes_soft_deleted_logs(fake_db):
    _seed_general(fake_db)
    now = datetime.now(timezone.utc)
    fake_db.insert(
        "conversation_logs",
        {"user_id": 1, "role": "user", "content": "已刪除", "created_at": now, "deleted_at": now},
    )

    context = knowledge.build_context(fake_db, user_id=1)

    assert context["recent_logs"] == []


def test_build_context_limits_recent_logs_to_ten_most_recent(fake_db):
    _seed_general(fake_db)
    base = datetime.now(timezone.utc)
    for i in range(15):
        fake_db.insert(
            "conversation_logs",
            {
                "user_id": 1,
                "role": "user",
                "content": f"msg-{i}",
                "created_at": base + timedelta(seconds=i),
                "deleted_at": None,
            },
        )

    context = knowledge.build_context(fake_db, user_id=1)

    assert len(context["recent_logs"]) == 10
    # 應該是最新的 10 則（msg-5 ~ msg-14），且依時間排序
    assert [row["content"] for row in context["recent_logs"]] == [f"msg-{i}" for i in range(5, 15)]


def test_save_custom_knowledge_inserts_custom_category(fake_db):
    knowledge.save_custom_knowledge(fake_db, user_id=1, content="威靈頓牛排食譜")

    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 1
    assert rows[0]["content"] == "威靈頓牛排食譜"


def test_log_message_inserts_conversation_log(fake_db):
    knowledge.log_message(fake_db, user_id=1, role="user", content="早安")

    rows = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "早安"
