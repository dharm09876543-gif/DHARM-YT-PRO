"""Generate TOKEN_ENCRYPTION_KEY and BACKEND_SECRET_KEY."""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.auth.encryption import generate_key  # noqa: E402

print("TOKEN_ENCRYPTION_KEY=" + generate_key())
print("BACKEND_SECRET_KEY=" + secrets.token_urlsafe(48))
print("\nPut these in your .env file and in GitHub Secrets. Never share them.")
