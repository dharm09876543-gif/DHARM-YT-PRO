import pytest

from src.auth.encryption import TokenCipher, generate_key
from src.services.channel_service import ChannelError, ChannelService

CID = "UC" + "a" * 22


@pytest.fixture
def svc(engine):
    return ChannelService(engine, TokenCipher(generate_key()))


def test_add_list_toggle(svc):
    svc.add(CID, "Dharm Vlogs", "folder1")
    with pytest.raises(ChannelError):
        svc.add(CID, "dup", "f")
    ch = svc.get(CID)
    assert ch["auth_status"] == "not_connected" and ch["enabled"]
    svc.disable(CID); assert not svc.get(CID)["enabled"]
    assert svc.list(enabled_only=True) == []
    svc.enable(CID); svc.rename(CID, "New"); svc.set_folder(CID, "f2"); svc.set_timezone(CID, "Asia/Dubai")
    ch = svc.get(CID)
    assert (ch["channel_name"], ch["drive_folder_id"], ch["timezone"]) == ("New", "f2", "Asia/Dubai")


def test_validation(svc):
    with pytest.raises(ChannelError):
        svc.add("bad", "x", "f")
    with pytest.raises(ChannelError):
        svc.add(CID, "x", "")
    with pytest.raises(ChannelError):
        svc.disable("UC" + "z" * 22)


def test_tokens_encrypted_and_status(svc, engine):
    from sqlalchemy import text
    svc.add(CID, "A", "f")
    svc.save_tokens(CID, "1//secret-refresh", "ya29.access")
    with engine.connect() as c:
        raw = c.execute(text("SELECT encrypted_refresh_token FROM oauth_credentials")).scalar()
    assert "secret" not in raw
    assert svc.refresh_token(CID) == "1//secret-refresh"
    assert svc.get(CID)["auth_status"] == "active"
    svc.mark_auth(CID, "revoked")
    with pytest.raises(ChannelError):
        svc.refresh_token(CID)
    assert not svc.health()[0]["ok"]


def test_remove_needs_confirm(svc):
    svc.add(CID, "A", "f"); svc.save_tokens(CID, "r")
    with pytest.raises(ChannelError):
        svc.remove(CID)
    svc.remove(CID, confirm=True)
    ch = svc.get(CID)
    assert ch["auth_status"] == "not_connected" and not ch["enabled"]
