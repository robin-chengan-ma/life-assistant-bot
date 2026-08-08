"""src/bot/youtube.py 的單元測試（對應 robinson SPEC.md FR-57～FR-59、ADR-21）。"""
from datetime import date, datetime, timezone

from src.bot import youtube

_TAIWAN_TZ = youtube._TAIWAN_TZ


class _FakeYouTubeClient:
    def __init__(self, search_results_by_topic=None, details_by_video_id=None):
        self.search_results_by_topic = search_results_by_topic or {}
        self.details_by_video_id = details_by_video_id or {}
        self.search_calls = []
        self.details_calls = []

    def search_videos(self, query, max_results=10):
        self.search_calls.append(query)
        return self.search_results_by_topic.get(query, [])

    def get_video_details(self, video_ids):
        self.details_calls.append(list(video_ids))
        return [self.details_by_video_id[vid] for vid in video_ids if vid in self.details_by_video_id]


class _FakeLLMClient:
    def __init__(self, response_text=None, responses=None):
        self._responses = list(responses) if responses is not None else None
        self.response_text = response_text if response_text is not None else ""
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        if self._responses is not None:
            if len(self._responses) > 1:
                return self._responses.pop(0)
            return self._responses[0]
        return self.response_text


class _FakeTelegramClient:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})


