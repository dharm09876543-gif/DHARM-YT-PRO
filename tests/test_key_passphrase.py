import pytest
from src.auth.encryption import TokenCipher, generate_key


def test_fernet_key_still_works():
    c = TokenCipher(generate_key())
    assert c.decrypt(c.encrypt("x")) == "x"


def test_passphrase_is_deterministic():
    p = "my very long secret passphrase 2026"
    a, b = TokenCipher(p), TokenCipher(p)
    assert b.decrypt(a.encrypt("tok")) == "tok"


def test_short_passphrase_rejected():
    with pytest.raises(ValueError):
        TokenCipher("short")


def test_wrong_passphrase_fails():
    a = TokenCipher("first passphrase that is long enough")
    b = TokenCipher("second passphrase that is long enough")
    with pytest.raises(ValueError):
        b.decrypt(a.encrypt("tok"))
