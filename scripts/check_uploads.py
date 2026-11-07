"""Ask YouTube directly about every video we think we uploaded (1 quota unit per 50 videos).

  python main.py check-uploads
Prints only video IDs, channel IDs and statuses (logs are public: no titles, no filenames).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

eng, cipher, settings, _, _ = bootstrap()
from sqlalchemy import text  # noqa: E402

from src.auth.token_manager import TokenManager  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402

tm = TokenManager(ChannelService(eng, cipher))
for ch in ChannelService(eng, cipher).list():
    print(f"== Channel in DB: {ch['channel_id']} auth={ch['auth_status']}")
    yt = tm.services(ch["channel_id"])["youtube"]
    me = yt.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    print("   Token belongs to channel(s):", ", ".join(i["id"] for i in me) or "NONE")
    with eng.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(text(
            "SELECT id, youtube_video_id, upload_status, metadata_source, (SELECT event_status || ' ' || COALESCE(message,'') FROM upload_history h WHERE h.video_id=videos.id AND h.event_type='ai_video' ORDER BY h.id DESC LIMIT 1) AS ai FROM videos WHERE channel_id=:c AND youtube_video_id IS NOT NULL ORDER BY id"),
            {"c": ch["channel_id"]})]
    print(f"   Videos with a YouTube ID in DB: {len(rows)}")
    ids = [r["youtube_video_id"] for r in rows]
    found = {}
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="status,snippet,processingDetails", id=",".join(ids[i:i + 50])).execute()
        found.update({it["id"]: it for it in resp.get("items", [])})
    for r in rows:
        it = found.get(r["youtube_video_id"])
        if not it:
            print(f"   #{r['id']} {r['youtube_video_id']} db={r['upload_status']} -> NOT FOUND on YouTube (deleted/rejected)")
            continue
        st, sn = it["status"], it["snippet"]
        print(f"   #{r['id']} {it['id']} db={r['upload_status']} -> channel={sn.get('channelId')} "
              f"privacy={st.get('privacyStatus')} upload={st.get('uploadStatus')} "
              f"reject={st.get('rejectionReason', '-')} fail={st.get('failureReason', '-')} "
              f"processing={(it.get('processingDetails') or {}).get('processingStatus', '-')} "
              f"publishAt={st.get('publishAt', '-')} meta={r.get('metadata_source') or '-'} ai={(r.get('ai') or '-')[:160]} "
              f"title_len={len(sn.get('title', ''))} hashtags={sn.get('description', '').count('#')}")
