"""YouTube Data API v3 通用 Client：用 API Key 認證（不需要 OAuth），查詢技術情報候選影片與
其統計數字。

對外暴露 `search_videos()`（`search.list`，依關鍵字取得候選影片中繼資料）與
`get_video_details()`（`videos.list`，批次補上觀看數/讚數/留言數），只回傳中繼資料與統計數字，
不下載或處理影音本身（對應 docs/specs/robinson/SPEC.md FR-57、ADR-21）。篩選/排序/推播等商業
邏輯一律由呼叫端（`src/bot/youtube.py`）決定，本模組只負責跟 YouTube API 溝通。
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from submodules.retry.client import call_with_retry

# 2026-08-08：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i）。只重試「暫時性錯誤」：
# HTTP 429／5xx 與連線/逾時類例外；配額用罄（403 quotaExceeded）等其他 4xx 重試也沒用，直接往外拋，
# 交由呼叫端依 FR-59c 優雅降級。
_RETRYABLE_HTTP_STATUS_MIN = 500
_RETRYABLE_RATE_LIMIT_STATUS = 429


def _is_retryable_google_api_error(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        status_code = getattr(exc.resp, "status", None)
        if status_code is None:
            return False
        return status_code == _RETRYABLE_RATE_LIMIT_STATUS or status_code >= _RETRYABLE_HTTP_STATUS_MIN
    return isinstance(exc, (ConnectionError, TimeoutError))


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


class YouTubeClient:
    """封裝 YouTube Data API v3 的最小 Client（API Key 認證，僅支援搜尋與查詢統計資料）。"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("api_key 不可為空")
        self._service = build("youtube", "v3", developerKey=api_key)

    def search_videos(self, query: str, max_results: int = 10) -> list[dict]:
        """依關鍵字搜尋候選影片（`search.list`，`order=relevance`），回傳
        `[{"video_id", "title", "description", "channel_title", "published_at", "url"}, ...]`。
        消耗 100 Units／次（見 FR-59b）。
        """
        request = self._service.search().list(
            part="snippet", q=query, type="video", order="relevance", maxResults=max_results,
        )
        response = call_with_retry(request.execute, is_retryable=_is_retryable_google_api_error)

        results = []
        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            results.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "url": _video_url(video_id),
            })
        return results

    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """批次查詢影片的中繼資料與統計數字（`videos.list`，一次最多 50 支，
        成本約每 50 支 1 Unit，見 FR-59b），回傳
        `[{"video_id", "title", "description", "channel_title", "published_at",
        "view_count", "like_count", "comment_count", "url"}, ...]`。

        `video_ids` 為空清單時直接回傳空清單，不呼叫 API（避免無意義的請求）。
        讚數/留言數若被上傳者關閉會不存在於回應中，缺值一律當作 0。
        """
        if not video_ids:
            return []

        request = self._service.videos().list(part="snippet,statistics", id=",".join(video_ids))
        response = call_with_retry(request.execute, is_retryable=_is_retryable_google_api_error)

        results = []
        for item in response.get("items", []):
            video_id = item.get("id")
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            results.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "view_count": int(statistics.get("viewCount", 0)),
                "like_count": int(statistics.get("likeCount", 0)),
                "comment_count": int(statistics.get("commentCount", 0)),
                "url": _video_url(video_id),
            })
        return results
