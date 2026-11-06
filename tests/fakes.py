"""Google API fakes - no network."""
from __future__ import annotations

import json
import re

from googleapiclient.errors import HttpError
from httplib2 import Response


def http_error(status: int, reason: str = "backendError") -> HttpError:
    body = json.dumps({"error": {"code": status, "errors": [{"reason": reason}]}}).encode()
    return HttpError(Response({"status": status}), body)


class _Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, **_):
        return self.fn()


# ---------------- Drive ----------------
class FakeDriveService:
    """files: id -> dict(name, mimeType, parents, ...); content: id -> bytes."""

    def __init__(self, files: dict, content: dict | None = None):
        self.files_db = files
        self.content = content or {}
        self.calls: list[tuple] = []

    def files(self):
        return self

    def list(self, q, pageToken=None, **_):
        self.calls.append(("list", q))
        parent = re.search(r"'([^']+)' in parents", q).group(1)
        items = [dict(id=i, **f) for i, f in self.files_db.items()
                 if parent in f.get("parents", []) and not f.get("trashed")]
        # 2 pages to test pagination
        half = len(items) // 2
        if pageToken is None and half:
            return _Exec(lambda: {"files": items[:half], "nextPageToken": "p2"})
        return _Exec(lambda: {"files": items[half:] if pageToken else items})

    def get(self, fileId, **_):
        return _Exec(lambda: dict(id=fileId, **self.files_db[fileId]))

    def get_media(self, fileId, **_):
        return _Exec(lambda: self.content[fileId])

    def update(self, fileId, body, **_):
        self.calls.append(("update", fileId, body))

        def run():
            self.files_db[fileId].update(body)
            return {"id": fileId, "trashed": self.files_db[fileId].get("trashed", False)}
        return _Exec(run)

    def delete(self, **_):  # pragma: no cover - must never be called
        raise AssertionError("files.delete was called! permanent delete is disabled")


def folder(parents):
    return {"name": "", "mimeType": "application/vnd.google-apps.folder", "parents": parents}


# ---------------- resumable upload server ----------------
class FakeUploadServer:
    """Simulated resumable upload server: session uri -> received bytes."""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.initiations = 0
        self.fail_plan: list = []      # popped before every chunk: None | Exception
        self.videos: dict[str, dict] = {}
        self.next_video_id = "yt_vid_001"

    def complete(self, uri):
        s = self.sessions[uri]
        vid = s.get("video_id") or self.next_video_id
        s["video_id"] = vid
        self.videos.setdefault(vid, {"id": vid})
        return {"id": vid, "snippet": s["body"]["snippet"], "status": s["body"]["status"]}


class _Progress:
    def __init__(self, p, total):
        self.resumable_progress, self.total_size = p, total


class FakeInsertRequest:
    """googleapiclient HttpRequest-like: resumable_uri, resumable_progress, _in_error_state, next_chunk."""

    def __init__(self, server: FakeUploadServer, body: dict, media):
        self.server, self.body, self.media = server, body, media
        self.resumable_uri = None
        self.resumable_progress = 0
        self._in_error_state = False
        self.status_queries = 0

    def next_chunk(self):
        srv, total = self.server, self.media.size
        if self.resumable_uri is None:
            srv.initiations += 1
            self.resumable_uri = f"https://upload.fake/s{srv.initiations}"
            srv.sessions[self.resumable_uri] = {"received": 0, "total": total, "body": self.body}
        elif self._in_error_state:
            self.status_queries += 1
            s = srv.sessions.get(self.resumable_uri)
            if s is None or s.get("expired"):
                from tests.fakes import http_error
                raise http_error(404, "notFound")
            if s["received"] >= s["total"]:
                return None, srv.complete(self.resumable_uri)
            self.resumable_progress = s["received"]
            self._in_error_state = False
        plan = srv.fail_plan.pop(0) if srv.fail_plan else None
        if plan == "lost_response":          # server accepted it, response lost
            s = srv.sessions[self.resumable_uri]
            s["received"] = min(total, self.resumable_progress + self.media.chunk)
            raise TimeoutError("network timeout")
        if isinstance(plan, Exception):
            raise plan
        s = srv.sessions[self.resumable_uri]
        s["received"] = min(total, self.resumable_progress + self.media.chunk)
        self.resumable_progress = s["received"]
        if s["received"] >= total:
            return None, srv.complete(self.resumable_uri)
        return _Progress(self.resumable_progress, total), None


class FakeMedia:
    def __init__(self, path, mimetype, chunk):
        import os
        self.path, self.mimetype, self.chunk = path, mimetype, chunk
        self.size = os.path.getsize(path)


def fake_media_factory(path, mimetype, chunk):
    return FakeMedia(path, mimetype, chunk)


class FakeYT:
    """YouTubeClient-like interface."""

    def __init__(self, server: FakeUploadServer, channel_id: str, quota=None):
        self.server, self.channel_id, self.quota = server, channel_id, quota
        self.thumbs: dict[str, object] = {}
        self.upload_status = "processed"
        self.thumb_error = None
        self.recent: list[dict] = []

    def _rec(self, op):
        if self.quota:
            self.quota.record(op)

    def insert_request(self, body, media):
        return FakeInsertRequest(self.server, body, media)

    def get_video(self, yt_id):
        self._rec("videos.list")
        if yt_id not in self.server.videos:
            return None
        return {"id": yt_id, "snippet": {"channelId": self.channel_id},
                "status": {"uploadStatus": self.upload_status},
                "processingDetails": {"processingStatus": "succeeded" if self.upload_status == "processed" else "processing"}}

    def set_thumbnail(self, yt_id, media):
        self._rec("thumbnails.set")
        if self.thumb_error:
            raise self.thumb_error
        self.thumbs[yt_id] = media
        return {"items": [{"default": {"url": "https://i.ytimg.com/x.jpg"}}]}

    def find_recent_upload(self, title, since=None):
        self._rec("playlistItems.list")
        for r in self.recent:
            if r["title"] == title:
                return r["id"]
        return None


class FakeMediaIo:
    def __init__(self, fh, mimetype=None, resumable=False):
        self.data, self.mimetype = fh.read(), mimetype
