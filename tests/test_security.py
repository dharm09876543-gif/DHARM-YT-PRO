import pytest

from src.auth.encryption import TokenCipher, generate_key
from src.utils.logging import redact
from src.utils.retry import retry


def test_encrypt_roundtrip():
    c = TokenCipher(generate_key())
    enc = c.encrypt("1//refresh-token")
    assert "refresh" not in enc and c.decrypt(enc) == "1//refresh-token"


def test_wrong_key_fails():
    enc = TokenCipher(generate_key()).encrypt("x")
    with pytest.raises(ValueError):
        TokenCipher(generate_key()).decrypt(enc)


def test_redact():
    out = redact("tok ya29.abcDEF-123 and 1//0gREFRESH PrivateKey = abc123 password=hunter2")
    assert "abcDEF" not in out and "REFRESH" not in out and "abc123" not in out and "hunter2" not in out


def test_retry():
    calls = []
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError
        return "ok"
    assert retry(fn, lambda e: isinstance(e, TimeoutError), sleep=lambda s: None) == "ok"
    with pytest.raises(KeyError):
        retry(lambda: (_ for _ in ()).throw(KeyError()), lambda e: False, sleep=lambda s: None)


def test_gitignore_protects_secrets():
    from src.config import ROOT
    gi = (ROOT / ".gitignore").read_text()
    for pat in [".env", "client_secret*.json", "token*.json", "wg*.conf"]:
        assert pat in gi
