"""YouTube metadata validation (current API limits)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

TITLE_MAX = 100
DESC_MAX = 5000            # bytes
TAGS_TOTAL_MAX = 500       # characters, all tags combined
VALID_PRIVACY = {"public", "unlisted", "private"}
CATEGORIES = {"1": "Film & Animation", "2": "Autos", "10": "Music", "15": "Pets & Animals",
              "17": "Sports", "19": "Travel", "20": "Gaming", "22": "People & Blogs",
              "23": "Comedy", "24": "Entertainment", "25": "News & Politics",
              "26": "Howto & Style", "27": "Education", "28": "Science & Technology"}


@dataclass
class VideoMetadata:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: str = "22"
    privacy_status: str = "private"
    publish_at: datetime | None = None
    language: str | None = None
    made_for_kids: bool = False

    def clean(self) -> "VideoMetadata":
        """Brings values within limits: removes < >, truncates length."""
        strip = lambda s: s.replace("<", "").replace(">", "").strip()  # noqa: E731
        self.title = strip(self.title)[:TITLE_MAX].strip()
        d = strip(self.description).encode("utf-8")[:DESC_MAX]
        self.description = d.decode("utf-8", "ignore")
        tags, total, seen = [], 0, set()
        for t in self.tags:
            t = strip(t).replace(",", "")
            cost = len(t) + (2 if " " in t else 0) + (1 if tags else 0)
            if not t or t.lower() in seen or total + cost > TAGS_TOTAL_MAX:
                continue
            tags.append(t); seen.add(t.lower()); total += cost
        self.tags = tags
        if self.publish_at:
            self.privacy_status = "private"   # scheduling needs private + publishAt
        return self

    def errors(self, now: datetime | None = None) -> list[str]:
        e = []
        if not self.title.strip():
            e.append("title is empty")
        if len(self.title) > TITLE_MAX:
            e.append(f"title {TITLE_MAX} characters is too long")
        if len(self.description.encode()) > DESC_MAX:
            e.append("description is longer than 5000 bytes")
        if any(c in self.title + self.description for c in "<>"):
            e.append("< > are not allowed")
        if self.category_id not in CATEGORIES:
            e.append(f"category_id {self.category_id} is invalid")
        if self.privacy_status not in VALID_PRIVACY:
            e.append("privacy is invalid")
        if self.publish_at:
            if self.publish_at.tzinfo is None:
                e.append("publish_at needs a timezone")
            elif self.publish_at <= (now or datetime.now(timezone.utc)):
                e.append("publish_at must be in the future")
            if self.privacy_status != "private":
                e.append("privacy must be 'private' for a scheduled video")
        return e

    def to_youtube_body(self) -> dict:
        status = {"privacyStatus": self.privacy_status, "selfDeclaredMadeForKids": self.made_for_kids}
        if self.publish_at:
            status["publishAt"] = self.publish_at.isoformat()
        snippet = {"title": self.title, "description": self.description,
                   "tags": self.tags, "categoryId": self.category_id}
        if self.language:
            snippet["defaultLanguage"] = self.language
            snippet["defaultAudioLanguage"] = self.language
        return {"snippet": snippet, "status": status}
