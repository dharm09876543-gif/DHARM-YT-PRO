"""Full journey of one video: lock -> download -> resumable upload -> thumbnail -> verify -> COMPLETED.

State is written to the DB after every step, so after a crash at any point the next run picks up from there.
"""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.auth.token_manager import AuthRevoked
from src.clients.errors import is_channel_limit, is_quota_exceeded
from src.services.quota import QuotaExceeded, QuotaLedger
from src.upload.metadata import VideoMetadata
from src.upload.resumable import ResumableUploader, SessionLost
from src.upload.state import acquire_lock, log_event, release_lock, transition, update_fields
from src.upload.thumbnail import apply_thumbnail
from src.upload.verifier import verify_upload
from src.utils.logging import get_logger
from src.utils.timeutil import parse_dt, utcnow

log = get_logger("dharm_yt.pipeline")
PRE_UPLOAD = {"QUEUED", "RETRY_WAIT", "DOWNLOADING", "READY", "UPLOADING"}


class ChannelLimit(RuntimeError):
    """This channel's daily upload limit (YouTube) - other channels keep running."""


@dataclass
class UploadContext:
    engine: Engine
    cipher: object
    yt: object                    # YouTubeClient
    drive: object                 # DriveClient
    quota: QuotaLedger
    settings: dict = field(default_factory=dict)
    worker: str = field(default_factory=lambda: f"{socket.gethostname()}")
    tmp_dir: Path = Path("data/tmp")
    media_factory: object = None
    thumb_media_cls: object = None
    sleep: object = None

    def uploader(self) -> ResumableUploader:
        up = self.settings.get("uploads", {})
        kw = {}
        if self.media_factory:
            kw["media_factory"] = self.media_factory
        if self.sleep:
            kw["sleep"] = self.sleep
        return ResumableUploader(self.engine, self.cipher, self.yt, self.quota,
                                 chunk_size=int(up.get("chunk_size_mb", 8)) * 1024 * 1024,
                                 max_retries=int(up.get("max_retries", 5)), **kw)


def load_video(engine: Engine, video_id: int) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT * FROM videos WHERE id=:v"), {"v": video_id}).first()._mapping)


def youtube_body(v: dict) -> dict:
    tags = v.get("tags")
    if isinstance(tags, str):
        tags = json.loads(tags or "[]")
    meta = VideoMetadata(title=v.get("title") or v["filename"], description=v.get("description") or "",
                         tags=tags or [], category_id=v.get("category_id") or "22",
                         privacy_status=v.get("privacy_status") or "private",
                         publish_at=parse_dt(v.get("scheduled_publish_at"))).clean()
    errs = meta.errors()
    if errs:
        raise ValueError("Invalid metadata: " + "; ".join(errs))
    return meta.to_youtube_body()


def _download(ctx: UploadContext, v: dict) -> Path:
    path = Path(ctx.tmp_dir) / f"{v['id']}_{v['drive_file_id']}"
    if path.exists() and v.get("file_size") and path.stat().st_size == int(v["file_size"]):
        return path
    return ctx.drive.download_to(v["drive_file_id"], path, expected_md5=v.get("drive_md5"))


def _upload_stage(ctx: UploadContext, v: dict) -> str:
    ctx.quota.check_upload(with_thumbnail=bool(v.get("thumbnail_drive_id")))
    body = youtube_body(v)
    transition(ctx.engine, v["id"], "DOWNLOADING")
    path = _download(ctx, v)
    try:
        transition(ctx.engine, v["id"], "READY")
        transition(ctx.engine, v["id"], "UPLOADING")
        up = ctx.uploader()
        try:
            resp = up.upload(v["id"], path, body, v.get("mime_type"))
        except SessionLost as sl:
            # No blind re-insert: first check whether the video is already on the channel.
            found = ctx.yt.find_recent_upload(body["snippet"]["title"], since=parse_dt(sl.created_at))
            log_event(ctx.engine, v["id"], "reconcile", "found" if found else "not_found",
                      "session expired; checked channel uploads", found)
            resp = {"id": found} if found else up.upload(v["id"], path, body, v.get("mime_type"))
    finally:
        path.unlink(missing_ok=True)
    yt_id = resp["id"]
    transition(ctx.engine, v["id"], "PROCESSING", "upload complete", event="uploaded", youtube_video_id=yt_id)
    return yt_id


