"""Trash the Drive files of verified videos (with a live re-verify on YouTube).

  python main.py cleanup            trash files
  python main.py cleanup --dry-run  only show what would happen
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap, make_ctx_factory  # noqa: E402

dry = "--dry-run" in sys.argv
eng, cipher, settings, _, _ = bootstrap()
from sqlalchemy import text  # noqa: E402

from src.auth.token_manager import AuthRevoked  # noqa: E402
from src.cleanup.drive_trash import blocking_reasons, cleanup_channel  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402

bad = False
factory = make_ctx_factory(eng, cipher, settings)
for ch in ChannelService(eng, cipher).list(enabled_only=True):
    if dry:
        with eng.connect() as c:
            rows = [dict(r._mapping) for r in c.execute(text(
                "SELECT * FROM videos WHERE channel_id=:c AND upload_status='COMPLETED' AND drive_trashed_at IS NULL"),
                {"c": ch["channel_id"]})]
        for v in rows:
            why = blocking_reasons(v, settings)
            print(f"[{'TRASH' if not why else 'BLOCK'}] {ch['channel_name']} / {v['filename']}"
                  + ("" if not why else "  -> " + ", ".join(why)))
        continue
    if ch["auth_status"] != "active":
        print(f"Skip {ch['channel_name']}: auth={ch['auth_status']}"); continue
    try:
        ctx = factory(ch)
        out = cleanup_channel(eng, ctx.drive, ch["channel_id"], settings, yt=ctx.yt)
        print(f"{ch['channel_name']}: trash={out['trashed']} blocked={len(out['blocked'])}")
        for vid, why in out["blocked"].items():
            print(f"   video {vid}: {', '.join(why)}")
    except AuthRevoked as e:
        bad = True; print(f"!! {ch['channel_name']}: {e}")
    except Exception as e:  # noqa: BLE001
        bad = True; print(f"!! {ch['channel_name']}: {type(e).__name__}: {e}")
sys.exit(1 if bad else 0)
