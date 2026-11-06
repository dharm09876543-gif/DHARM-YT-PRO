"""Channel Manager: add, list, enable/disable, folder, defaults, remove, health."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.auth.encryption import TokenCipher


class ChannelError(ValueError):
    pass


class ChannelService:
    def __init__(self, engine: Engine, cipher: TokenCipher | None = None):
        self.db = engine
        self.cipher = cipher

    # ---- channels ----
    def add(self, channel_id: str, name: str, drive_folder_id: str,
            timezone_name: str = "Asia/Kolkata", thumbnail_url: str | None = None) -> None:
        if not channel_id.startswith("UC") or len(channel_id) != 24:
            raise ChannelError("channel_id galat hai")
        if not drive_folder_id:
            raise ChannelError("drive_folder_id zaroori hai")
        with self.db.begin() as c:
            if c.execute(text("SELECT 1 FROM channels WHERE channel_id=:c"), {"c": channel_id}).first():
                raise ChannelError("ye channel pehle se jud chuka hai")
            c.execute(text("""INSERT INTO channels(channel_id, channel_name, drive_folder_id, timezone, thumbnail_url)
                              VALUES (:c,:n,:f,:t,:th)"""),
                      {"c": channel_id, "n": name, "f": drive_folder_id, "t": timezone_name, "th": thumbnail_url})

    def list(self, enabled_only: bool = False) -> list[dict]:
        q = """SELECT c.channel_id, c.channel_name, c.drive_folder_id, c.timezone, c.enabled,
                      c.thumbnail_url, COALESCE(o.status,'not_connected') AS auth_status,
                      (SELECT COUNT(*) FROM videos v WHERE v.channel_id=c.channel_id AND v.upload_status='COMPLETED') AS uploaded,
                      (SELECT COUNT(*) FROM videos v WHERE v.channel_id=c.channel_id AND v.upload_status IN ('DISCOVERED','QUEUED','READY','RETRY_WAIT')) AS queued,
                      (SELECT COUNT(*) FROM videos v WHERE v.channel_id=c.channel_id AND v.upload_status='FAILED') AS failed
               FROM channels c LEFT JOIN oauth_credentials o ON o.channel_id=c.channel_id"""
        if enabled_only:
            q += " WHERE c.enabled = TRUE"
        q += " ORDER BY c.channel_name"
        with self.db.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(q))]

    def get(self, channel_id: str) -> dict:
        for ch in self.list():
            if ch["channel_id"] == channel_id:
                return ch
        raise ChannelError("channel nahi mila")

    def _update(self, channel_id: str, **fields) -> None:
        sets = ", ".join(f"{k}=:{k}" for k in fields)
        with self.db.begin() as c:
            n = c.execute(text(f"UPDATE channels SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE channel_id=:cid"),
                          {**fields, "cid": channel_id}).rowcount
        if not n:
            raise ChannelError("channel nahi mila")

    def enable(self, channel_id: str) -> None:
        self._update(channel_id, enabled=True)

    def disable(self, channel_id: str) -> None:
        self._update(channel_id, enabled=False)

    def rename(self, channel_id: str, name: str) -> None:
        self._update(channel_id, channel_name=name)

    def set_folder(self, channel_id: str, drive_folder_id: str) -> None:
        if not drive_folder_id:
            raise ChannelError("drive_folder_id zaroori hai")
        self._update(channel_id, drive_folder_id=drive_folder_id)

    def set_timezone(self, channel_id: str, tz: str) -> None:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
        self._update(channel_id, timezone=tz)

    # ---- OAuth tokens (encrypted) ----
    def save_tokens(self, channel_id: str, refresh_token: str, access_token: str | None = None,
                    expiry: datetime | None = None, scopes: list[str] | None = None) -> None:
        if not self.cipher:
            raise ChannelError("encryption key chahiye")
        self.get(channel_id)
        params = {"c": channel_id, "rt": self.cipher.encrypt(refresh_token),
                  "at": self.cipher.encrypt(access_token) if access_token else None,
                  "e": expiry, "s": json.dumps(scopes or [])}
        with self.db.begin() as c:
            c.execute(text("DELETE FROM oauth_credentials WHERE channel_id=:c"), {"c": channel_id})
            c.execute(text("""INSERT INTO oauth_credentials(channel_id, encrypted_refresh_token,
                              encrypted_access_token, token_expiry, scopes, status)
                              VALUES (:c,:rt,:at,:e,:s,'active')"""), params)

    def update_access_token(self, channel_id: str, access_token: str | None,
                            expiry: datetime | None = None) -> None:
        """Refresh ke baad naya access token (encrypted) save; refresh token waisa hi rehta hai."""
        if not self.cipher:
            raise ChannelError("encryption key chahiye")
        with self.db.begin() as c:
            c.execute(text("""UPDATE oauth_credentials SET encrypted_access_token=:at, token_expiry=:e,
                              updated_at=CURRENT_TIMESTAMP WHERE channel_id=:c"""),
                      {"at": self.cipher.encrypt(access_token) if access_token else None,
                       "e": expiry, "c": channel_id})

    def update_profile(self, channel_id: str, name: str | None = None,
                       thumbnail_url: str | None = None) -> None:
        fields = {k: v for k, v in {"channel_name": name, "thumbnail_url": thumbnail_url}.items() if v}
        if fields:
            self._update(channel_id, **fields)

    def exists(self, channel_id: str) -> bool:
        with self.db.connect() as c:
            return c.execute(text("SELECT 1 FROM channels WHERE channel_id=:c"), {"c": channel_id}).first() is not None

    def refresh_token(self, channel_id: str) -> str:
        with self.db.connect() as c:
            r = c.execute(text("SELECT encrypted_refresh_token, status FROM oauth_credentials WHERE channel_id=:c"),
                          {"c": channel_id}).first()
        if not r:
            raise ChannelError("channel connect nahi hai - OAuth karein")
        if r.status != "active":
            raise ChannelError(f"authorization '{r.status}' hai - dobara connect karein")
        return self.cipher.decrypt(r.encrypted_refresh_token)

    def mark_auth(self, channel_id: str, status: str) -> None:
        if status not in {"active", "expired", "revoked"}:
            raise ChannelError("status galat")
        with self.db.begin() as c:
            c.execute(text("UPDATE oauth_credentials SET status=:s, updated_at=CURRENT_TIMESTAMP WHERE channel_id=:c"),
                      {"s": status, "c": channel_id})

    def remove(self, channel_id: str, confirm: bool = False) -> None:
        """Authorization hata deta hai aur channel disable karta hai; upload history safe rehti hai."""
        if not confirm:
            raise ChannelError("remove ke liye confirm=True dein")
        with self.db.begin() as c:
            c.execute(text("DELETE FROM oauth_credentials WHERE channel_id=:c"), {"c": channel_id})
        self.disable(channel_id)

    def health(self) -> list[dict]:
        out = []
        for ch in self.list():
            issues = []
            if ch["auth_status"] != "active":
                issues.append("OAuth connect/reconnect karein")
            if not ch["enabled"]:
                issues.append("disabled")
            if ch["failed"]:
                issues.append(f"{ch['failed']} upload fail")
            out.append({"channel_id": ch["channel_id"], "name": ch["channel_name"],
                        "ok": not issues, "issues": issues,
                        "checked_at": datetime.now(timezone.utc).isoformat()})
        return out
