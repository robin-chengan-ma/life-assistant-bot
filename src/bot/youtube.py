"""YouTube 技術情報模組（對應 docs/specs/robinson/SPEC.md FR-57～FR-59、ADR-21，Step 3.4）。

僅 Robin 可用（`tech_intel` 功能開關，與每日技術分享共用，見 feature-toggles SPEC.md FR-3 追記）。
負責：多組主題管理（FR-57a）、候選影片蒐集與篩選（FR-57、FR-58a、FR-58d）、LLM 語意判讀評分
（FR-58b）、多主題「保底 + 輪替」分配（FR-58c）、每週四固定推播（FR-59）。不處理 Telegram 對話
狀態機（主題新增/移除的多輪反問，那是 `src/bot/commands.py` 的責任），這裡保持純粹的資料操作與
計算，方便獨立測試。

**FR-58c 多主題分配演算法（見 ADR-21 決策 4）**：每週固定推薦 `total`（預設 3）支影片。依
`youtube_topics.last_recommended_on` 由舊到新排序（`NULL` 視為最舊、最優先），取前
`min(主題數, total)` 個主題為「本次涉及主題」；每個涉及主題各自蒐集/篩選/評分候選影片後，先各
保底取 1 支分數最高的，若保底完還不夠 `total`，剩餘名額從這些涉及主題的候選清單（扣掉已保底的）
裡挑分數最高的依序補滿。這個通用規則剛好能推導出 Robin 明確要求的三種情境：只有 1 個主題時
`min(1,3)=1` 個涉及主題保底 1 支、剩餘 2 支從同一主題候選裡補滿（等於「該組出 3 支」）；2 個主題
時 `min(2,3)=2` 個涉及主題各保底 1 支、剩餘 1 支從兩組候選裡選分數最高者；3 個以上主題時
`min(n,3)=3` 個涉及主題保底 3 支剛好用完名額（等於「優先 3 組各出 1 支」）。**已知簡化**：若涉及
主題剛好都篩不出候選影片（極端邊界情況），不會回頭挑第 4 個以後的主題遞補，這種情況下當週會少於
`total` 支推薦，屬於 Robin 已知情並接受的簡化（見 SPEC.md ADR-21）。

**FR-58b LLM 評分（取代原 Rule-based Weight，見 ADR-21）**：把候選影片的標題、說明欄、頻道名稱、
發布時間、觀看數/讚數/留言數一次交給 LLM，要求針對每支影片輸出 0～10 分的綜合分數（是否符合主題
＋數據代表的熱度/品質），不做時長判斷（FR-58a 修正，Robin 明確表示不用排除 Shorts，品質完全交給
LLM 判讀）。LLM 輸出格式解析失敗時，優雅降級為依觀看數排序（`score` 欄位標記為 `None`），不讓整
個 Pipeline 卡住。
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PUSH_WEEKDAY_THURSDAY = 3  # Python datetime.weekday()：Monday=0 ... Thursday=3
_PUSH_HOUR = 8
_FEATURE_KEY = "tech_intel"
_DEFAULT_TOTAL_RECOMMENDATIONS = 3
_DEFAULT_SEARCH_RESULTS_PER_TOPIC = 10
_HISTORY_DEDUPE_WINDOW_DAYS = 30
_DESCRIPTION_SNIPPET_LENGTH = 200

_RANKING_PROMPT_TEMPLATE = (
    "以下是使用者訂閱的技術情報主題「{topic}」，請針對每一支候選影片，依據標題、說明欄是否"
    "符合這個主題，加上觀看次數/讚數/留言數等數據代表的熱度與品質，給出一個 0～10 分的綜合分數"
    "（分數越高代表越推薦），完全不需要考慮影片時長長短。\n\n"
    "候選影片清單：\n{candidates_text}\n\n"
    "請針對每一支影片，嚴格依照下面格式各自輸出一行，不要輸出其他任何文字：\n"
    "<編號>: <分數>"
)
_SCORE_LINE_PATTERN = re.compile(r"^\s*(\d+)\s*[:：]\s*(\d+(?:\.\d+)?)")

_PUSH_MESSAGE_HEADER = "📺 主任，這週的技術情報影片來囉！"


# --- FR-57a：多主題管理 ---


def list_topics(db: CloudSQLClient, user_id: int) -> list[dict]:
    """列出這個使用者設定的所有主題，依新增順序（`id`）排序。"""
    rows = db.select("youtube_topics", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: row["id"])
    return rows


def _get_topic(db: CloudSQLClient, user_id: int, topic: str) -> dict | None:
    return db.select(
        "youtube_topics", where="user_id = %s AND topic = %s", params=(user_id, topic), fetch_one=True
    )


def add_topic(db: CloudSQLClient, user_id: int, topic: str) -> dict:
    """新增一組主題；已存在同樣文字的主題時不重複新增，回傳 `{"already_exists": bool, "topic"}`
    供呼叫端組回覆文字。"""
    existing = _get_topic(db, user_id, topic)
    if existing is not None:
        return {"already_exists": True, "topic": topic}

    db.insert("youtube_topics", {"user_id": user_id, "topic": topic, "last_recommended_on": None})
    return {"already_exists": False, "topic": topic}


def remove_topic(db: CloudSQLClient, user_id: int, topic_id: int) -> bool:
    """依 `id` 刪除一組主題（限這個使用者自己的），回傳是否有實際刪除到（`id` 不存在或不屬於這
    個使用者則回傳 `False`）。"""
    deleted = db.delete("youtube_topics", where="id = %s AND user_id = %s", params=(topic_id, user_id))
    return deleted > 0


def format_topics_list(topics: list[dict]) -> str:
    """把 `list_topics()` 的結果組成含編號的文字清單，供「我的YouTube主題」／「移除YouTube主題」
    共用（`src/bot/commands.py` 負責決定要不要接著進入可移除的對話狀態）。"""
    if not topics:
        return "目前還沒有設定任何 YouTube 技術情報主題喔！可以用「新增YouTube主題」設定第一組。"

    lines = ["📺 目前設定的 YouTube 技術情報主題："]
    for index, topic in enumerate(topics, start=1):
        last_recommended = topic.get("last_recommended_on")
        recommended_text = f"上次推播：{last_recommended}" if last_recommended else "尚未推播過"
        lines.append(f"{index}. {topic['topic']}（{recommended_text}）")
    return "\n".join(lines)


def _mark_topic_recommended(db: CloudSQLClient, user_id: int, topic: str, recommended_on: date) -> None:
    row = _get_topic(db, user_id, topic)
    if row is not None:
        db.update("youtube_topics", {"last_recommended_on": recommended_on}, where="id = %s", params=(row["id"],))


# --- FR-58a：格式過濾（僅去重，不排除 Shorts，見 ADR-21 決策 5）---


def _dedupe_by_video_id(candidates: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for candidate in candidates:
        if candidate["video_id"] in seen:
            continue
        seen.add(candidate["video_id"])
        result.append(candidate)
    return result


# --- FR-58d：歷史比對（過去 30 天內已推播之 video_id 去重）---


def _filter_recently_pushed(
    db: CloudSQLClient, user_id: int, candidates: list[dict], today: date, window_days: int = _HISTORY_DEDUPE_WINDOW_DAYS
) -> list[dict]:
    cutoff = today - timedelta(days=window_days)
    pushed_rows = db.select("youtube_pushed_videos", where="user_id = %s", params=(user_id,))
    recently_pushed_ids = {row["video_id"] for row in pushed_rows if row["pushed_on"] >= cutoff}
    return [c for c in candidates if c["video_id"] not in recently_pushed_ids]


# --- FR-58b：LLM 語意判讀評分 ---


def _build_ranking_prompt(topic: str, candidates: list[dict]) -> str:
    lines = []
    for index, candidate in enumerate(candidates, start=1):
        description = (candidate.get("description") or "")[:_DESCRIPTION_SNIPPET_LENGTH]
        lines.append(
            f"{index}. 標題：{candidate['title']}\n"
            f"   頻道：{candidate['channel_title']}\n"
            f"   說明欄：{description}\n"
            f"   發布時間：{candidate['published_at']}\n"
            f"   觀看數：{candidate['view_count']}　讚數：{candidate['like_count']}　"
            f"留言數：{candidate['comment_count']}"
        )
    return _RANKING_PROMPT_TEMPLATE.format(topic=topic, candidates_text="\n".join(lines))


def _parse_scores(raw: str, count: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for line in raw.splitlines():
        match = _SCORE_LINE_PATTERN.match(line)
        if not match:
            continue
        index = int(match.group(1))
        if 1 <= index <= count:
            scores[index] = float(match.group(2))
    return scores


def score_candidates_for_topic(llm_client, topic: str, candidates: list[dict]) -> list[dict]:
    """把候選影片交給 LLM 評分並依分數由高到低排序，回傳每筆候選加上 `score` 欄位的清單。

    LLM 輸出解析不出任何有效分數時（格式跑掉等異常情況），優雅降級為依觀看數排序，`score` 標記
    為 `None`，不讓整個推播 Pipeline 因為一次解析失敗就完全沒有結果（FR-58b）。
    """
    if not candidates:
        return []

    raw = llm_client.generate_text(_build_ranking_prompt(topic, candidates))
    scores = _parse_scores(raw, len(candidates))

    if not scores:
        _logger.warning("YouTube 候選影片 LLM 評分解析失敗（主題：%s），改用觀看數排序備援", topic)
        ranked = sorted(candidates, key=lambda c: c["view_count"], reverse=True)
        return [{**c, "score": None} for c in ranked]

    scored = [{**candidate, "score": scores.get(index, 0.0)} for index, candidate in enumerate(candidates, start=1)]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


# --- 候選蒐集（整合 FR-57／FR-58a／FR-58d／FR-58b）---


def _gather_scored_candidates(
    youtube_client, llm_client, db: CloudSQLClient, user_id: int, topic: str, today: date,
    search_limit: int = _DEFAULT_SEARCH_RESULTS_PER_TOPIC,
) -> list[dict]:
    search_results = youtube_client.search_videos(topic, max_results=search_limit)
    deduped = _dedupe_by_video_id(search_results)
    if not deduped:
        return []

    details = youtube_client.get_video_details([c["video_id"] for c in deduped])
    details_by_id = {detail["video_id"]: detail for detail in details}
    # 只保留查得到統計資料的候選（理論上不該發生查不到的情況，屬防禦性處理）。
    merged = [details_by_id[c["video_id"]] for c in deduped if c["video_id"] in details_by_id]

    filtered = _filter_recently_pushed(db, user_id, merged, today)
    if not filtered:
        return []

    return score_candidates_for_topic(llm_client, topic, filtered)


# --- FR-58c：多主題分配（保底 + 輪替）---


def _topics_by_priority(topics: list[dict]) -> list[dict]:
    """依 `last_recommended_on` 由舊到新排序，`NULL`（從未推播過）視為最優先。"""
    return sorted(topics, key=lambda t: (t["last_recommended_on"] is not None, t["last_recommended_on"]))


def select_weekly_recommendations(
    db: CloudSQLClient, youtube_client, llm_client, user_id: int, today: date,
    total: int = _DEFAULT_TOTAL_RECOMMENDATIONS,
) -> list[dict]:
    """FR-58c：計算這週要推薦的影片清單（見模組 docstring 演算法說明），並同步寫入
    `youtube_pushed_videos`（供下次 FR-58d 去重）與更新涉及主題的 `last_recommended_on`
    （供下次 FR-58c 輪替判斷）。回傳每筆推薦 `{"video_id", "title", "url", "topic", "score", ...}`。
    """
    topics = list_topics(db, user_id)
    if not topics:
        return []

    involved_topics = _topics_by_priority(topics)[: min(len(topics), total)]

    topic_candidates = {
        t["topic"]: _gather_scored_candidates(youtube_client, llm_client, db, user_id, t["topic"], today)
        for t in involved_topics
    }

    picks: list[dict] = []
    picked_video_ids: set[str] = set()

    # 保底：每個涉及主題各取分數最高的 1 支（沒有候選的主題這輪貢獻 0 支）。
    # 同一支影片可能同時符合多個主題的搜尋結果，此時要跳過已保底過的 video_id，
    # 改取該主題分數次高者，避免同一支影片被算成兩個主題的保底名額。
    for t in involved_topics:
        candidates = topic_candidates[t["topic"]]
        top = next((c for c in candidates if c["video_id"] not in picked_video_ids), None)
        if top:
            picks.append({**top, "topic": t["topic"]})
            picked_video_ids.add(top["video_id"])

    # 補滿：保底後名額還沒滿，從涉及主題的剩餘候選（扣掉已保底的）裡挑分數最高的依序補上。
    if len(picks) < total:
        leftovers = [
            {**candidate, "topic": t["topic"]}
            for t in involved_topics
            for candidate in topic_candidates[t["topic"]]
            if candidate["video_id"] not in picked_video_ids
        ]
        leftovers.sort(key=lambda c: c["score"] if c["score"] is not None else -1, reverse=True)
        for candidate in leftovers:
            if len(picks) >= total:
                break
            if candidate["video_id"] in picked_video_ids:
                continue
            picks.append(candidate)
            picked_video_ids.add(candidate["video_id"])

    picks = picks[:total]

    for topic_name in {p["topic"] for p in picks}:
        _mark_topic_recommended(db, user_id, topic_name, today)
    for pick in picks:
        db.insert(
            "youtube_pushed_videos",
            {"user_id": user_id, "video_id": pick["video_id"], "topic": pick["topic"], "pushed_on": today},
        )

    return picks


# --- 推播訊息格式化 ---


def format_push_message(picks: list[dict]) -> str | None:
    """組出推播訊息（Markdown 超連結，FR-58d）；沒有任何推薦時回傳 `None`，呼叫端據此跳過推播，
    避免無意義的空訊息。"""
    if not picks:
        return None

    lines = [_PUSH_MESSAGE_HEADER]
    for pick in picks:
        lines.append(f"・[{pick['title']}]({pick['url']})（主題：{pick['topic']}）")
    return "\n".join(lines)


# --- FR-59：每週四固定推播 ---


def _get_owner(db: CloudSQLClient) -> dict | None:
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def check_and_push_weekly_youtube(db: CloudSQLClient, youtube_client, llm_client, telegram_client, now: datetime | None = None) -> None:
    """FR-59a：固定台灣時間週四 08:00，依 FR-58c 選出這週要推薦的影片並推播；只在週四 08 點這個
    小時內執行，同一天最多執行一次（`users.youtube_last_run_on` 去重，比照
    `toeic_pipeline_last_run_on` 既有慣例）；`tech_intel` 功能開關關閉時跳過，不消耗任何配額。

    執行過程若拋出例外（FR-59c：超出配額或連線異常），記錄警告日誌並優雅結束，不影響 `/healthz`
    本身；當天已經標記為執行過，不會在剩餘時間內重複重試消耗配額（暫時性錯誤已在
    `submodules/youtube` 底層透過重試機制處理過，這裡拋出的多半是永久性問題，重試也沒用）。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.weekday() != _PUSH_WEEKDAY_THURSDAY or now_local.hour != _PUSH_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    if owner.get("youtube_last_run_on") == today:
        return

    try:
        picks = select_weekly_recommendations(db, youtube_client, llm_client, owner["id"], today)
    except Exception:
        _logger.exception("YouTube 技術情報週推播失敗，不影響健康檢查端點本身")
        db.update("users", {"youtube_last_run_on": today}, where="id = %s", params=(owner["id"],))
        return

    db.update("users", {"youtube_last_run_on": today}, where="id = %s", params=(owner["id"],))

    message = format_push_message(picks)
    if message is None:
        return
    telegram_client.send_text(chat_id=owner["telegram_user_id"], text=message)