def _detail(video_id, **overrides):
    row = {
        "video_id": video_id, "title": f"Title {video_id}", "description": f"Desc {video_id}",
        "channel_title": "Channel", "published_at": "2026-08-01T00:00:00Z",
        "view_count": 100, "like_count": 10, "comment_count": 1,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
    row.update(overrides)
    return row


def _search_result(video_id, **overrides):
    row = {
        "video_id": video_id, "title": f"Title {video_id}", "description": f"Desc {video_id}",
        "channel_title": "Channel", "published_at": "2026-08-01T00:00:00Z",
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
    row.update(overrides)
    return row


def _seed_topic(fake_db, **overrides):
    row = {"user_id": 1, "topic": "AI Agent", "last_recommended_on": None}
    row.update(overrides)
    return fake_db.insert("youtube_topics", row)


# --- 主題管理（FR-57a）---


def test_list_topics_sorted_by_id(fake_db):
    _seed_topic(fake_db, topic="B")
    _seed_topic(fake_db, topic="A")

    topics = youtube.list_topics(fake_db, 1)

    assert [t["topic"] for t in topics] == ["B", "A"]


def test_list_topics_only_this_user(fake_db):
    _seed_topic(fake_db, user_id=1)
    _seed_topic(fake_db, user_id=2)

    assert len(youtube.list_topics(fake_db, 1)) == 1


def test_add_topic_inserts_new(fake_db):
    result = youtube.add_topic(fake_db, 1, "後端架構")

    assert result == {"already_exists": False, "topic": "後端架構"}
    rows = fake_db.select("youtube_topics")
    assert rows[0]["topic"] == "後端架構"
    assert rows[0]["last_recommended_on"] is None


def test_add_topic_already_exists_does_not_duplicate(fake_db):
    _seed_topic(fake_db, topic="後端架構")

    result = youtube.add_topic(fake_db, 1, "後端架構")

    assert result == {"already_exists": True, "topic": "後端架構"}
    assert len(fake_db.select("youtube_topics")) == 1


def test_remove_topic_deletes_and_returns_true(fake_db):
    topic_id = _seed_topic(fake_db)

    assert youtube.remove_topic(fake_db, 1, topic_id) is True
    assert fake_db.select("youtube_topics") == []


def test_remove_topic_nonexistent_returns_false(fake_db):
    assert youtube.remove_topic(fake_db, 1, 999) is False


def test_remove_topic_wrong_user_returns_false(fake_db):
    topic_id = _seed_topic(fake_db, user_id=1)

    assert youtube.remove_topic(fake_db, 2, topic_id) is False
    assert len(fake_db.select("youtube_topics")) == 1


# --- FR-58a：候選清單去重 ---


def test_dedupe_by_video_id_keeps_first_occurrence():
    candidates = [_search_result("v1", title="第一次"), _search_result("v1", title="第二次"), _search_result("v2")]

    result = youtube._dedupe_by_video_id(candidates)

    assert [c["video_id"] for c in result] == ["v1", "v2"]
    assert result[0]["title"] == "第一次"


def test_dedupe_by_video_id_empty():
    assert youtube._dedupe_by_video_id([]) == []


# --- FR-58d：歷史去重 ---


def test_filter_recently_pushed_excludes_within_window(fake_db):
    fake_db.insert("youtube_pushed_videos", {"user_id": 1, "video_id": "v1", "topic": "AI", "pushed_on": date(2026, 8, 1)})
    candidates = [_detail("v1"), _detail("v2")]

    result = youtube._filter_recently_pushed(fake_db, 1, candidates, today=date(2026, 8, 10))

    assert [c["video_id"] for c in result] == ["v2"]


def test_filter_recently_pushed_allows_outside_window(fake_db):
    fake_db.insert("youtube_pushed_videos", {"user_id": 1, "video_id": "v1", "topic": "AI", "pushed_on": date(2026, 7, 1)})
    candidates = [_detail("v1")]

    result = youtube._filter_recently_pushed(fake_db, 1, candidates, today=date(2026, 8, 10))

    assert [c["video_id"] for c in result] == ["v1"]


def test_filter_recently_pushed_only_this_user(fake_db):
    fake_db.insert("youtube_pushed_videos", {"user_id": 2, "video_id": "v1", "topic": "AI", "pushed_on": date(2026, 8, 1)})
    candidates = [_detail("v1")]

    result = youtube._filter_recently_pushed(fake_db, 1, candidates, today=date(2026, 8, 10))

    assert [c["video_id"] for c in result] == ["v1"]


# --- FR-58b：LLM 評分 ---


def test_build_ranking_prompt_includes_all_fields():
    candidates = [_detail("v1", title="AI 教學", view_count=1000, like_count=50, comment_count=5)]

    prompt = youtube._build_ranking_prompt("AI", candidates)

    assert "AI 教學" in prompt
    assert "1000" in prompt
    assert "50" in prompt
    assert "AI" in prompt


def test_build_ranking_prompt_truncates_long_description():
    candidates = [_detail("v1", description="x" * 500)]

    prompt = youtube._build_ranking_prompt("AI", candidates)

    assert "x" * 500 not in prompt
    assert "x" * 200 in prompt


def test_parse_scores_valid_format():
    raw = "1: 8\n2: 3.5\n3: 9"
    assert youtube._parse_scores(raw, 3) == {1: 8.0, 2: 3.5, 3: 9.0}


def test_parse_scores_ignores_out_of_range_index():
    raw = "1: 8\n5: 3"
    assert youtube._parse_scores(raw, 3) == {1: 8.0}


def test_parse_scores_ignores_unparseable_lines():
    raw = "這是一段沒有格式的文字\n1: 8"
    assert youtube._parse_scores(raw, 3) == {1: 8.0}


def test_parse_scores_empty_raw():
    assert youtube._parse_scores("", 3) == {}


def test_score_candidates_for_topic_sorts_by_score_desc():
    candidates = [_detail("v1"), _detail("v2"), _detail("v3")]
    llm_client = _FakeLLMClient(response_text="1: 3\n2: 9\n3: 5")

    result = youtube.score_candidates_for_topic(llm_client, "AI", candidates)

    assert [c["video_id"] for c in result] == ["v2", "v3", "v1"]
    assert [c["score"] for c in result] == [9.0, 5.0, 3.0]


def test_score_candidates_for_topic_empty_candidates_skips_llm_call():
    llm_client = _FakeLLMClient(response_text="不應該被呼叫")

    result = youtube.score_candidates_for_topic(llm_client, "AI", [])

    assert result == []
    assert llm_client.prompts == []


def test_score_candidates_for_topic_missing_index_defaults_zero():
    candidates = [_detail("v1"), _detail("v2")]
    llm_client = _FakeLLMClient(response_text="1: 8")

    result = youtube.score_candidates_for_topic(llm_client, "AI", candidates)

    assert result[0]["video_id"] == "v1"
    assert result[0]["score"] == 8.0
    assert result[1]["video_id"] == "v2"
    assert result[1]["score"] == 0.0


def test_score_candidates_for_topic_parse_failure_falls_back_to_view_count(caplog):
    candidates = [_detail("v1", view_count=10), _detail("v2", view_count=500), _detail("v3", view_count=100)]
    llm_client = _FakeLLMClient(response_text="完全不是預期的格式")

    result = youtube.score_candidates_for_topic(llm_client, "AI", candidates)

    assert [c["video_id"] for c in result] == ["v2", "v3", "v1"]
    assert all(c["score"] is None for c in result)


# --- _gather_scored_candidates（整合 FR-57／FR-58a／FR-58d／FR-58b）---


def test_gather_scored_candidates_full_pipeline(fake_db):
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={"AI": [_search_result("v1"), _search_result("v2")]},
        details_by_video_id={"v1": _detail("v1", view_count=50), "v2": _detail("v2", view_count=999)},
    )
    llm_client = _FakeLLMClient(response_text="1: 2\n2: 9")

    result = youtube._gather_scored_candidates(youtube_client, llm_client, fake_db, 1, "AI", date(2026, 8, 10))

    assert [c["video_id"] for c in result] == ["v2", "v1"]
    assert youtube_client.search_calls == ["AI"]
    assert youtube_client.details_calls == [["v1", "v2"]]


def test_gather_scored_candidates_no_search_results_skips_details_and_llm(fake_db):
    youtube_client = _FakeYouTubeClient(search_results_by_topic={})
    llm_client = _FakeLLMClient(response_text="不應該被呼叫")

    result = youtube._gather_scored_candidates(youtube_client, llm_client, fake_db, 1, "AI", date(2026, 8, 10))

    assert result == []
    assert youtube_client.details_calls == []
    assert llm_client.prompts == []


def test_gather_scored_candidates_all_filtered_by_history_skips_llm(fake_db):
    fake_db.insert("youtube_pushed_videos", {"user_id": 1, "video_id": "v1", "topic": "AI", "pushed_on": date(2026, 8, 5)})
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={"AI": [_search_result("v1")]},
        details_by_video_id={"v1": _detail("v1")},
    )
    llm_client = _FakeLLMClient(response_text="不應該被呼叫")

    result = youtube._gather_scored_candidates(youtube_client, llm_client, fake_db, 1, "AI", date(2026, 8, 10))

    assert result == []
    assert llm_client.prompts == []


