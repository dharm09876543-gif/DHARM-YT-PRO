"""Token encryption (Fernet / AES). Tokens kabhi plain text mein store nahi hote."""
from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    return Fernet.generate_key().decode()


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise ValueError("TOKEN_ENCRYPTION_KEY set nahi hai")
        self._f = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise ValueError("Token decrypt nahi hua - key galat hai?") from e
