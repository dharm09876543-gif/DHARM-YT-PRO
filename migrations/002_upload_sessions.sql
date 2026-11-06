CREATE TABLE IF NOT EXISTS upload_sessions (
    id BIGSERIAL PRIMARY KEY,
    video_id BIGINT NOT NULL REFERENCES videos(id),
    encrypted_session_uri TEXT,
    bytes_uploaded BIGINT DEFAULT 0,
    total_bytes BIGINT,
    session_status TEXT NOT NULL DEFAULT 'active',
    last_checkpoint_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- ek video ka sirf ek active session
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session
    ON upload_sessions(video_id) WHERE session_status = 'active';
