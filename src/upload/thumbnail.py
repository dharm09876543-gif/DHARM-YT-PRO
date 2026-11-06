"""Drive thumbnail -> YouTube thumbnails.set. Limit: JPG/PNG, max 2MB.
Custom thumbnails require a phone-verified channel."""
from __future__ import annotations

import io

from src.upload.state import log_event, update_fields

MAX_BYTES = 2 * 1024 * 1024


def apply_thumbnail(engine, video_id: int, yt_video_id: str, drive, yt, thumb_drive_id: str,
                    media_cls=None) -> bool:
    if media_cls is None:
        from googleapiclient.http import MediaIoBaseUpload as media_cls
    try:
        meta = drive.get(thumb_drive_id)
        mime = meta.get("mimeType", "image/jpeg")
        if mime not in ("image/jpeg", "image/png"):
            raise ValueError(f"thumbnail format {mime} not allowed (JPG/PNG)")
        if int(meta.get("size") or 0) > MAX_BYTES:
            raise ValueError("thumbnail is larger than 2MB")
        data = drive.read_bytes(thumb_drive_id)
        if len(data) > MAX_BYTES:
            raise ValueError("thumbnail is larger than 2MB")
        resp = yt.set_thumbnail(yt_video_id, media_cls(io.BytesIO(data), mimetype=mime, resumable=False))
        if not (resp or {}).get("items"):
            raise ValueError("empty thumbnails.set response")
        update_fields(engine, video_id, thumbnail_status="set")
        log_event(engine, video_id, "thumbnail", "ok", youtube_video_id=yt_video_id)
        return True
    except Exception as e:  # noqa: BLE001 - a failed thumbnail does not fail the video
        update_fields(engine, video_id, thumbnail_status="failed", last_error=f"thumbnail: {e}"[:500])
        log_event(engine, video_id, "thumbnail", "failed", str(e), yt_video_id)
        return False
