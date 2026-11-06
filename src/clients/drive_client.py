"""Google Drive v3 wrapper: list videos, subfolders, thumbnails, sidecars, download, trash.

files.delete is never called - trash only (files.update trashed=true).
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePath

FILE_FIELDS = "id,name,size,mimeType,createdTime,version,md5Checksum,trashed,parents"
FOLDER_MIME = "application/vnd.google-apps.folder"
IMAGE_MIMES = {"image/jpeg", "image/png"}


def basename(name: str) -> str:
    return PurePath(name).stem.lower()


class DriveClient:
    def __init__(self, service):
        self.svc = service

    def _list(self, q: str) -> list[dict]:
        out, token = [], None
        while True:
            resp = self.svc.files().list(q=q, fields=f"nextPageToken, files({FILE_FIELDS})",
                                         pageSize=200, pageToken=token,
                                         supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            out.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                return out

    def children(self, folder_id: str) -> list[dict]:
        return self._list(f"'{folder_id}' in parents and trashed = false")

    def subfolder(self, folder_id: str, name: str) -> str | None:
        for f in self.children(folder_id):
            if f.get("mimeType") == FOLDER_MIME and f.get("name", "").lower() == name.lower():
                return f["id"]
        return None

    def list_videos(self, folder_id: str) -> list[dict]:
        """Folder + its 'videos' subfolder; video/* files only, oldest first."""
        folders = [folder_id]
        sub = self.subfolder(folder_id, "videos")
        if sub:
            folders.append(sub)
        seen, vids = set(), []
        for fid in folders:
            for f in self.children(fid):
                if "video/" in (f.get("mimeType") or "") and f["id"] not in seen:
                    seen.add(f["id"]); vids.append(f)
        return sorted(vids, key=lambda f: f.get("createdTime", ""))

    def find_thumbnail(self, folder_id: str, video_name: str) -> dict | None:
        sub = self.subfolder(folder_id, "thumbnails")
        if not sub:
            return None
        want = basename(video_name)
        for f in self.children(sub):
            if f.get("mimeType") in IMAGE_MIMES and basename(f["name"]) == want:
                return f
        return None

    def find_sidecar(self, folder_ids: list[str], video_name: str) -> dict | None:
        """A .json or .txt next to the video with the same name (title/description/tags)."""
        want = basename(video_name)
        for fid in folder_ids:
            for f in self.children(fid):
                n = f.get("name", "")
                if basename(n) == want and n.lower().endswith((".json", ".txt")):
                    return f
        return None

    def get(self, file_id: str) -> dict:
        return self.svc.files().get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True).execute()

    def read_bytes(self, file_id: str) -> bytes:
        data = self.svc.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
        return data if isinstance(data, bytes) else str(data).encode()

    def download_to(self, file_id: str, path: Path, expected_md5: str | None = None,
                    chunk_size: int = 32 * 1024 * 1024, downloader_cls=None) -> Path:
        if downloader_cls is None:
            from googleapiclient.http import MediaIoBaseDownload as downloader_cls
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        req = self.svc.files().get_media(fileId=file_id, supportsAllDrives=True)
        with open(path, "wb") as fh:
            dl = downloader_cls(fh, req, chunksize=chunk_size)
            done = False
            while not done:
                _, done = dl.next_chunk(num_retries=3)
        if expected_md5:
            h = hashlib.md5()
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(block)
            if h.hexdigest() != expected_md5:
                path.unlink(missing_ok=True)
                raise IOError("Download corrupted: md5 mismatch")
        return path

    def trash(self, file_id: str) -> dict:
        return self.svc.files().update(fileId=file_id, body={"trashed": True},
                                       fields="id,trashed", supportsAllDrives=True).execute()


def read_stream(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)