def _finish_stage(ctx: UploadContext, v: dict) -> str:
    v = load_video(ctx.engine, v["id"])
    yt_id = v["youtube_video_id"]
    if v["upload_status"] in ("PROCESSING", "RETRY_WAIT"):
        if v.get("thumbnail_drive_id") and v.get("thumbnail_status") != "set":
            apply_thumbnail(ctx.engine, v["id"], yt_id, ctx.drive, ctx.yt, v["thumbnail_drive_id"],
                            media_cls=ctx.thumb_media_cls)
        transition(ctx.engine, v["id"], "VERIFYING")
    r = verify_upload(ctx.yt, yt_id, v["channel_id"])
    if r.ok:
        transition(ctx.engine, v["id"], "COMPLETED", r.reason, event="verified", youtube_video_id=yt_id,
                   verified_channel_id=r.channel_id, processing_status=r.processing_status or r.upload_status,
                   last_error=None)
        with ctx.engine.begin() as c:
            c.execute(text("UPDATE schedules SET status='uploaded' WHERE video_id=:v"), {"v": v["id"]})
        return "COMPLETED"
    if r.final:
        transition(ctx.engine, v["id"], "FAILED", r.reason, event="verified", last_error=r.reason,
                   processing_status=r.processing_status)
        return "FAILED"
    update_fields(ctx.engine, v["id"], processing_status=r.processing_status or r.upload_status)
    log_event(ctx.engine, v["id"], "verify", "pending", r.reason, yt_id)
    return "VERIFYING"


def process_video(ctx: UploadContext, video_id: int) -> str:
    """Returns the final/current status. QuotaExceeded, AuthRevoked, ChannelLimit propagate up."""
    if not acquire_lock(ctx.engine, video_id, ctx.worker,
                        int(ctx.settings.get("uploads", {}).get("stale_lock_minutes", 90))):
        return "LOCKED"
    v = load_video(ctx.engine, video_id)
    try:
        if v["upload_status"] in PRE_UPLOAD and not v.get("youtube_video_id"):
            _upload_stage(ctx, v)
        if load_video(ctx.engine, video_id)["upload_status"] in ("PROCESSING", "VERIFYING", "RETRY_WAIT") \
                and load_video(ctx.engine, video_id).get("youtube_video_id"):
            return _finish_stage(ctx, v)
        return load_video(ctx.engine, video_id)["upload_status"]
    except QuotaExceeded:
        _back_to_queue(ctx, video_id, "quota used up - back in queue")
        raise
    except AuthRevoked:
        _back_to_queue(ctx, video_id, "auth revoked - after reconnect")
        raise
    except Exception as e:  # noqa: BLE001
        if is_quota_exceeded(e):
            ctx.quota.mark_exceeded()
            _back_to_queue(ctx, video_id, "Google quotaExceeded - retry tomorrow")
            raise QuotaExceeded("Google returned quotaExceeded") from e
        if is_channel_limit(e):
            _back_to_queue(ctx, video_id, "channel upload limit - retry tomorrow")
            raise ChannelLimit(str(e)) from e
        return _fail_or_retry(ctx, video_id, e)
    finally:
        release_lock(ctx.engine, video_id, ctx.worker)


def _back_to_queue(ctx: UploadContext, video_id: int, msg: str) -> None:
    v = load_video(ctx.engine, video_id)
    target = "RETRY_WAIT" if v.get("youtube_video_id") else "QUEUED"
    if v["upload_status"] != target:
        try:
            transition(ctx.engine, video_id, target, msg, event="paused", next_retry_at=utcnow())
        except Exception:  # noqa: BLE001
            log_event(ctx.engine, video_id, "paused", v["upload_status"], msg)


def _fail_or_retry(ctx: UploadContext, video_id: int, e: Exception) -> str:
    v = load_video(ctx.engine, video_id)
    up = ctx.settings.get("uploads", {})
    attempts = int(v.get("attempts") or 0) + 1
    msg = f"{type(e).__name__}: {e}"[:500]
    log.warning("Video %s fail (attempt %s): %s", video_id, attempts, msg)
    if attempts >= int(up.get("max_retries", 5)):
        transition(ctx.engine, video_id, "FAILED", msg, event="error", attempts=attempts, last_error=msg)
        return "FAILED"
    wait = int(up.get("retry_wait_minutes", 30)) * attempts
    transition(ctx.engine, video_id, "RETRY_WAIT", msg, event="error", attempts=attempts, last_error=msg,
               next_retry_at=utcnow() + timedelta(minutes=wait))
    return "RETRY_WAIT"
