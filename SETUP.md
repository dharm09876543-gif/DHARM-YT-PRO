# Setup Guide

## 1. Google Cloud project
1. Open https://console.cloud.google.com and click **New Project** at the top → name it `dharm-yt-pro`.
2. Under **APIs & Services → Library**, enable these 3 APIs:
   - YouTube Data API v3
   - YouTube Analytics API
   - Google Drive API

## 2. OAuth (to connect channels)
1. **OAuth consent screen** → External → app name `DHARM YT PRO` → your email.
2. Add the scopes: `youtube.upload`, `youtube`, `yt-analytics.readonly`, `drive`.
3. Under **Test users**, add the email of every Google account whose channel you want to connect.
4. **Credentials → Create credentials → OAuth client ID → Web application**
   - Redirect URI: `http://localhost:8080/oauth/callback`
5. Put the Client ID and Secret into `.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

## 3. Google Drive folders
```
DHARM_YT_PRO/
  CHANNEL_001/videos/   CHANNEL_001/thumbnails/
  CHANNEL_002/videos/   ...
```
Open a folder; the last part of its URL (`.../folders/XXXX`) is the `drive_folder_id`. Put it in `config/channels.yaml`.

## 4. Config
```bash
cp config/settings.example.yaml config/settings.yaml
cp config/channels.example.yaml config/channels.yaml
cp config/schedules.example.yaml config/schedules.yaml
python main.py validate
```
Gemini writes metadata in **English** by default. Per channel you can set `defaults.language: Hindi` or `Hinglish`
in `config/channels.yaml`; `python main.py ai ... --language Hindi` works too.

## 5. GitHub Secrets (for cloud automation)
Repo → **Settings → Secrets and variables → Actions → New secret**:
`DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Optional VPN (Phase 9): one secret per WireGuard profile, e.g. `WG_CONF_CH01`, `WG_CONF_CH02` (see step 7).
Optional repository **variable** `UPLOAD_MAX_PARALLEL` (default 4) = how many channel jobs upload at once.

## 6. Free PostgreSQL
Create a free Postgres database on Neon.tech or Supabase, name the database `dharm_yt`, and put the connection string in `DATABASE_URL`.

## 7. Optional: separate outgoing IP per channel (Surfshark WireGuard)
1. In your Surfshark account, open the manual WireGuard setup (menu names may change), create a key pair and download a
   config for a location (or for your **Dedicated IP**). Each config is a `.conf` text with `[Interface]` and `[Peer]`.
2. Create a GitHub secret per profile, named `WG_CONF_<PROFILE>` in upper case (`ch01` → `WG_CONF_CH01`), and paste the
   whole `.conf` text as its value. Never commit a `.conf` file (`.gitignore` blocks `*.conf`).
3. Link the profile to a channel: `python main.py channels vpn --channel UC... --profile ch01`
   (remove it with `--clear`).
4. In `config/settings.yaml` set `vpn.enabled: true`. Keep `require_for_channels_with_profile: true` so a channel never
   uploads from the wrong IP.
5. Run **Actions → Upload videos → Run workflow** and check the channel's job log for `VPN ch01 up: public IP 185.x.x.12`.

## Quota increase
Console → IAM & Admin → Quotas → YouTube Data API v3 → fill in the "YouTube API Services - Audit and Quota Extension Form".
