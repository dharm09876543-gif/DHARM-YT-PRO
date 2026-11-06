-- DHARM YT PRO: database dharm_yt
CREATE TABLE IF NOT EXISTS channels (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT UNIQUE NOT NULL,
    channel_name TEXT NOT NULL,
    thumbnail_url TEXT,
    drive_folder_id TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_credentials (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT UNIQUE NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT NOT NULL,
    token_expiry TIMESTAMPTZ,
    scopes JSONB,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS videos (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    drive_file_id TEXT NOT NULL,
    drive_file_version TEXT NOT NULL DEFAULT '1',
    filename TEXT NOT NULL,
    file_size BIGINT,
    mime_type TEXT,
    youtube_video_id TEXT UNIQUE,
    title TEXT,
    description TEXT,
    tags JSONB,
    category_id TEXT,
    privacy_status TEXT,
    scheduled_publish_at TIMESTAMPTZ,
    upload_status TEXT NOT NULL DEFAULT 'DISCOVERED',
    processing_status TEXT,
    locked_by TEXT,
    locked_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, drive_file_id, drive_file_version),
    CHECK (upload_status IN ('DISCOVERED','QUEUED','DOWNLOADING','READY','UPLOADING',
        'PROCESSING','VERIFYING','COMPLETED','FAILED','RETRY_WAIT','CANCELLED'))
);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(upload_status);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);

CREATE TABLE IF NOT EXISTS upload_history (
    id BIGSERIAL PRIMARY KEY,
    video_id BIGINT NOT NULL REFERENCES videos(id),
    event_type TEXT NOT NULL,
    event_status TEXT NOT NULL,
    message TEXT,
    youtube_video_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_history_video ON upload_history(video_id);

CREATE TABLE IF NOT EXISTS quota_usage (
    id BIGSERIAL PRIMARY KEY,
    quota_date DATE NOT NULL,
    api_project_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    quota_units BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(quota_date, api_project_id, operation)
);

CREATE TABLE IF NOT EXISTS schedules (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    video_id BIGINT NOT NULL REFERENCES videos(id),
    scheduled_at TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(video_id)
);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(status, scheduled_at);