def test_gather_scored_candidates_missing_detail_dropped(fake_db):
    # 防禦性情境：search 回傳的 video_id 在 get_video_details 查不到（理論上不該發生）。
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={"AI": [_search_result("v1"), _search_result("v2")]},
        details_by_video_id={"v1": _detail("v1")},
    )
    llm_client = _FakeLLMClient(response_text="1: 5")

    result = youtube._gather_scored_candidates(youtube_client, llm_client, fake_db, 1, "AI", date(2026, 8, 10))

    assert [c["video_id"] for c in result] == ["v1"]


# --- _topics_by_priority（FR-58c 輪替排序）---


def test_topics_by_priority_null_first():
    topics = [
        {"topic": "A", "last_recommended_on": date(2026, 8, 1)},
        {"topic": "B", "last_recommended_on": None},
    ]
    result = youtube._topics_by_priority(topics)
    assert [t["topic"] for t in result] == ["B", "A"]


def test_topics_by_priority_oldest_first():
    topics = [
        {"topic": "A", "last_recommended_on": date(2026, 8, 5)},
        {"topic": "B", "last_recommended_on": date(2026, 8, 1)},
    ]
    result = youtube._topics_by_priority(topics)
    assert [t["topic"] for t in result] == ["B", "A"]


# --- select_weekly_recommendations（FR-58c 三種情境）---


def test_select_weekly_recommendations_no_topics_returns_empty(fake_db):
    youtube_client = _FakeYouTubeClient()
    llm_client = _FakeLLMClient()

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    assert result == []


def test_select_weekly_recommendations_single_topic_takes_top_three(fake_db):
    _seed_topic(fake_db, topic="AI")
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={
            "AI": [_search_result("v1"), _search_result("v2"), _search_result("v3"), _search_result("v4")]
        },
        details_by_video_id={
            "v1": _detail("v1"), "v2": _detail("v2"), "v3": _detail("v3"), "v4": _detail("v4"),
        },
    )
    llm_client = _FakeLLMClient(response_text="1: 9\n2: 5\n3: 3\n4: 1")

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    assert [p["video_id"] for p in result] == ["v1", "v2", "v3"]
    assert all(p["topic"] == "AI" for p in result)

    topic_row = fake_db.select("youtube_topics", where="user_id = %s", params=(1,))[0]
    assert topic_row["last_recommended_on"] == date(2026, 8, 13)
    assert len(fake_db.select("youtube_pushed_videos")) == 3


