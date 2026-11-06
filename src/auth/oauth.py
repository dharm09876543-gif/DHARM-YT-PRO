"""Google OAuth 2.0 (per channel): installed (local browser) aur web flow.

Channel ka malik khud consent deta hai. Consent ke baad channels.list(mine=true) se
asli channel id/naam/thumbnail lekar DB mein channel verify/register hota hai aur
tokens ChannelService.save_tokens se encrypted save hote hain.
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
        raise OAuthError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET set nahi hain (.env ya GitHub Secrets)")
    redirect = redirect_uri or os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/")
    return {kind: {"client_id": cid, "client_secret": secret, "auth_uri": AUTH_URI,
                   "token_uri": TOKEN_URI, "redirect_uris": [redirect, "http://localhost"]}}


def run_installed_flow(port: int = 8080, open_browser: bool = True, flow_cls=None):
    """Local PC par browser kholkar consent leta hai; Credentials lautata hai."""
    if flow_cls is None:
        from google_auth_oauthlib.flow import InstalledAppFlow as flow_cls
    flow = flow_cls.from_client_config(client_config("installed"), SCOPES)
    return flow.run_local_server(port=port, open_browser=open_browser, prompt="consent",
                                 access_type="offline", include_granted_scopes="true",
                                 authorization_prompt_message="Browser mein Google account chunein: {url}",
                                 success_message="Ho gaya! Ye tab band kar sakte hain.")


def build_web_flow(redirect_uri: str, state: str | None = None, flow_cls=None):
    """Web (backend) flow: (flow, authorization_url, state). Dashboard Phase 10 mein use hoga."""
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
    registered: bool        # naya channel DB mein bana?


def fetch_own_channel(youtube) -> dict:
    """channels.list(mine=true): jis channel ko consent mila uski asli details."""
    resp = youtube.channels().list(part="snippet", mine=True, maxResults=5).execute()
    items = resp.get("items") or []
    if not items:
        raise OAuthError("Is Google account mein koi YouTube channel nahi mila")
    it = items[0]
    sn = it.get("snippet", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    return {"channel_id": it["id"], "channel_name": sn.get("title", it["id"]), "thumbnail_url": thumb}


def connect_channel(svc: ChannelService, creds, youtube, expected_channel_id: str | None = None,
                    drive_folder_id: str | None = None, timezone_name: str = "Asia/Kolkata",
                    quota=None) -> ConnectResult:
    """Consent ke baad: asli channel verify/register + encrypted tokens save."""
    if not getattr(creds, "refresh_token", None):
        raise OAuthError("Refresh token nahi mila - dobara connect karein (prompt=consent zaroori)")
    info = fetch_own_channel(youtube)
    if quota:
        quota.record("channels.list")
    cid = info["channel_id"]
    if expected_channel_id and expected_channel_id != cid:
        raise OAuthError(f"Galat channel chuna: chahiye {expected_channel_id}, mila {cid} ({info['channel_name']})")
    registered = False
    if svc.exists(cid):
        svc.update_profile(cid, info["channel_name"], info["thumbnail_url"])
        if drive_folder_id:
            svc.set_folder(cid, drive_folder_id)
    else:
        if not drive_folder_id:
            raise OAuthError(f"Channel {cid} DB mein nahi hai - --folder DRIVE_FOLDER_ID dein")
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
