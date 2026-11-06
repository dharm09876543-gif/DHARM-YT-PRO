"""Gemini AI se YouTube title, description, tags banana.

Key: GEMINI_API_KEY env / GitHub Secret. Model: GEMINI_MODEL (default gemini-2.5-flash).
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
            raise GeminiError("GEMINI_API_KEY set nahi hai")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = client or httpx.Client(timeout=60)

    def generate(self, filename: str, channel: str = "", notes: str = "",
                 language: str = "Hindi", style: str = "friendly, energetic",
                 footer: str = "", extra_tags: list[str] | None = None) -> VideoMetadata:
        prompt = PROMPT.format(filename=filename, channel=channel or "-", notes=notes or "-",
                               language=language, style=style,
                               categories=json.dumps(CATEGORIES))
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
        r = self.client.post(API.format(model=self.model), json=body,
                             headers={"x-goog-api-key": self.key})
        if r.status_code == 429:
            raise GeminiError("Gemini quota/rate limit - thodi der baad")
        if r.status_code >= 400:
            raise GeminiError(f"Gemini error {r.status_code}")
        try:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text.strip().removeprefix("```json").removesuffix("```"))
        except (KeyError, IndexError, ValueError) as e:
            raise GeminiError("Gemini ka jawab samajh nahi aaya") from e
        desc = data.get("description", "")
        if footer:
            desc = f"{desc}\n\n{footer}"
        cat = str(data.get("category_id", "22"))
        meta = VideoMetadata(title=data.get("title") or filename,
                             description=desc,
                             tags=list(data.get("tags") or []) + list(extra_tags or []),
                             category_id=cat if cat in CATEGORIES else "22")
        return meta.clean()
