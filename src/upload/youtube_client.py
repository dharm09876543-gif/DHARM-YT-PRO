"""YouTube Data API v3 wrapper. Every call is recorded in the quota ledger."""
from __future__ import annotations

from datetime import datetime

from src.utils.timeutil import parse_dt


class YouTubeClient:
    def __init__(self, service, quota=None):
        self.svc = service
        self.quota = quota

    def _rec(self, op: str) -> None:
        if self.quota:
            self.quota.record(op)

    def trending(self, region: str = "IN", count: int = 15) -> list[str]:
        """Titles + top tags of what is trending now (1 quota unit). Cached per client."""
        key = (region, count)
        cache = self.__dict__.setdefault("_trend_cache", {})
        if key not in cache:
            resp = self.svc.videos().list(part="snippet", chart="mostPopular", regionCode=region,
                                          maxResults=max(1, min(50, count))).execute()
            self._rec("videos.list")
            out = []
            for it in resp.get("items", []):
                sn = it.get("snippet", {})
                tags = ", ".join((sn.get("tags") or [])[:5])
                out.append(sn.get("title", "") + (f"  [tags: {tags}]" if tags else ""))
            cache[key] = out
        return cache[key]

    def insert_request(self, body: dict, media):
        """Resumable videos.insert request (not executed; the uploader drives next_chunk)."""
        return self.svc.videos().insert(part="snippet,status", body=body, media_body=media,
                                        notifySubscribers=False)

    def get_video(self, yt_id: str) -> dict | None:
        try:
            resp = self.svc.videos().list(part="snippet,status,processingDetails", id=yt_id).execute()
        finally:
            self._rec("videos.list")
        items = resp.get("items") or []
        return items[0] if items else None

    def set_thumbnail(self, yt_id: str, media) -> dict:
        try:
            return self.svc.thumbnails().set(videoId=yt_id, media_body=media).execute()
        finally:
            self._rec("thumbnails.set")

    def my_channel(self) -> dict | None:
        try:
            resp = self.svc.channels().list(part="snippet,contentDetails", mine=True).execute()
        finally:
            self._rec("channels.list")
        items = resp.get("items") or []
        return items[0] if items else None

    def find_recent_upload(self, title: str, since: datetime | None = None, pages: int = 2) -> str | None:
        """After an uncertain upload: is this video already on the channel? (title + time match)"""
        ch = self.my_channel()
        pl = ((ch or {}).get("contentDetails", {}).get("relatedPlaylists", {}) or {}).get("uploads")
        if not pl:
            return None
        token = None
        for _ in range(pages):
            try:
                resp = self.svc.playlistItems().list(part="snippet", playlistId=pl, maxResults=50,
                                                     pageToken=token).execute()
            finally:
                self._rec("playlistItems.list")
            for it in resp.get("items", []):
                sn = it.get("snippet", {})
                pub = parse_dt(sn.get("publishedAt"))
                if sn.get("title") == title and (since is None or pub is None or pub >= since):
                    return sn.get("resourceId", {}).get("videoId")
            token = resp.get("nextPageToken")
            if not token:
                break
        return None