def test_select_weekly_recommendations_two_topics_guarantee_plus_best_leftover(fake_db):
    _seed_topic(fake_db, topic="A")
    _seed_topic(fake_db, topic="B")
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={
            "A": [_search_result("a1"), _search_result("a2")],
            "B": [_search_result("b1"), _search_result("b2")],
        },
        details_by_video_id={
            "a1": _detail("a1"), "a2": _detail("a2"), "b1": _detail("b1"), "b2": _detail("b2"),
        },
    )
    # A: a1=9, a2=2；B: b1=7, b2=6 -> 保底 a1、b1；剩餘名額比較 leftovers[a2=2, b2=6] -> b2 勝出
    llm_client = _FakeLLMClient(responses=["1: 9\n2: 2", "1: 7\n2: 6"])

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    assert {p["video_id"] for p in result} == {"a1", "b1", "b2"}
    topics_after = {t["topic"]: t["last_recommended_on"] for t in fake_db.select("youtube_topics")}
    assert topics_after == {"A": date(2026, 8, 13), "B": date(2026, 8, 13)}


def test_select_weekly_recommendations_three_or_more_topics_picks_oldest_three(fake_db):
    _seed_topic(fake_db, topic="T1", last_recommended_on=None)
    _seed_topic(fake_db, topic="T2", last_recommended_on=date(2026, 7, 20))
    _seed_topic(fake_db, topic="T3", last_recommended_on=date(2026, 7, 25))
    _seed_topic(fake_db, topic="T4", last_recommended_on=date(2026, 8, 12))  # 最近推播過，這次不參與

    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={
            "T1": [_search_result("t1a")], "T2": [_search_result("t2a")],
            "T3": [_search_result("t3a")], "T4": [_search_result("t4a")],
        },
        details_by_video_id={
            "t1a": _detail("t1a"), "t2a": _detail("t2a"), "t3a": _detail("t3a"), "t4a": _detail("t4a"),
        },
    )
    llm_client = _FakeLLMClient(response_text="1: 5")

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    assert {p["video_id"] for p in result} == {"t1a", "t2a", "t3a"}
    assert youtube_client.search_calls == ["T1", "T2", "T3"]  # T4 完全不參與這次篩選

    t4_row = next(t for t in fake_db.select("youtube_topics") if t["topic"] == "T4")
    assert t4_row["last_recommended_on"] == date(2026, 8, 12)  # 未被更動


def test_select_weekly_recommendations_shared_video_guaranteed_round_not_double_picked(fake_db):
    # v-shared 同時是 A、B 兩個主題各自分數最高的候選（保底輪的第一名）。
    # A 保底先拿走 v-shared，B 保底輪應該跳過它、改拿 B 自己分數次高的 b2，
    # 而不是把 v-shared 重複算成兩個主題的保底名額。
    _seed_topic(fake_db, topic="A")
    _seed_topic(fake_db, topic="B")
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={
            "A": [_search_result("v-shared"), _search_result("a2")],
            "B": [_search_result("v-shared"), _search_result("b2")],
        },
        details_by_video_id={
            "v-shared": _detail("v-shared"), "a2": _detail("a2"), "b2": _detail("b2"),
        },
    )
    llm_client = _FakeLLMClient(responses=["1: 9\n2: 1", "1: 9\n2: 2"])

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    video_ids = [p["video_id"] for p in result]
    assert video_ids.count("v-shared") == 1
    assert len(result) == len(set(video_ids))
    assert set(video_ids) == {"v-shared", "b2", "a2"}


def test_select_weekly_recommendations_shared_video_in_leftovers_not_double_picked(fake_db):
    # v-shared 不是任何主題的保底第一名，所以會同時留在 A、B 兩個主題的 leftovers 候選裡；
    # 補滿輪處理到第二次出現時（名額仍未滿）必須跳過，不能重複計入 picks。
    _seed_topic(fake_db, topic="A")
    _seed_topic(fake_db, topic="B")
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={
            "A": [_search_result("a-top"), _search_result("v-shared"), _search_result("a2")],
            "B": [_search_result("b-top"), _search_result("v-shared"), _search_result("b2")],
        },
        details_by_video_id={
            "a-top": _detail("a-top"), "v-shared": _detail("v-shared"), "a2": _detail("a2"),
            "b-top": _detail("b-top"), "b2": _detail("b2"),
        },
    )
    llm_client = _FakeLLMClient(responses=["1: 9\n2: 7\n3: 3", "1: 8\n2: 7\n3: 2"])

    result = youtube.select_weekly_recommendations(
        fake_db, youtube_client, llm_client, 1, date(2026, 8, 13), total=5
    )

    video_ids = [p["video_id"] for p in result]
    assert video_ids.count("v-shared") == 1
    assert len(result) == len(set(video_ids))
    assert set(video_ids) == {"a-top", "b-top", "v-shared", "a2", "b2"}


