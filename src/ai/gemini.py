"""Generate YouTube title, description and tags with Gemini AI.

Key: GEMINI_API_KEY env / GitHub Secret. Model: GEMINI_MODEL (default gemini-3.6-flash).
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path

import httpx

from src.upload.metadata import CATEGORIES, VideoMetadata

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You are a YouTube SEO expert for an Indian creator.
Write metadata for a video.
Video file name: {filename}
Channel: {channel}
Topic / notes from creator: {notes}
Language: {language}
Style: {style}

Rules:
- title: catchy, honest (no clickbait lies), max 90 characters, may include 1 emoji.
- description: 150-300 words, first 2 lines hook the viewer, then summary, then
  3-5 hashtags at the end. No < or > characters. No fake links.
- tags: 10-15 search keywords, mix of {language} and English.
- category_id: best match from {categories}
Return ONLY JSON: {{"title": str, "description": str, "tags": [str], "category_id": str}}"""


VIDEO_PROMPT = """You are a YouTube SEO expert. WATCH this whole video and LISTEN to it carefully.
Channel: {channel}
Original file name (hint only, may be meaningless): {filename}

Step 1 - Language: find the main SPOKEN language of the video. If nobody speaks, use the language of the
on-screen text. If there is neither, use English. Write EVERYTHING below in that same language and its
normal script (Hindi in Devanagari, English in English, Tamil in Tamil, etc.).

Step 2 - Write metadata that describes what really happens in the video:
- title: catchy and honest (never promise something the video does not show), max 90 characters,
  may include 1 emoji. Put the most searched words first.
- description: 80-200 words. First 2 lines hook the viewer and say what the video shows, then a short
  summary. End with 4-6 hashtags on one line. No < or > characters. No links.
- hashtags: 4-6 hashtags (no spaces inside a hashtag). If this is a vertical / short video, include #Shorts.
- tags: 10-15 search keywords in the video language, plus a few English ones.
- category_id: best match from {categories}

Trending right now on YouTube ({region}). Use a trend word or hashtag ONLY if the video is really about it;
otherwise ignore this list completely:
{trends}

Return ONLY JSON: {{"language": str, "title": str, "description": str, "hashtags": [str], "tags": [str],
"category_id": str}}"""

BASE = "https://generativelanguage.googleapis.com"


class GeminiError(RuntimeError):
    pass


