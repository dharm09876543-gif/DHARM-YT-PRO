import json

import httpx
import pytest

from src.ai.gemini import GeminiError, GeminiMetadata


def _client(status=200, payload=None, capture=None):
    def handler(req):
        if capture is not None:
            capture.append(req)
        return httpx.Response(status, json=payload or {})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _reply(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


def test_generate_ok():
    seen = []
    g = GeminiMetadata("k", client=_client(payload=_reply(
        {"title": "Mathura Holi 2026 🎨", "description": "Colours everywhere", "tags": ["holi", "mathura"], "category_id": "19"}), capture=seen))
    m = g.generate("holi.mp4", notes="holi vlog", footer="Subscribe!", extra_tags=["vlog"])
    assert m.title.startswith("Mathura") and m.category_id == "19"
    assert m.description.endswith("Subscribe!") and m.tags == ["holi", "mathura", "vlog"]
    assert seen[0].headers["x-goog-api-key"] == "k" and "k" not in str(seen[0].url)


def test_bad_category_falls_back():
    g = GeminiMetadata("k", client=_client(payload=_reply({"title": "t", "category_id": "777"})))
    assert g.generate("a.mp4").category_id == "22"


def test_errors():
    with pytest.raises(GeminiError):
        GeminiMetadata("k", client=_client(429)).generate("a.mp4")
    with pytest.raises(GeminiError):
        GeminiMetadata("k", client=_client(payload={"oops": 1})).generate("a.mp4")


def test_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiError):
        GeminiMetadata()


def test_default_language_is_english_and_hindi_still_supported():
    seen = []
    ok = _reply({"title": "T", "description": "D", "tags": [], "category_id": "22"})
    GeminiMetadata("k", client=_client(payload=ok, capture=seen)).generate("a.mp4")
    assert "Language: English" in json.loads(seen[0].content)["contents"][0]["parts"][0]["text"]
    GeminiMetadata("k", client=_client(payload=ok, capture=seen)).generate("a.mp4", language="Hindi")
    assert "Language: Hindi" in json.loads(seen[1].content)["contents"][0]["parts"][0]["text"]


def test_discovery_passes_channel_language_default_english(engine, channel):
    from tests.test_drive_discovery import _tree
    from src.clients.drive_client import DriveClient
    from src.upload.discovery import discover_channel
    from src.upload.metadata import VideoMetadata
    langs = []

    class G:
        def generate(self, filename, **kw):
            langs.append(kw.get("language"))
            return VideoMetadata(title="AI", description="", tags=[], category_id="22")
    discover_channel(engine, channel, DriveClient(_tree()), {}, gemini=G())
    assert langs and set(langs) == {"English"}
