"""src/bot/commands.py 的 start_friend_chat 單元測試（對應 robinson SPEC.md FR-51、FR-52，ADR-22）。"""
from src.bot import commands, mood


class _FakeLLMClient:
    def __init__(self, response_text="這是一段陪伴回覆"):
        self.response_text = response_text
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        return self.response_text


def test_start_friend_chat_uses_user_role_and_returns_llm_reply(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "媽媽", "is_owner": False})
    mood.create_mood_journal(fake_db, user_id, "happy_excited", "今天很開心", commands._now().date())
    llm_client = _FakeLLMClient(response_text="媽媽最近心情不錯耶！")

    reply = commands.start_friend_chat(fake_db, llm_client, user_id)

    assert reply == "媽媽最近心情不錯耶！"
    assert len(llm_client.prompts) == 1
    assert "媽媽" in llm_client.prompts[0]
    assert "心情小記" in llm_client.prompts[0]


def test_start_friend_chat_no_recent_data_still_generates_reply(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 2, "role": "弟弟", "is_owner": False})
    llm_client = _FakeLLMClient(response_text="最近過得如何呀？")

    reply = commands.start_friend_chat(fake_db, llm_client, user_id)

    assert reply == "最近過得如何呀？"
    assert "沒有任何功能模組的紀錄資料" in llm_client.prompts[0]


def test_start_friend_chat_strips_llm_whitespace(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 3, "role": "妹妹", "is_owner": False})
    llm_client = _FakeLLMClient(response_text="  回覆前後有空白  \n")

    reply = commands.start_friend_chat(fake_db, llm_client, user_id)

    assert reply == "回覆前後有空白"


def test_start_friend_chat_unknown_user_falls_back_to_generic_role(fake_db):
    llm_client = _FakeLLMClient(response_text="嗨，最近好嗎？")

    reply = commands.start_friend_chat(fake_db, llm_client, 999)

    assert reply == "嗨，最近好嗎？"
    assert "這位使用者" in llm_client.prompts[0]
