# Setup Guide (Hindi)

## 1. Google Cloud project
1. https://console.cloud.google.com kholein, upar **New Project** → naam `dharm-yt-pro`.
2. **APIs & Services → Library** mein ye 3 enable karein:
   - YouTube Data API v3
   - YouTube Analytics API
   - Google Drive API

## 2. OAuth (channel connect karne ke liye)
1. **OAuth consent screen** → External → app naam `DHARM YT PRO` → apna email.
2. Scopes add karein: `youtube.upload`, `youtube`, `yt-analytics.readonly`, `drive`.
3. **Test users** mein har us Google account ka email daalein jiske channel connect karne hain.
4. **Credentials → Create credentials → OAuth client ID → Web application**
   - Redirect URI: `http://localhost:8080/oauth/callback`
5. Client ID aur Secret ko `.env` mein `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` mein daalein.

## 3. Google Drive folders
```
DHARM_YT_PRO/
  CHANNEL_001/videos/   CHANNEL_001/thumbnails/
  CHANNEL_002/videos/   ...
```
Folder kholein, URL ka aakhri hissa (`.../folders/XXXX`) = `drive_folder_id`. Ise `config/channels.yaml` mein daalein.

## 4. Config
```bash
cp config/settings.example.yaml config/settings.yaml
cp config/channels.example.yaml config/channels.yaml
cp config/schedules.example.yaml config/schedules.yaml
python main.py validate
```

## 5. GitHub Secrets (cloud automation ke liye)
Repo → **Settings → Secrets and variables → Actions → New secret**:
`DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `GEMINI_API_KEY`, (optional) `SURFSHARK_WIREGUARD_CONFIG`, `TELEGRAM_BOT_TOKEN`.

## 6. Free PostgreSQL
Neon.tech ya Supabase par free Postgres banayein, database naam `dharm_yt`, connection string `DATABASE_URL` mein.

## Quota increase
Console → IAM & Admin → Quotas → YouTube Data API v3 → "YouTube API Services - Audit and Quota Extension Form" bharein.
