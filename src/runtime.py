"""Scripts ke liye common wiring: .env, DB, cipher, config, per-channel Google clients."""
from __future__ import annotations

import os
import sys

from src.config import ROOT, load_yaml


def load_dotenv() -> None:
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


def require_env(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        print("Galti: ye zaroori settings/secrets nahi mile: " + ", ".join(missing))
        print("Local: .env mein daalein. GitHub: Settings > Secrets and variables > Actions.")
        sys.exit(2)


def bootstrap(need_google: bool = True):
    """(engine, cipher, settings, schedules, channels_cfg)"""
    load_dotenv()
    req = ["TOKEN_ENCRYPTION_KEY"] + (["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"] if need_google else [])
    require_env(*req)
    from src.auth.encryption import TokenCipher
    from src.database.connection import get_engine, run_migrations
    eng = get_engine()
    run_migrations(eng)
    return (eng, TokenCipher(os.environ["TOKEN_ENCRYPTION_KEY"]), load_yaml("settings"),
            load_yaml("schedules"), load_yaml("channels"))


def channel_defaults(channels_cfg: dict):
    by_id = {c.get("channel_id"): (c.get("defaults") or {}) for c in channels_cfg.get("channels") or []}
    return lambda ch: by_id.get(ch["channel_id"], {})


def make_ctx_factory(engine, cipher, settings, build=None):
    from src.auth.token_manager import TokenManager
    from src.clients.drive_client import DriveClient
    from src.services.channel_service import ChannelService
    from src.services.quota import QuotaLedger
    from src.upload.pipeline import UploadContext
    from src.upload.youtube_client import YouTubeClient
    tm = TokenManager(ChannelService(engine, cipher))
    quota = QuotaLedger(engine, settings)

    def factory(channel: dict) -> UploadContext:
        s = tm.services(channel["channel_id"], build=build)
        ctx = UploadContext(engine, cipher, YouTubeClient(s["youtube"], quota), DriveClient(s["drive"]),
                            quota, settings, tmp_dir=ROOT / "data" / "tmp")
        ctx.analytics = s["analytics"]
        return ctx
    return factory
