"""Token encryption (Fernet / AES). Tokens are never stored in plain text.

TOKEN_ENCRYPTION_KEY may be either a Fernet key (from `main.py keygen`) or a
long passphrase (20+ characters). A passphrase is stretched into a Fernet key
with scrypt, so the same passphrase always gives the same key.
"""
import base64
import binascii
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_SALT = b"dharm-yt-pro/token-key/v1"
MIN_PASSPHRASE = 20


def generate_key() -> str:
    return Fernet.generate_key().decode()


def _is_fernet_key(key: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(key.encode())) == 32 and len(key) == 44
    except (binascii.Error, ValueError):
        return False


def derive_key(key: str) -> bytes:
    key = key.strip()
    if _is_fernet_key(key):
        return key.encode()
    if len(key) < MIN_PASSPHRASE:
        raise ValueError(f"TOKEN_ENCRYPTION_KEY passphrase must be at least {MIN_PASSPHRASE} characters")
    raw = hashlib.scrypt(key.encode(), salt=_SALT, n=2**14, r=8, p=1, dklen=32)
    return base64.urlsafe_b64encode(raw)


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise ValueError("TOKEN_ENCRYPTION_KEY is not set")
        self._f = Fernet(derive_key(key))

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise ValueError("Token could not be decrypted - wrong key?") from e
