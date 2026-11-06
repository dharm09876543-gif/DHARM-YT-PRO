-- Phase 3-8: discovery, thumbnails, verification, cleanup, retry bookkeeping
ALTER TABLE videos ADD COLUMN drive_md5 TEXT;
ALTER TABLE videos ADD COLUMN thumbnail_drive_id TEXT;
ALTER TABLE videos ADD COLUMN thumbnail_status TEXT;
ALTER TABLE videos ADD COLUMN verified_channel_id TEXT;
ALTER TABLE videos ADD COLUMN last_error TEXT;
ALTER TABLE videos ADD COLUMN next_retry_at TIMESTAMPTZ;
ALTER TABLE videos ADD COLUMN drive_trashed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_videos_md5 ON videos(channel_id, drive_md5);
