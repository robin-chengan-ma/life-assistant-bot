"""LLM 通用 Client：目前串接 Gemini API（官方 google-genai SDK）。

命名為 llm 而不是 gemini，是為了讓對外呼叫介面（generate_text /
generate_with_image）維持穩定；未來若要換成其他供應商或新增第二個供應商，
呼叫端的程式碼不需要跟著改，只有這個檔案內部的實作需要調整。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 api_key。
"""
from google import genai
from google.genai import types

_DEFAULT_MODEL = "gemini-flash-latest"


class LLMClient:
    """封裝官方 google-genai SDK 的最小 Client。"""

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL):
        if not api_key:
            raise ValueError("api_key 不可為空")
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_text(self, prompt: str) -> str:
        """純文字生成，回傳模型的文字回應。"""
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return response.text

    def generate_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> str:
        """圖像 + 文字提示的生成呼叫（例如解析證照題目截圖）。"""
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[image_part, prompt],
        )
        return response.text

    def generate_with_search(self, prompt: str) -> tuple[str, bool]:
        """帶 Google Search 工具的生成呼叫，回傳 (回應文字, 是否實際使用了 Google Search)。

        是否要查網路由模型自行判斷（見 docs/specs/chat-core/SPEC.md ADR-1），本方法只負責
        從回應的 grounding_metadata 判讀這次有沒有真的觸發搜尋，不自己額外呼叫第二次 API。
        """
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return response.text, self._used_search(response)

    @staticmethod
    def _used_search(response) -> bool:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return False
        metadata = getattr(candidates[0], "grounding_metadata", None)
        if metadata is None:
            return False
        return bool(getattr(metadata, "web_search_queries", None))
