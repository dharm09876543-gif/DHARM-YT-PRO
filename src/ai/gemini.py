"""Generate YouTube title, description and tags with Gemini AI.

Key: GEMINI_API_KEY env / GitHub Secret. Model: GEMINI_MODEL (default gemini-3.6-flash).
"""
from __future__ import annotations

import json
import os

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
        if r.status_code in (404, 429):  # model retired, or no free quota on it -> try others
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
