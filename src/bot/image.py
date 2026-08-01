"""影像辨識邏輯（對應 docs/specs/robinson/SPEC.md FR-17、FR-17a～FR-17c、ADR-13）。

處理使用者傳來的圖片：Pillow 壓縮（僅記憶體內即時處理，不落地存回 Google Drive，見
ADR-13 2026-07-31 更新）→ 隨機挑一把圖片辨識 Key 呼叫 Gemini → 若有看不清楚的地方
要反問使用者確認，不能用猜的（FR-17b）。下載 Telegram 檔案屬於 I/O 邊界，由呼叫端
（webhook.py）處理完、把原始 bytes 傳進來，這裡只處理「圖片辨識」本身的商業邏輯。
"""
import random
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from src.bot.media import save_media_upload
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_MAX_DIMENSION = 1024
_JPEG_QUALITY = 80
_UNCERTAIN_MARKER = "[NEED_CONFIRM]"

_BASE_PROMPT = (
    "你是 Robinson，請用溫暖、自然口語的語氣分析這張圖片，並回答使用者的問題（若沒有附加文字說明，"
    "就直接描述圖片內容並提供有幫助的資訊）。\n"
    "規則：\n"
    "1. 如果圖片中有部分內容你看不清楚或無法判斷（例如被遮住、模糊、角度看不到），不可以用猜的，"
    f"請具體說明是哪個部分不確定，並在回覆最前面加上 {_UNCERTAIN_MARKER} 標記；"
    "如果整張圖片你都能判斷清楚，就不要加這個標記，直接正常回答。\n"
    "2. 如果這是飲食/食物相關的分析（例如估算熱量、營養成分），務必在回覆中提醒使用者這是估算值、"
    "可能會有誤差、僅供參考，不能讓使用者誤以為是精確數值。\n"
)


def compress_image(image_bytes: bytes) -> bytes:
    """依 ADR-13：縮放至 1024×1024 以下、轉存 JPEG 品質 80，降低送給 Gemini 的 Payload。"""
    image = Image.open(BytesIO(image_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue()


def build_upload_filename(user_role: str, purpose: str = "圖片辨識", now: datetime | None = None) -> str:
    """依 ADR-13 命名規則：使用者稱呼＋當下時間戳記＋用途。"""
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    return f"{user_role}_{timestamp}_{purpose}.jpg"


def handle_image_message(
    db: CloudSQLClient,
    gdrive_client,
    image_llm_clients: list,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    user_role: str,
    image_bytes: bytes,
    caption: str | None,
) -> str:
    """處理使用者傳來的圖片：上傳原始檔到 Drive、記錄 media_uploads、壓縮後隨機挑一把
    圖片辨識 Key 呼叫 Gemini，回傳要回覆給使用者的文字。
    """
    gdrive_url = gdrive_client.upload_file(
        filename=build_upload_filename(user_role),
        content=image_bytes,
        mime_type="image/jpeg",
    )
    save_media_upload(db, user_id, "image", gdrive_url)

    compressed_bytes = compress_image(image_bytes)
    llm_client = random.choice(image_llm_clients)
    prompt = _BASE_PROMPT + f"\n使用者的問題／說明：{caption or '（無，請直接描述圖片內容）'}"
    reply_text = llm_client.generate_with_image(prompt, compressed_bytes, mime_type="image/jpeg")

    if reply_text.startswith(_UNCERTAIN_MARKER):
        question = reply_text[len(_UNCERTAIN_MARKER):].strip()
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_image_confirm",
                "image_bytes": compressed_bytes,
                "original_caption": caption,
                "target_user_id": user_id,
                "llm_client_index": image_llm_clients.index(llm_client),
            },
        )
        return question

    return reply_text


def handle_image_confirm_step(
    image_llm_clients: list,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 FR-17b 反問使用者後的下一則澄清訊息，帶著使用者的澄清重新分析一次圖片。"""
    state = state_store.get(telegram_user_id)
    state_store.clear(telegram_user_id)

    llm_client = image_llm_clients[state["llm_client_index"]]
    prompt = (
        _BASE_PROMPT
        + f"\n使用者的問題／說明：{state['original_caption'] or '（無，請直接描述圖片內容）'}"
        + f"\n\n你剛剛反問使用者不確定的地方，使用者的澄清是：「{text}」。"
        "請根據這個澄清重新分析這張圖片並給出最終答案，這次不能再加上不確定標記，"
        "如果還是有無法判斷的地方，就誠實說明並盡力回答，不要再反問第二次。"
    )
    return llm_client.generate_with_image(prompt, state["image_bytes"], mime_type="image/jpeg")