def test_select_weekly_recommendations_topic_with_no_candidates_contributes_nothing(fake_db):
    _seed_topic(fake_db, topic="Empty")
    youtube_client = _FakeYouTubeClient(search_results_by_topic={})
    llm_client = _FakeLLMClient()

    result = youtube.select_weekly_recommendations(fake_db, youtube_client, llm_client, 1, date(2026, 8, 13))

    assert result == []
    assert fake_db.select("youtube_pushed_videos") == []
    topic_row = fake_db.select("youtube_topics")[0]
    assert topic_row["last_recommended_on"] is None  # 沒有貢獻任何影片，不更新輪替時間


# --- format_push_message ---


def test_format_push_message_empty_returns_none():
    assert youtube.format_push_message([]) is None


def test_format_push_message_lists_markdown_links():
    picks = [
        {"title": "AI 教學", "url": "https://youtu.be/v1", "topic": "AI", "video_id": "v1", "score": 9.0},
    ]
    text = youtube.format_push_message(picks)
    assert "[AI 教學](https://youtu.be/v1)" in text
    assert "AI" in text


# --- check_and_push_weekly_youtube（FR-59）---


def _thursday_8am_utc():
    # 2026-08-13 是週四；台灣時間 08:00 = UTC 前一天 00:00。
    return datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)


def test_check_and_push_weekly_youtube_skips_when_not_thursday(fake_db):
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    telegram_client = _FakeTelegramClient()
    not_thursday = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)  # 週三

    youtube.check_and_push_weekly_youtube(fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=not_thursday)

    assert telegram_client.sent == []


def test_check_and_push_weekly_youtube_skips_when_wrong_hour(fake_db):
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    telegram_client = _FakeTelegramClient()
    wrong_hour = datetime(2026, 8, 13, 5, 0, tzinfo=timezone.utc)  # 台灣時間 13:00

    youtube.check_and_push_weekly_youtube(fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=wrong_hour)

    assert telegram_client.sent == []


def test_check_and_push_weekly_youtube_skips_when_no_owner(fake_db):
    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=_thursday_8am_utc())

    assert telegram_client.sent == []


def test_check_and_push_weekly_youtube_skips_when_toggle_disabled(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "tech_intel", "is_enabled": False})
    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=_thursday_8am_utc())

    assert telegram_client.sent == []


def test_check_and_push_weekly_youtube_skips_when_already_run_today(fake_db):
    fake_db.insert(
        "users",
        {"telegram_user_id": 1, "role": "Robin", "is_owner": True, "youtube_last_run_on": date(2026, 8, 13)},
    )
    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=_thursday_8am_utc())

    assert telegram_client.sent == []


def test_check_and_push_weekly_youtube_happy_path_sends_message_and_marks_run(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    fake_db.insert("youtube_topics", {"user_id": owner_id, "topic": "AI", "last_recommended_on": None})
    youtube_client = _FakeYouTubeClient(
        search_results_by_topic={"AI": [_search_result("v1")]}, details_by_video_id={"v1": _detail("v1")},
    )
    llm_client = _FakeLLMClient(response_text="1: 8")
    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(fake_db, youtube_client, llm_client, telegram_client, now=_thursday_8am_utc())

    assert len(telegram_client.sent) == 1
    assert telegram_client.sent[0]["chat_id"] == 999
    assert "v1" in telegram_client.sent[0]["text"] or "Title v1" in telegram_client.sent[0]["text"]
    owner_row = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner_row["youtube_last_run_on"] == date(2026, 8, 13)


def test_check_and_push_weekly_youtube_no_picks_marks_run_but_does_not_send(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    # 沒有設定任何主題，select_weekly_recommendations 會回傳空清單。
    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(
        fake_db, _FakeYouTubeClient(), _FakeLLMClient(), telegram_client, now=_thursday_8am_utc()
    )

    assert telegram_client.sent == []
    owner_row = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner_row["youtube_last_run_on"] == date(2026, 8, 13)


def test_check_and_push_weekly_youtube_exception_marks_run_and_does_not_crash(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    fake_db.insert("youtube_topics", {"user_id": owner_id, "topic": "AI", "last_recommended_on": None})

    class _BoomYouTubeClient:
        def search_videos(self, query, max_results=10):
            raise RuntimeError("配額用罄")

    telegram_client = _FakeTelegramClient()

    youtube.check_and_push_weekly_youtube(
        fake_db, _BoomYouTubeClient(), _FakeLLMClient(), telegram_client, now=_thursday_8am_utc()
    )

    assert telegram_client.sent == []
    owner_row = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner_row["youtube_last_run_on"] == date(2026, 8, 13)
