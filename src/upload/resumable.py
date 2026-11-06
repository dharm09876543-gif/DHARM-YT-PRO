"""Resumable upload jo crash/restart ke baad wahi se continue karta hai.

- Session URI (encrypted) aur bytes_uploaded har chunk ke baad upload_sessions mein.
- Restart par: active session ho to naya insert NAHI; pehle server se status poochte hain
  (googleapiclient ka error-state query: PUT 'bytes */size'), phir bacha hua bhejte hain.
  Agar upload pehle hi poora ho chuka tha to server video resource lauta deta hai.
- 5xx / timeout: src/utils/retry.py exponential backoff.
- Session gone (404/410): SessionLost - caller reconcile karta hai (channel uploads mein dhoondh kar),
  andha re-insert kabhi nahi.
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.clients.errors import is_retryable, is_session_gone
from src.utils.retry import retry
from src.utils.timeutil import utcnow

MIN_CHUNK = 256 * 1024


class SessionLost(RuntimeError):
    def __init__(self, session_id: int, bytes_uploaded: int, created_at):
        super().__init__("Upload session expire/kho gaya")
        self.session_id, self.bytes_uploaded, self.created_at = session_id, bytes_uploaded, created_at


def _default_media(path: str, mimetype: str | None, chunksize: int):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(path, mimetype=mimetype or "video/*", chunksize=chunksize, resumable=True)


class ResumableUploader:
    def __init__(self, engine: Engine, cipher, yt, quota=None, chunk_size: int = 8 * 1024 * 1024,
                 media_factory=_default_media, max_retries: int = 5, sleep=time.sleep,
                 on_progress=None):
        if chunk_size % MIN_CHUNK:
            raise ValueError("chunk_size 256KB ka multiple hona chahiye")
        self.db, self.cipher, self.yt, self.quota = engine, cipher, yt, quota
        self.chunk = chunk_size
        self.media_factory = media_factory
        self.max_retries, self.sleep = max_retries, sleep
        self.on_progress = on_progress

    # ---- session rows ----
    def active_session(self, video_id: int):
        with self.db.connect() as c:
            return c.execute(text("""SELECT id, encrypted_session_uri, bytes_uploaded, total_bytes, created_at
                                     FROM upload_sessions WHERE video_id=:v AND session_status='active'"""),
                             {"v": video_id}).first()

    def _new_session(self, video_id: int, total: int) -> int:
        with self.db.begin() as c:
            c.execute(text("""INSERT INTO upload_sessions(video_id, total_bytes, bytes_uploaded, session_status,
                              created_at, updated_at) VALUES (:v,:t,0,'active',:now,:now)"""),
                      {"v": video_id, "t": total, "now": utcnow()})
            return c.execute(text("""SELECT id FROM upload_sessions WHERE video_id=:v
                                     AND session_status='active'"""), {"v": video_id}).scalar()

    def _checkpoint(self, sid: int, uri: str | None, progress: int) -> None:
        with self.db.begin() as c:
            c.execute(text("""UPDATE upload_sessions SET encrypted_session_uri=COALESCE(:u, encrypted_session_uri),
                              bytes_uploaded=:b, last_checkpoint_at=:now, updated_at=:now WHERE id=:id"""),
                      {"u": self.cipher.encrypt(uri) if uri else None, "b": progress,
                       "now": utcnow(), "id": sid})

    def close_session(self, sid: int, status: str) -> None:
        with self.db.begin() as c:
            c.execute(text("UPDATE upload_sessions SET session_status=:s, updated_at=:now WHERE id=:id"),
                      {"s": status, "now": utcnow(), "id": sid})

    # ---- upload ----
    def upload(self, video_id: int, path: Path, body: dict, mimetype: str | None = None) -> dict:
        """Video resource (dict, 'id' ke saath) lautata hai."""
        path = Path(path)
        total = path.stat().st_size
        media = self.media_factory(str(path), mimetype, self.chunk)
        request = self.yt.insert_request(body, media)
        sess = self.active_session(video_id)
        if sess and sess.encrypted_session_uri:
            # Purana session: naya insert nahi. Pehle server se poochho kitna pahuncha.
            request.resumable_uri = self.cipher.decrypt(sess.encrypted_session_uri)
            request.resumable_progress = int(sess.bytes_uploaded or 0)
            request._in_error_state = True
            sid = sess.id
            started = sess.created_at
        else:
            # Session row hai par URI kabhi save nahi hua -> koi byte server tak nahi gaya, safe.
            started = utcnow()
            sid = sess.id if sess else self._new_session(video_id, total)
            if self.quota:
                self.quota.record("videos.insert")

        def one_chunk():
            try:
                return request.next_chunk()
            except Exception:
                if request.resumable_uri:
                    request._in_error_state = True   # agli koshish pehle status poochhegi
                raise
            finally:
                self._checkpoint(sid, request.resumable_uri, int(request.resumable_progress or 0))

        response = None
        while response is None:
            try:
                status, response = retry(one_chunk, is_retryable, max_retries=self.max_retries,
                                         sleep=self.sleep)
            except Exception as e:
                if is_session_gone(e):
                    self.close_session(sid, "expired")
                    raise SessionLost(sid, int(request.resumable_progress or 0), started) from e
                raise   # session 'active' rehta hai -> agla run status query se resume karega
            if status is not None and self.on_progress:
                self.on_progress(status.resumable_progress, total)
        self._checkpoint(sid, request.resumable_uri, total)
        self.close_session(sid, "completed")
        return response
