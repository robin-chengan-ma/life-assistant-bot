from datetime import datetime, timedelta, timezone

from src.bot import memory


class _FakeTextLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 memory.py 會用到的 generate_text。"""

    def __init__(self, response_text="濃縮後的摘要"):
        self.response_text = response_text
        self.last_prompt = None
        self.call_count = 0

    def generate_text(self, prompt):
        self.last_prompt = prompt
        self.call_count += 1
        return self.response_text


class _RaisingTextLLMClient:
    def generate_text(self, prompt):
        raise RuntimeError("Gemini 額度用盡")


def _insert_logs(fake_db, user_id, count, start_id_offset=0):
    base = datetime.now(timezone.utc)
    for i in range(count):
        fake_db.insert(
            "conversation_logs",
            {
                "user_id": user_id,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg-{start_id_offset + i}",
                "created_at": base + timedelta(seconds=start_id_offset + i),
                "deleted_at": None,
            },
        )


def test_get_or_create_summary_row_creates_blank_row_for_new_user(fake_db):
    row = memory.get_or_create_summary_row(fake_db, user_id=1)

    assert row["user_id"] == 1
    assert row["summary"] == ""
    assert row["summarized_up_to_log_id"] == 0


def test_get_or_create_summary_row_returns_existing_row(fake_db):
    fake_db.insert(
        "conversation_summaries",
        {"user_id": 1, "summary": "既有摘要", "summarized_up_to_log_id": 5},
    )

    row = memory.get_or_create_summary_row(fake_db, user_id=1)

    assert row["summary"] == "既有摘要"
    assert row["summarized_up_to_log_id"] == 5


def test_get_summary_returns_empty_string_for_new_user(fake_db):
    assert memory.get_summary(fake_db, user_id=1) == ""


def test_get_summary_returns_existing_summary(fake_db):
    fake_db.insert(
        "conversation_summaries",
        {"user_id": 1, "summary": "之前聊過記帳的事", "summarized_up_to_log_id": 3},
    )

    assert memory.get_summary(fake_db, user_id=1) == "之前聊過記帳的事"


def test_maybe_update_summary_does_nothing_when_backlog_below_threshold(fake_db):
    # 20 則對話：最近 10 則是短記憶，backlog 只有 10 則以下（剛好 10 則會觸發，這裡故意少一則）
    _insert_logs(fake_db, user_id=1, count=19)
    llm_client = _FakeTextLLMClient()

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    assert llm_client.call_count == 0
    row = memory.get_or_create_summary_row(fake_db, user_id=1)
    assert row["summary"] == ""
    assert row["summarized_up_to_log_id"] == 0


def test_maybe_update_summary_triggers_when_backlog_reaches_threshold(fake_db):
    # 20 則對話：最近 10 則是短記憶，backlog 剛好 10 則，達門檻
    _insert_logs(fake_db, user_id=1, count=20)
    llm_client = _FakeTextLLMClient(response_text="新的濃縮摘要")

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    assert llm_client.call_count == 1
    row = memory.get_or_create_summary_row(fake_db, user_id=1)
    assert row["summary"] == "新的濃縮摘要"
    assert row["summarized_up_to_log_id"] > 0


def test_maybe_update_summary_prompt_includes_existing_summary_and_backlog(fake_db):
    fake_db.insert(
        "conversation_summaries",
        {"user_id": 1, "summary": "舊摘要內容", "summarized_up_to_log_id": 0},
    )
    _insert_logs(fake_db, user_id=1, count=20)
    llm_client = _FakeTextLLMClient()

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    assert "舊摘要內容" in llm_client.last_prompt
    assert "msg-0" in llm_client.last_prompt  # backlog 應包含最早的訊息


def test_maybe_update_summary_only_considers_own_user_logs(fake_db):
    _insert_logs(fake_db, user_id=1, count=20)
    _insert_logs(fake_db, user_id=2, count=20)
    llm_client = _FakeTextLLMClient()

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    row_user_2 = memory.get_or_create_summary_row(fake_db, user_id=2)
    assert row_user_2["summary"] == ""


def test_maybe_update_summary_excludes_soft_deleted_logs(fake_db):
    base = datetime.now(timezone.utc)
    for i in range(20):
        fake_db.insert(
            "conversation_logs",
            {
                "user_id": 1,
                "role": "user",
                "content": f"msg-{i}",
                "created_at": base + timedelta(seconds=i),
                "deleted_at": base if i < 15 else None,  # 前 15 則已刪除
            },
        )
    llm_client = _FakeTextLLMClient()

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    # 只剩 5 則未刪除，未達門檻，不應觸發
    assert llm_client.call_count == 0


def test_maybe_update_summary_does_not_reprocess_already_summarized_logs(fake_db):
    _insert_logs(fake_db, user_id=1, count=20)
    llm_client = _FakeTextLLMClient(response_text="第一次摘要")
    memory.maybe_update_summary(fake_db, llm_client, user_id=1)
    first_watermark = memory.get_or_create_summary_row(fake_db, user_id=1)["summarized_up_to_log_id"]

    # 再呼叫一次，backlog 還沒累積到新的 10 則，不該再次觸發
    memory.maybe_update_summary(fake_db, llm_client, user_id=1)

    assert llm_client.call_count == 1
    assert memory.get_or_create_summary_row(fake_db, user_id=1)["summarized_up_to_log_id"] == first_watermark


def test_maybe_update_summary_swallows_llm_errors_without_raising(fake_db):
    _insert_logs(fake_db, user_id=1, count=20)
    llm_client = _RaisingTextLLMClient()

    memory.maybe_update_summary(fake_db, llm_client, user_id=1)  # 不應拋出例外

    row = memory.get_or_create_summary_row(fake_db, user_id=1)
    assert row["summary"] == ""  # 更新失敗，摘要維持原狀
