"""Make uploaded videos public now (clears the scheduled publish time).

  python main.py make-public                 every uploaded video of every channel
  python main.py make-public --video ID,ID   only these YouTube video IDs
Costs 1 + 50 quota units per video. Logs show only video IDs and results.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

eng, cipher, settings, _, _ = bootstrap()
from googleapiclient.errors import HttpError  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.auth.token_manager import TokenManager  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402
from src.services.quota import QuotaLedger  # noqa: E402

args = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "make-public" else sys.argv[1:]
only = set(args[args.index("--video") + 1].split(",")) if "--video" in args else None
quota = QuotaLedger(eng, settings)
tm = TokenManager(ChannelService(eng, cipher))
bad = 0
for ch in ChannelService(eng, cipher).list():
    with eng.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(text(
            "SELECT id, youtube_video_id FROM videos WHERE channel_id=:c AND youtube_video_id IS NOT NULL ORDER BY id"),
            {"c": ch["channel_id"]})]
    rows = [r for r in rows if not only or r["youtube_video_id"] in only]
    if not rows:
        continue
    yt = tm.services(ch["channel_id"])["youtube"]
    for r in rows:
        vid = r["youtube_video_id"]
        try:
            items = yt.videos().list(part="status", id=vid).execute().get("items", [])
            quota.record("videos.list")
            if not items:
                print(f"{vid}: NOT FOUND"); bad = 1; continue
            st = items[0]["status"]
            if st.get("privacyStatus") == "public":
                print(f"{vid}: already public"); continue
            st["privacyStatus"] = "public"
            st.pop("publishAt", None)
            for k in ("uploadStatus", "failureReason", "rejectionReason", "madeForKids"):
                st.pop(k, None)
            out = yt.videos().update(part="status", body={"id": vid, "status": st}).execute()
            quota.record("videos.update")
            now = out["status"]["privacyStatus"]
            with eng.begin() as c:
                c.execute(text("UPDATE videos SET privacy_status=:p, scheduled_publish_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=:i"),
                          {"p": now, "i": r["id"]})
            print(f"{vid}: privacy now {now}")
            bad |= now != "public"
        except HttpError as e:
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "") if e.error_details else ""
            except Exception:  # noqa: BLE001
                pass
            print(f"{vid}: FAILED HTTP {e.resp.status} {reason} - {str(e)[-300:]}"); bad = 1
sys.exit(bad)
