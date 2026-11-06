"""Find new videos in Drive -> videos table (DISCOVERED).

Metadata priority: sidecar (.json/.txt with the same name) > Gemini (if GEMINI_API_KEY is set) > filename.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import PurePath

from sqlalchemy.engine import Engine

from src.clients.drive_client import DriveClient
from src.upload.duplicate_guard import file_version, find_existing, insert_if_new
from src.upload.metadata import VideoMetadata
from src.utils.logging import get_logger

log = get_logger("dharm_yt.discovery")


@dataclass
class DiscoveryResult:
    channel_id: str
    found: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def parse_sidecar(name: str, raw: bytes) -> dict:
    s = raw.decode("utf-8", "ignore").lstrip("\ufeff")
    if name.lower().endswith(".json"):
        data = json.loads(s)
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        out = {k: data[k] for k in ("title", "description", "category_id", "privacy") if data.get(k)}
        out["tags"] = tags
        return out
    # .txt: line 1 = title; "tags: a, b" line; the rest is the description
    lines = s.splitlines()
    title = lines[0].strip() if lines else ""
    tags, desc = [], []
    for ln in lines[1:]:
        if ln.lower().startswith("tags:"):
            tags = [t.strip() for t in ln.split(":", 1)[1].split(",") if t.strip()]
        else:
            desc.append(ln)
    return {"title": title, "description": "\n".join(desc).strip(), "tags": tags}


def title_from_filename(name: str) -> str:
    return PurePath(name).stem.replace("_", " ").replace("-", " ").strip() or name


def build_metadata(drive: DriveClient, f: dict, folders: list[str], channel: dict,
                   defaults: dict, gemini=None) -> VideoMetadata:
    meta: dict = {}
    side = drive.find_sidecar(folders, f["name"])
    if side:
        try:
            meta = parse_sidecar(side["name"], drive.read_bytes(side["id"]))
        except Exception as e:  # noqa: BLE001
            log.warning("Could not read sidecar (%s): %s", side["name"], e)
    if not meta.get("title"):
        gm = gemini
        if gm is None and os.getenv("GEMINI_API_KEY"):
            from src.ai.gemini import GeminiMetadata
            gm = GeminiMetadata()
        if gm is not None:
            try:
                g = gm.generate(f["name"], channel=channel.get("channel_name", ""),
                                language=defaults.get("language") or "English",
                                footer=defaults.get("description_footer", ""),
                                extra_tags=defaults.get("tags"))
                meta = {"title": g.title, "description": g.description, "tags": g.tags,
                        "category_id": g.category_id}
            except Exception as e:  # noqa: BLE001
                log.warning("Gemini failed, using the filename as title: %s", e)
    if not meta.get("title"):
        footer = defaults.get("description_footer", "")
        meta = {"title": title_from_filename(f["name"]), "description": footer,
                "tags": list(defaults.get("tags") or [])}
    vm = VideoMetadata(title=meta["title"], description=meta.get("description", ""),
                       tags=list(meta.get("tags") or []),
                       category_id=str(meta.get("category_id") or defaults.get("category_id", "22")),
                       privacy_status=meta.get("privacy") or defaults.get("privacy", "private"))
    return vm.clean()


def discover_channel(engine: Engine, channel: dict, drive: DriveClient,
                     defaults: dict | None = None, gemini=None) -> DiscoveryResult:
    defaults = defaults or {}
    cid, root = channel["channel_id"], channel["drive_folder_id"]
    res = DiscoveryResult(cid)
    files = drive.list_videos(root)
    res.found = len(files)
    folders = [root] + [x for x in [drive.subfolder(root, "videos")] if x]
    for f in files:
        try:
            ver, md5 = file_version(f), f.get("md5Checksum")
            with engine.connect() as c:
                existing, _ = find_existing(c, cid, f["id"], ver, md5)
            if existing:
                res.skipped += 1
                continue
            meta = build_metadata(drive, f, folders, channel, defaults, gemini)
            thumb = drive.find_thumbnail(root, f["name"])
            vid, why = insert_if_new(engine, {
                "channel_id": cid, "drive_file_id": f["id"], "drive_file_version": ver,
                "drive_md5": md5, "filename": f["name"], "file_size": int(f["size"]) if f.get("size") else None,
                "mime_type": f.get("mimeType"), "title": meta.title, "description": meta.description,
                "tags": meta.tags, "category_id": meta.category_id, "privacy_status": meta.privacy_status,
                "thumbnail_drive_id": thumb["id"] if thumb else None})
            if vid:
                res.inserted += 1
            else:
                res.skipped += 1
        except Exception as e:  # noqa: BLE001 - one bad file must not block the rest
            res.errors.append(f"{f.get('name')}: {e}")
    return res
