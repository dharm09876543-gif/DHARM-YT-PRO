"""TOKEN_ENCRYPTION_KEY aur BACKEND_SECRET_KEY banayein."""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.auth.encryption import generate_key  # noqa: E402

print("TOKEN_ENCRYPTION_KEY=" + generate_key())
print("BACKEND_SECRET_KEY=" + secrets.token_urlsafe(48))
print("\nInhe .env file mein aur GitHub Secrets mein daalein. Kisi ko share na karein.")
