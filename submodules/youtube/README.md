# youtube

YouTube Data API v3 通用 Client，用 API Key 認證（不需要 OAuth），查詢技術情報候選影片的中繼資料與統計數字（觀看數/讚數/留言數），不下載或處理影音本身。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `YOUTUBE_API_KEY` | Google Cloud Console 建立的 API Key，僅需啟用 YouTube Data API v3 |

## 安裝

```bash
pip install -r submodules/youtube/requirements.txt
```

## 使用範例

```python
from submodules.youtube.client import YouTubeClient

client = YouTubeClient(api_key="...")

candidates = client.search_videos("AI Agent 架構設計", max_results=10)
# [{"video_id": "...", "title": "...", "description": "...", "channel_title": "...",
#   "published_at": "...", "url": "https://www.youtube.com/watch?v=..."}, ...]

details = client.get_video_details([c["video_id"] for c in candidates])
# 額外補上 view_count／like_count／comment_count
```

## 設計限制（務必遵守）

1. 只支援搜尋與查詢統計資料（`search_videos`／`get_video_details`），不做其他寫入類操作——本模組只是輕量的唯讀資料獲取層。
2. 篩選（格式過濾/歷史去重）、LLM 語意判讀排序、多主題分配、推播等商業邏輯一律由呼叫端（`src/bot/youtube.py`）決定，本模組只負責跟 YouTube API 溝通。
3. `search_videos` 消耗 100 Units／次、`get_video_details` 消耗約每 50 支影片 1 Unit，配額管理與每日上限判斷由呼叫端負責（見 docs/specs/SPEC.md FR-59b）。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-57～FR-59、[docs/ADR/discuss/youtube-intel.md](../../docs/ADR/discuss/youtube-intel.md) ADR-21
