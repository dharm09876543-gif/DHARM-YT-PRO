"""Google OAuth 2.0 (per channel): installed (local browser) and web flow.

The channel owner gives consent themselves. After consent, channels.list(mine=true) returns
the real channel id/name/thumbnail, the channel is verified/registered in the DB, and
tokens are saved encrypted via ChannelService.save_tokens.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.services.channel_service import ChannelError, ChannelService

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/drive",
]
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthError(RuntimeError):
    pass


def client_config(kind: str = "installed", redirect_uri: str | None = None) -> dict:
    cid, secret = os.getenv("GOOGLE_CLIENT_ID", ""), os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not cid or not secret:
        raise OAuthError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set (.env or GitHub Secrets)")
    redirect = redirect_uri or os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/")
    return {kind: {"client_id": cid, "client_secret": secret, "auth_uri": AUTH_URI,
                   "token_uri": TOKEN_URI, "redirect_uris": [redirect, "http://localhost"]}}


def run_installed_flow(port: int = 8080, open_browser: bool = True, flow_cls=None):
    """Opens a browser on the local PC to get consent; returns Credentials."""
    if flow_cls is None:
        from google_auth_oauthlib.flow import InstalledAppFlow as flow_cls
    flow = flow_cls.from_client_config(client_config("installed"), SCOPES)
    return flow.run_local_server(port=port, open_browser=open_browser, prompt="consent",
                                 access_type="offline", include_granted_scopes="true",
                                 authorization_prompt_message="Choose your Google account in the browser: {url}",
                                 success_message="Done! You can close this tab.")


def build_web_flow(redirect_uri: str, state: str | None = None, flow_cls=None):
    """Web (backend) flow: (flow, authorization_url, state). Used by the dashboard in Phase 10."""
    if flow_cls is None:
        from google_auth_oauthlib.flow import Flow as flow_cls
    flow = flow_cls.from_client_config(client_config("web", redirect_uri), SCOPES, state=state)
    flow.redirect_uri = redirect_uri
    url, st = flow.authorization_url(access_type="offline", prompt="consent",
                                     include_granted_scopes="true")
    return flow, url, st


def finish_web_flow(flow, authorization_response: str):
    flow.fetch_token(authorization_response=authorization_response)
    return flow.credentials


@dataclass
class ConnectResult:
    channel_id: str
    channel_name: str
    thumbnail_url: str | None
    registered: bool        # was a new channel created in the DB?


def fetch_own_channel(youtube) -> dict:
    """channels.list(mine=true): real details of the channel that gave consent."""
    resp = youtube.channels().list(part="snippet", mine=True, maxResults=5).execute()
    items = resp.get("items") or []
    if not items:
        raise OAuthError("No YouTube channel found in this Google account")
    it = items[0]
    sn = it.get("snippet", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    return {"channel_id": it["id"], "channel_name": sn.get("title", it["id"]), "thumbnail_url": thumb}


def connect_channel(svc: ChannelService, creds, youtube, expected_channel_id: str | None = None,
                    drive_folder_id: str | None = None, timezone_name: str = "Asia/Kolkata",
                    quota=None) -> ConnectResult:
    """After consent: verify/register the real channel + save encrypted tokens."""
    if not getattr(creds, "refresh_token", None):
        raise OAuthError("Refresh token not received - connect again (prompt=consent is required)")
    info = fetch_own_channel(youtube)
    if quota:
        quota.record("channels.list")
    cid = info["channel_id"]
    if expected_channel_id and expected_channel_id != cid:
        raise OAuthError(f"Wrong channel selected: expected {expected_channel_id}, got {cid} ({info['channel_name']})")
    registered = False
    if svc.exists(cid):
        svc.update_profile(cid, info["channel_name"], info["thumbnail_url"])
        if drive_folder_id:
            svc.set_folder(cid, drive_folder_id)
    else:
        if not drive_folder_id:
            raise OAuthError(f"Channel {cid} is not in the DB - pass --folder DRIVE_FOLDER_ID")
        try:
            svc.add(cid, info["channel_name"], drive_folder_id, timezone_name, info["thumbnail_url"])
        except ChannelError as e:
            raise OAuthError(str(e)) from e
        registered = True
    expiry = getattr(creds, "expiry", None)
    if expiry is not None and expiry.tzinfo is None:
        from datetime import timezone
        expiry = expiry.replace(tzinfo=timezone.utc)
    svc.save_tokens(cid, creds.refresh_token, getattr(creds, "token", None), expiry,
                    list(getattr(creds, "scopes", None) or SCOPES))
    return ConnectResult(cid, info["channel_name"], info["thumbnail_url"], registered)