class GeminiMetadata:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 client: httpx.Client | None = None):
        self.key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.key:
            raise GeminiError("GEMINI_API_KEY is not set")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.client = client or httpx.Client(timeout=90)
        self.tried: list[tuple[str, int]] = []

    def _post(self, body: dict, model: str | None = None):
        return self.client.post(API.format(model=model or self.model), json=body,
                                headers={"x-goog-api-key": self.key})

    @staticmethod
    def _msg(r) -> str:
        try:
            return str(r.json().get("error", {}).get("message", ""))[:200]
        except Exception:
            return ""

    def _candidates(self) -> list[str]:
        try:
            r = self.client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                params={"pageSize": 200}, headers={"x-goog-api-key": self.key})
            if r.status_code >= 400:
                return []
            names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        except Exception:
            return []
        def rank(n: str):
            stable = not any(x in n for x in ("preview", "exp", "image", "tts", "live", "embedding"))
            return ("flash" in n, stable, "lite" not in n, n)
        names = [n for n in names if "gemini" in n]
        names.sort(key=rank, reverse=True)
        return names[:8]

    def _pick_model(self) -> str | None:
        try:
            r = self.client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                params={"pageSize": 200}, headers={"x-goog-api-key": self.key})
            if r.status_code >= 400:
                return None
            names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        except Exception:
            return None
        def rank(n: str):
            stable = not any(x in n for x in ("preview", "exp", "lite", "image", "tts", "live"))
            return ("flash" in n, stable, n)
        names.sort(key=rank, reverse=True)
        return names[0] if names else None

    def generate(self, filename: str, channel: str = "", notes: str = "",
                 language: str = "English", style: str = "friendly, energetic",
                 footer: str = "", extra_tags: list[str] | None = None) -> VideoMetadata:
        prompt = PROMPT.format(filename=filename, channel=channel or "-", notes=notes or "-",
                               language=language, style=style,
                               categories=json.dumps(CATEGORIES))
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
        r = self._post(body)
        self.tried.append((self.model, r.status_code))
        if r.status_code in (404, 429, 500, 503):  # model retired, or no free quota on it -> try others
            for alt in self._candidates():
                if alt == self.model:
                    continue
                try:
                    r2 = self._post(body, alt)
                except httpx.HTTPError:
                    continue
                self.tried.append((alt, r2.status_code))
                if r2.status_code < 400:
                    self.model, r = alt, r2
                    break
        if r.status_code == 429:
            raise GeminiError(f"Gemini quota/rate limit - try again later ({self._msg(r)})")
        if r.status_code >= 400:
            raise GeminiError(f"Gemini error {r.status_code} ({self._msg(r)})")
        try:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text.strip().removeprefix("```json").removesuffix("```"))
        except (KeyError, IndexError, ValueError) as e:
            raise GeminiError("Could not parse the Gemini response") from e
        desc = data.get("description", "")
        if footer:
            desc = f"{desc}\n\n{footer}"
        cat = str(data.get("category_id", "22"))
        meta = VideoMetadata(title=data.get("title") or filename,
                             description=desc,
                             tags=list(data.get("tags") or []) + list(extra_tags or []),
                             category_id=cat if cat in CATEGORIES else "22")
        return meta.clean()


    # ---------------- metadata from the real video ----------------
    def _upload_file(self, path: Path, mime: str) -> dict:
        size = path.stat().st_size
        r = self.client.post(f"{BASE}/upload/v1beta/files", headers={
            "x-goog-api-key": self.key, "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime, "Content-Type": "application/json"},
            json={"file": {"display_name": f"dy-{path.stem[:40]}"}})
        url = r.headers.get("x-goog-upload-url")
        if r.status_code >= 400 or not url:
            raise GeminiError(f"Gemini file upload start failed {r.status_code} ({self._msg(r)})")
        with open(path, "rb") as fh:
            r = self.client.post(url, content=fh.read(), headers={
                "Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize"}, timeout=600)
        if r.status_code >= 400:
            raise GeminiError(f"Gemini file upload failed {r.status_code} ({self._msg(r)})")
        return r.json()["file"]

    def _wait_active(self, f: dict, timeout_s: int = 300) -> dict:
        end = time.monotonic() + timeout_s
        while f.get("state") == "PROCESSING":
            if time.monotonic() > end:
                raise GeminiError("Gemini is still processing the video (timeout)")
            time.sleep(self.poll_s)
            r = self.client.get(f"{BASE}/v1beta/{f['name']}", headers={"x-goog-api-key": self.key})
            if r.status_code >= 400:
                raise GeminiError(f"Gemini file status error {r.status_code}")
            f = r.json()
        if f.get("state") != "ACTIVE":
            raise GeminiError(f"Gemini could not read the video (state {f.get('state')})")
        return f

    def _delete_file(self, name: str) -> None:
        try:
            self.client.delete(f"{BASE}/v1beta/{name}", headers={"x-goog-api-key": self.key})
        except Exception:  # noqa: BLE001 - Gemini deletes files after 48h anyway
            pass

    poll_s = 3

    def generate_from_video(self, path: Path, mime: str | None = None, channel: str = "",
                            filename: str = "", trends: list[str] | None = None, region: str = "IN",
                            footer: str = "", extra_tags: list[str] | None = None) -> VideoMetadata:
        path = Path(path)
        mime = mime or mimetypes.guess_type(path.name)[0] or "video/mp4"
        f = self._wait_active(self._upload_file(path, mime))
        try:
            prompt = VIDEO_PROMPT.format(channel=channel or "-", filename=filename or path.name,
                                         categories=json.dumps(CATEGORIES), region=region,
                                         trends="\n".join(f"- {t}" for t in (trends or [])[:25]) or "- (none)")
            body = {"contents": [{"parts": [{"file_data": {"mime_type": mime, "file_uri": f["uri"]}},
                                            {"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
            r = self._post(body)
            self.tried.append((self.model, r.status_code))
            if r.status_code in (404, 429, 500, 503):
                for alt in self._candidates():
                    if alt == self.model:
                        continue
                    try:
                        r2 = self._post(body, alt)
                    except httpx.HTTPError:
                        continue
                    self.tried.append((alt, r2.status_code))
                    if r2.status_code < 400:
                        self.model, r = alt, r2
                        break
            if r.status_code >= 400:
                raise GeminiError(f"Gemini error {r.status_code} ({self._msg(r)})")
            try:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(txt.strip().removeprefix("```json").removesuffix("```"))
            except (KeyError, IndexError, ValueError) as e:
                raise GeminiError("Could not parse the Gemini response") from e
        finally:
            self._delete_file(f["name"])
        tags_h = [h if h.startswith("#") else f"#{h}" for h in (data.get("hashtags") or []) if str(h).strip()]
        tags_h = [h.replace(" ", "") for h in tags_h]
        desc = str(data.get("description") or "").strip()
        missing = [h for h in tags_h if h.lower() not in desc.lower()]
        if missing:
            desc = f"{desc}\n\n{' '.join(missing)}"
        if footer:
            desc = f"{desc}\n\n{footer}"
        cat = str(data.get("category_id", "22"))
        tags = list(data.get("tags") or []) + [h.lstrip("#") for h in tags_h] + list(extra_tags or [])
        seen, uniq = set(), []
        for t in tags:
            k = str(t).strip().lower()
            if k and k not in seen:
                seen.add(k); uniq.append(str(t).strip())
        meta = VideoMetadata(title=data.get("title") or Path(filename or path.name).stem,
                             description=desc, tags=uniq,
                             category_id=cat if cat in CATEGORIES else "22")
        meta = meta.clean()
        meta.detected_language = str(data.get("language") or "")  # a name like "Hindi", not a code
        return meta
