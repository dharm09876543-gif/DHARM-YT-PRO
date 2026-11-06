"""Duplicate guard: the same video is never uploaded twice to a channel.

1. DB constraint UNIQUE(channel_id, drive_file_id, drive_file_version) - the last line of defence.
2. Pre-check: same drive file+version, or same md5 content (re-uploaded under a different file id) already present?
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


def file_version(f: dict) -> str:
    """Content-based version: md5 is the most reliable (does not change on rename)."""
    return str(f.get("md5Checksum") or f.get("version") or "1")


def find_existing(conn, channel_id: str, drive_file_id: str, version: str, md5: str | None):
    r = conn.execute(text("""SELECT id, upload_status FROM videos WHERE channel_id=:c
                             AND drive_file_id=:d AND drive_file_version=:v"""),
                     {"c": channel_id, "d": drive_file_id, "v": version}).first()
    if r:
        return r.id, "same_file"
    if md5:
        r = conn.execute(text("""SELECT id, upload_status FROM videos WHERE channel_id=:c AND drive_md5=:m
                                 AND upload_status <> 'CANCELLED'"""), {"c": channel_id, "m": md5}).first()
        if r:
            return r.id, "same_content"
    return None, None


def insert_if_new(engine: Engine, row: dict) -> tuple[int | None, str]:
    """(new_video_id, 'inserted') or (None, 'same_file'|'same_content'|'race')."""
    with engine.begin() as c:
        vid, why = find_existing(c, row["channel_id"], row["drive_file_id"],
                                 row["drive_file_version"], row.get("drive_md5"))
        if vid:
            return None, why
    params = {**row, "tags": json.dumps(row.get("tags") or [], ensure_ascii=False)}
    try:
        with engine.begin() as c:
            c.execute(text("""INSERT INTO videos(channel_id, drive_file_id, drive_file_version, drive_md5,
                                filename, file_size, mime_type, title, description, tags, category_id,
                                privacy_status, thumbnail_drive_id, upload_status)
                              VALUES (:channel_id,:drive_file_id,:drive_file_version,:drive_md5,:filename,
                                :file_size,:mime_type,:title,:description,:tags,:category_id,
                                :privacy_status,:thumbnail_drive_id,'DISCOVERED')"""), params)
            new_id = c.execute(text("""SELECT id FROM videos WHERE channel_id=:c AND drive_file_id=:d
                                       AND drive_file_version=:v"""),
                               {"c": row["channel_id"], "d": row["drive_file_id"],
                                "v": row["drive_file_version"]}).scalar()
            c.execute(text("""INSERT INTO upload_history(video_id, event_type, event_status, message)
                              VALUES (:v,'discovered','ok',:m)"""), {"v": new_id, "m": row["filename"]})
        return new_id, "inserted"
    except IntegrityError:
        return None, "race"   # another worker inserted it first - blocked by the constraint
