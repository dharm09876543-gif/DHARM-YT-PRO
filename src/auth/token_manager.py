"""Per-channel credentials: encrypted refresh token -> google Credentials -> refresh.

On invalid_grant (user removed access / token expired) the channel is marked 'revoked'.
"""
from __future__ import annotations

import os
from datetime import timezone

from src.auth.oauth import SCOPES, TOKEN_URI
from src.services.channel_service import ChannelError, ChannelService


class AuthRevoked(RuntimeError):
    """The channel must be connected again."""


class TokenManager:
    def __init__(self, svc: ChannelService, client_id: str | None = None,
                 client_secret: str | None = None, credentials_cls=None, request_factory=None):
        self.svc = svc
        self.client_id = client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
        if credentials_cls is None:
            from google.oauth2.credentials import Credentials as credentials_cls
        if request_factory is None:
            from google.auth.transport.requests import Request as request_factory
        self._cred_cls = credentials_cls
        self._request = request_factory

    def credentials(self, channel_id: str):
        if not self.client_id or not self.client_secret:
            raise AuthRevoked("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set")
        try:
            rt = self.svc.refresh_token(channel_id)
        except ChannelError as e:
            raise AuthRevoked(str(e)) from e
        creds = self._cred_cls(token=None, refresh_token=rt, token_uri=TOKEN_URI,
                               client_id=self.client_id, client_secret=self.client_secret,
                               scopes=SCOPES)
        try:
            creds.refresh(self._request())
        except Exception as e:  # noqa: BLE001 - google.auth.exceptions.RefreshError
            msg = str(e)
            if "invalid_grant" in msg or "unauthorized_client" in msg:
                self.svc.mark_auth(channel_id, "revoked")
                raise AuthRevoked(f"Channel {channel_id} access was revoked/expired - "
                                  "reconnect with 'python main.py connect'") from e
            raise
        expiry = getattr(creds, "expiry", None)
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        self.svc.update_access_token(channel_id, getattr(creds, "token", None), expiry)
        return creds

    def services(self, channel_id: str, build=None) -> dict:
        """youtube, drive, youtubeAnalytics service objects from the same credentials."""
        if build is None:
            from googleapiclient.discovery import build
        creds = self.credentials(channel_id)
        kw = {"credentials": creds, "cache_discovery": False}
        return {"youtube": build("youtube", "v3", **kw), "drive": build("drive", "v3", **kw),
                "analytics": build("youtubeAnalytics", "v2", **kw)}
