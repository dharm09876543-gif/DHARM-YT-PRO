from datetime import datetime
from types import SimpleNamespace

import pytest

from src.auth.oauth import SCOPES, OAuthError, client_config, connect_channel, fetch_own_channel, run_installed_flow
from src.auth.token_manager import AuthRevoked, TokenManager
from tests.fakes import _Exec

CID = "UC" + "d" * 22


class FakeYTChannels:
    def __init__(self, items):
        self.items, self.calls = items, []

    def channels(self):
        return self

    def list(self, **kw):
        self.calls.append(kw)
        return _Exec(lambda: {"items": self.items})


def _item(cid=CID, title="Asli Channel"):
    return {"id": cid, "snippet": {"title": title, "thumbnails": {"high": {"url": "https://yt3/x.jpg"}}}}


def _creds(rt="1//new-refresh"):
    return SimpleNamespace(refresh_token=rt, token="ya29.tok", expiry=datetime(2030, 1, 1), scopes=SCOPES)


def test_scopes_and_client_config(monkeypatch):
    assert "https://www.googleapis.com/auth/youtube.upload" in SCOPES
    assert "https://www.googleapis.com/auth/drive" in SCOPES
    assert "https://www.googleapis.com/auth/yt-analytics.readonly" in SCOPES
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(OAuthError):
        client_config()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    assert client_config()["installed"]["client_id"] == "cid"


def test_installed_flow_requests_offline_consent(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid"); monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    seen = {}

    class Flow:
        @classmethod
        def from_client_config(cls, cfg, scopes):
            seen["scopes"] = scopes
            return cls()

        def run_local_server(self, **kw):
            seen.update(kw)
            return _creds()
    run_installed_flow(port=9999, open_browser=False, flow_cls=Flow)
    assert seen["prompt"] == "consent" and seen["access_type"] == "offline" and seen["port"] == 9999
    assert seen["scopes"] == SCOPES


def test_connect_registers_real_channel_and_encrypts(engine, chsvc):
    yt = FakeYTChannels([_item()])
    r = connect_channel(chsvc, _creds(), yt, drive_folder_id="fold1")
    assert r.registered and r.channel_id == CID and yt.calls[0]["mine"] is True
    ch = chsvc.get(CID)
    assert ch["channel_name"] == "Asli Channel" and ch["auth_status"] == "active"
    assert ch["thumbnail_url"] == "https://yt3/x.jpg"
    assert chsvc.refresh_token(CID) == "1//new-refresh"
    from sqlalchemy import text
    with engine.connect() as c:
        raw = c.execute(text("SELECT encrypted_refresh_token FROM oauth_credentials")).scalar()
    assert "new-refresh" not in raw


def test_connect_existing_updates_and_mismatch_rejected(chsvc):
    chsvc.add(CID, "Old Name", "f")
    r = connect_channel(chsvc, _creds(), FakeYTChannels([_item(title="New")]))
    assert not r.registered and chsvc.get(CID)["channel_name"] == "New"
    with pytest.raises(OAuthError, match="Wrong channel"):
        connect_channel(chsvc, _creds(), FakeYTChannels([_item()]), expected_channel_id="UC" + "e" * 22)
    with pytest.raises(OAuthError, match="Refresh token"):
        connect_channel(chsvc, _creds(rt=None), FakeYTChannels([_item()]))


def test_connect_errors_no_channel_or_no_folder(chsvc):
    with pytest.raises(OAuthError, match="No YouTube channel"):
        fetch_own_channel(FakeYTChannels([]))
    with pytest.raises(OAuthError, match="--folder"):
        connect_channel(chsvc, _creds(), FakeYTChannels([_item()]))


class FakeCreds:
    instances = []

    def __init__(self, **kw):
        self.kw, self.token, self.expiry = kw, None, None
        FakeCreds.instances.append(self)

    def refresh(self, request):
        if self.kw["refresh_token"] == "1//dead":
            raise Exception("('invalid_grant: Token has been expired or revoked.', {...})")
        self.token, self.expiry = "ya29.fresh", datetime(2030, 1, 1)


def test_token_refresh_builds_credentials(engine, chsvc, channel):
    tm = TokenManager(chsvc, "cid", "sec", credentials_cls=FakeCreds, request_factory=object)
    creds = tm.credentials(channel["channel_id"])
    assert creds.kw["refresh_token"] == "1//refresh-x" and creds.kw["client_id"] == "cid"
    assert creds.kw["client_secret"] == "sec" and creds.kw["token_uri"].startswith("https://oauth2")
    assert creds.token == "ya29.fresh"


def test_invalid_grant_marks_revoked(chsvc, channel):
    chsvc.save_tokens(channel["channel_id"], "1//dead")
    tm = TokenManager(chsvc, "cid", "sec", credentials_cls=FakeCreds, request_factory=object)
    with pytest.raises(AuthRevoked, match="reconnect"):
        tm.credentials(channel["channel_id"])
    assert chsvc.get(channel["channel_id"])["auth_status"] == "revoked"
    with pytest.raises(AuthRevoked):        # after revoke, no refresh is even attempted
        tm.credentials(channel["channel_id"])


def test_services_built_with_credentials(chsvc, channel):
    tm = TokenManager(chsvc, "cid", "sec", credentials_cls=FakeCreds, request_factory=object)
    built = []
    s = tm.services(channel["channel_id"], build=lambda n, v, **kw: built.append((n, v, kw)) or n)
    assert set(s) == {"youtube", "drive", "analytics"}
    assert all(kw["credentials"].token == "ya29.fresh" for _, _, kw in built)
