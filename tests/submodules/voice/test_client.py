"""submodules/voice/client.py 的單元測試。

不呼叫真正的 Groq API，一律 mock `requests.post`。
"""
from unittest.mock import MagicMock

import pytest

from submodules.voice import client as client_module
from submodules.voice.client import VoiceClient


def test_init_raises_on_empty_api_key():
    with pytest.raises(ValueError):
        VoiceClient(api_key="")


def _fake_response(text=""):
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()
    return response


def test_transcribe_posts_correct_multipart_payload(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response("今天天氣真好"))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = VoiceClient(api_key="fake-groq-key")
    result = client.transcribe(b"fake-audio-bytes", filename="voice.ogg", mime_type="audio/ogg")

    assert result == "今天天氣真好"
    called_url = mock_post.call_args.args[0]
    assert called_url == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert mock_post.call_args.kwargs["headers"] == {"Authorization": "Bearer fake-groq-key"}
    assert mock_post.call_args.kwargs["files"] == {"file": ("voice.ogg", b"fake-audio-bytes", "audio/ogg")}
    assert mock_post.call_args.kwargs["data"] == {"model": "whisper-large-v3", "response_format": "text"}


def test_transcribe_strips_surrounding_whitespace(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response("  哈囉，世界  \n"))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = VoiceClient(api_key="fake-groq-key")
    result = client.transcribe(b"fake-audio-bytes")

    assert result == "哈囉，世界"


def test_transcribe_uses_default_filename_and_mime_type(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response("預設值測試"))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = VoiceClient(api_key="fake-groq-key")
    client.transcribe(b"fake-audio-bytes")

    assert mock_post.call_args.kwargs["files"] == {"file": ("audio.ogg", b"fake-audio-bytes", "audio/ogg")}


def test_transcribe_raises_when_response_status_not_ok(monkeypatch):
    response = _fake_response("")
    response.raise_for_status.side_effect = RuntimeError("500 Server Error")
    mock_post = MagicMock(return_value=response)
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = VoiceClient(api_key="fake-groq-key")
    with pytest.raises(RuntimeError):
        client.transcribe(b"fake-audio-bytes")


def test_custom_model_is_used_in_request(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response("自訂模型測試"))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = VoiceClient(api_key="fake-groq-key", model="whisper-large-v3-turbo")
    client.transcribe(b"fake-audio-bytes")

    assert mock_post.call_args.kwargs["data"] == {"model": "whisper-large-v3-turbo", "response_format": "text"}
