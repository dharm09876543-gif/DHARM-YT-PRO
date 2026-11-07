"""Finish a YouTube channel connect on GitHub Actions (no local PC needed).

1. Open the Google sign-in link (redirect http://localhost) and Allow.
2. The browser lands on a "can't reach localhost" page. Copy that whole address.
3. Run the "Connect channel" workflow with that address + the Drive folder ID.

  python main.py connect-url --url "http://localhost/?code=...&scope=..." --folder FOLDER_ID
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

REDIRECT = "http://localhost"


def extract_code(url: str) -> str:
    url = (url or "").strip()
    q = parse_qs(urlparse(url).query) if "?" in url else parse_qs(url)
    if q.get("error"):
        raise SystemExit(f"Error: Google returned '{q['error'][0]}' - sign in again and press Allow.")
    code = (q.get("code") or [""])[0]
    if not code:
        raise SystemExit("Error: no ?code= found in the URL. Copy the full address bar after pressing Allow.")
    return code


def folder_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if "/folders/" in value:
        value = value.split("/folders/", 1)[1]
    return value.split("?")[0].split("/")[0] or None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py connect-url")
    ap.add_argument("--url", default=os.getenv("CONNECT_URL", ""))
    ap.add_argument("--folder", default=os.getenv("CONNECT_FOLDER", ""))
    ap.add_argument("--channel", default=os.getenv("CONNECT_CHANNEL", "") or None)
    ap.add_argument("--timezone", default="Asia/Kolkata")
    a = ap.parse_args(argv)
    code = extract_code(a.url)
    if os.getenv("GITHUB_ACTIONS"):
        print(f"::add-mask::{code}")

    eng, cipher, settings, _, _ = bootstrap()
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build

    from src.auth.oauth import SCOPES, OAuthError, client_config, connect_channel
    from src.services.channel_service import ChannelService
    from src.services.quota import QuotaLedger

    flow = Flow.from_client_config(client_config("installed", REDIRECT), SCOPES, redirect_uri=REDIRECT)
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    try:
        flow.fetch_token(code=code)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "invalid_grant" in msg:
            raise SystemExit("Error: this sign-in code is used or expired (they last ~10 min). Make a new link and try again.")
        raise SystemExit(f"Error: token exchange failed: {msg[:200]}")
    creds = flow.credentials
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        r = connect_channel(ChannelService(eng, cipher), creds, yt, expected_channel_id=a.channel,
                            drive_folder_id=folder_id(a.folder), timezone_name=a.timezone,
                            quota=QuotaLedger(eng, settings))
    except OAuthError as e:
        raise SystemExit(f"Error: {e}")
    print(f"Connected: {r.channel_name} ({r.channel_id})" + (" - new channel created" if r.registered else ""))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"### Connected: {r.channel_name}\n\nChannel ID `{r.channel_id}`. Tokens saved encrypted.\n")


if __name__ == "__main__":
    main(sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "connect-url" else sys.argv[1:])
