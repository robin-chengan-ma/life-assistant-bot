from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from src.bot import image
from src.bot.state import ConversationStateStore


class _FakeImageLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 image.py 會用到的 generate_with_image。"""

    def __init__(self, response_text="這是一張貓咪的照片"):
        self.response_text = response_text
        self.last_prompt = None
        self.last_image_bytes = None
        self.last_mime_type = None

    def generate_with_image(self, prompt, image_bytes, mime_type="image/jpeg"):
        self.last_prompt = prompt
        self.last_image_bytes = image_bytes
        self.last_mime_type = mime_type
        return self.response_text


class _FakeGDriveClient:
    def __init__(self, url="https://drive.google.com/file/d/fake123/view"):
        self.url = url
        self.last_upload = None

    def upload_file(self, filename, content, mime_type):
        self.last_upload = {"filename": filename, "content": content, "mime_type": mime_type}
        return self.url


def _make_test_image_bytes(size=(2000, 1500)) -> bytes:
    image_obj = Image.new("RGB", size, color=(255, 0, 0))
    buffer = BytesIO()
    image_obj.save(buffer, format="PNG")
    return buffer.getvalue()


# --- compress_image ---


def test_compress_image_resizes_within_max_dimension():
    original_bytes = _make_test_image_bytes(size=(2000, 1500))

    compressed_bytes = image.compress_image(original_bytes)

    result = Image.open(BytesIO(compressed_bytes))
    assert result.format == "JPEG"
    assert result.width <= 1024
    assert result.height <= 1024


def test_compress_image_converts_non_rgb_mode():
    # RGBA（例如帶透明背景的 PNG）要能正常轉存為 JPEG（JPEG 不支援 alpha channel）
    image_obj = Image.new("RGBA", (500, 500), color=(0, 255, 0, 128))
    buffer = BytesIO()
    image_obj.save(buffer, format="PNG")

    compressed_bytes = image.compress_image(buffer.getvalue())

    result = Image.open(BytesIO(compressed_bytes))
    assert result.mode == "RGB"


# --- build_upload_filename ---


def test_build_upload_filename_matches_adr13_format():
    fixed_time = datetime(2026, 7, 31, 15, 30, 0, tzinfo=timezone.utc)

    filename = image.build_upload_filename("爸爸", now=fixed_time)

    assert filename == "爸爸_20260731153000_圖片辨識.jpg"


def test_build_upload_filename_accepts_custom_purpose():
    fixed_time = datetime(2026, 7, 31, 15, 30, 0, tzinfo=timezone.utc)

    filename = image.build_upload_filename("媽媽", purpose="飲食紀錄", now=fixed_time)

    assert filename == "媽媽_20260731153000_飲食紀錄.jpg"


# --- save_media_upload：2026-08-01 已抽到 src/bot/media.py，見 test_media.py ---


# --- handle_image_message ---


def test_handle_image_message_happy_path_returns_reply_without_marker(fake_db):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient()
    llm_client = _FakeImageLLMClient(response_text="這是一盤義大利麵")
    store = ConversationStateStore()

    reply = image.handle_image_message(
        fake_db,
        gdrive_client,
        [llm_client],
        store,
        telegram_user_id=1,
        user_id=1,
        user_role="爸爸",
        image_bytes=original_bytes,
        caption="這是什麼？",
    )

    assert reply == "這是一盤義大利麵"
    assert store.get(1) is None


def test_handle_image_message_uploads_original_to_gdrive_and_logs(fake_db):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient(url="https://drive/original")
    llm_client = _FakeImageLLMClient()
    store = ConversationStateStore()

    image.handle_image_message(
        fake_db, gdrive_client, [llm_client], store, telegram_user_id=1, user_id=42,
        user_role="爸爸", image_bytes=original_bytes, caption=None,
    )

    # 上傳到 Drive 的是原始 bytes，不是壓縮後的版本（ADR-13：只存原始檔）
    assert gdrive_client.last_upload["content"] == original_bytes
    rows = fake_db.select("media_uploads", where="user_id = %s", params=(42,))
    assert len(rows) == 1
    assert rows[0]["gdrive_url"] == "https://drive/original"
    assert rows[0]["media_type"] == "image"


def test_handle_image_message_sends_compressed_bytes_to_llm(fake_db):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient()
    llm_client = _FakeImageLLMClient()
    store = ConversationStateStore()

    image.handle_image_message(
        fake_db, gdrive_client, [llm_client], store, telegram_user_id=1, user_id=1,
        user_role="爸爸", image_bytes=original_bytes, caption=None,
    )

    # 送給 LLM 的不是原始 bytes，而是壓縮後、縮小尺寸的版本
    assert llm_client.last_image_bytes != original_bytes
    compressed_image = Image.open(BytesIO(llm_client.last_image_bytes))
    assert compressed_image.width <= 1024
    assert compressed_image.height <= 1024


def test_handle_image_message_prompt_includes_caption(fake_db):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient()
    llm_client = _FakeImageLLMClient()
    store = ConversationStateStore()

    image.handle_image_message(
        fake_db, gdrive_client, [llm_client], store, telegram_user_id=1, user_id=1,
        user_role="爸爸", image_bytes=original_bytes, caption="這道菜熱量多少？",
    )

    assert "這道菜熱量多少？" in llm_client.last_prompt


def test_handle_image_message_sets_pending_state_when_uncertain(fake_db):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient()
    llm_client = _FakeImageLLMClient(response_text="[NEED_CONFIRM] 這個食材是什麼看不清楚，可以說明一下嗎？")
    store = ConversationStateStore()

    reply = image.handle_image_message(
        fake_db, gdrive_client, [llm_client], store, telegram_user_id=1, user_id=7,
        user_role="爸爸", image_bytes=original_bytes, caption="幫我分析這道菜",
    )

    assert reply == "這個食材是什麼看不清楚，可以說明一下嗎？"
    state = store.get(1)
    assert state["flow"] == "pending_image_confirm"
    assert state["target_user_id"] == 7
    assert state["original_caption"] == "幫我分析這道菜"
    assert state["llm_client_index"] == 0
    assert isinstance(state["image_bytes"], bytes)


def test_handle_image_message_picks_from_multiple_llm_clients(fake_db, monkeypatch):
    original_bytes = _make_test_image_bytes()
    gdrive_client = _FakeGDriveClient()
    client_a = _FakeImageLLMClient(response_text="A 回答")
    client_b = _FakeImageLLMClient(response_text="B 回答")
    store = ConversationStateStore()

    monkeypatch.setattr(image.random, "choice", lambda seq: seq[1])

    reply = image.handle_image_message(
        fake_db, gdrive_client, [client_a, client_b], store, telegram_user_id=1, user_id=1,
        user_role="爸爸", image_bytes=original_bytes, caption=None,
    )

    assert reply == "B 回答"
    assert client_a.last_prompt is None  # 沒被選到的那把不該被呼叫


# --- handle_image_confirm_step ---


def test_handle_image_confirm_step_reanalyzes_with_clarification():
    llm_client = _FakeImageLLMClient(response_text="確認後：這是茄子")
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_image_confirm",
            "image_bytes": b"fake-compressed-bytes",
            "original_caption": "這道菜有哪些食材？",
            "target_user_id": 7,
            "llm_client_index": 0,
        },
    )

    reply = image.handle_image_confirm_step([llm_client], store, telegram_user_id=1, text="是紫色的那個食材")

    assert reply == "確認後：這是茄子"
    assert "是紫色的那個食材" in llm_client.last_prompt
    assert llm_client.last_image_bytes == b"fake-compressed-bytes"
    assert store.get(1) is None


def test_handle_image_confirm_step_uses_correct_client_index():
    client_a = _FakeImageLLMClient(response_text="A")
    client_b = _FakeImageLLMClient(response_text="B")
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_image_confirm",
            "image_bytes": b"fake-bytes",
            "original_caption": None,
            "target_user_id": 1,
            "llm_client_index": 1,
        },
    )

    reply = image.handle_image_confirm_step([client_a, client_b], store, telegram_user_id=1, text="補充說明")

    assert reply == "B"
    assert client_a.last_prompt is None
