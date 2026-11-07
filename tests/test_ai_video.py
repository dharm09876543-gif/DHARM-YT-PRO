import json

import httpx

from src.ai.gemini import GeminiMetadata


def _client(seen):
    def handler(req: httpx.Request):
        seen.append((req.method, str(req.url)))
        u = str(req.url)
        if "/upload/v1beta/files" in u and req.headers.get("X-Goog-Upload-Command") == "start":
            return httpx.Response(200, headers={"x-goog-upload-url": "https://up.example/sess"})
        if u.startswith("https://up.example/sess"):
            return httpx.Response(200, json={"file": {"name": "files/abc", "uri": "https://g/files/abc",
                                                      "state": "PROCESSING"}})
        if req.method == "GET" and u.endswith("/v1beta/files/abc"):
            return httpx.Response(200, json={"name": "files/abc", "uri": "https://g/files/abc", "state": "ACTIVE"})
        if ":generateContent" in u:
            body = json.loads(req.content)
            parts = body["contents"][0]["parts"]
            assert parts[0]["file_data"]["file_uri"] == "https://g/files/abc"
            assert "Diwali sale" in parts[1]["text"]          # trends reach the prompt
            out = {"language": "Hindi", "title": "दिवाली पर सबसे सस्ता जुगाड़ 🔥", "description": "देखिए पूरा तरीका",
                   "hashtags": ["Shorts", "#दिवाली"], "tags": ["दिवाली", "jugaad"], "category_id": "26"}
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}]})
        if req.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_from_video_uses_video_language_and_cleans_up(tmp_path):
    seen = []
    vid = tmp_path / "x.mp4"; vid.write_bytes(b"0" * 1000)
    g = GeminiMetadata(api_key="k", model="m", client=_client(seen)); g.poll_s = 0
    m = g.generate_from_video(vid, "video/mp4", channel="C", trends=["Diwali sale"])
    assert m.title.startswith("दिवाली") and m.category_id == "26"
    assert "#Shorts" in m.description and "#दिवाली" in m.description
    assert "Shorts" in m.tags and m.detected_language == "Hindi"
    assert ("DELETE", "https://generativelanguage.googleapis.com/v1beta/files/abc") in seen


def test_ai_step_skips_sidecar_metadata(tmp_path):
    from src.upload.pipeline import UploadContext, _ai_from_video

    class Boom:
        def generate_from_video(self, *a, **k):
            raise AssertionError("must not be called")
    ctx = UploadContext(engine=None, cipher=None, yt=None, drive=None, quota=None, gemini=Boom())
    v = {"id": 1, "metadata_source": "sidecar"}
    assert _ai_from_video(ctx, v, tmp_path) is v
