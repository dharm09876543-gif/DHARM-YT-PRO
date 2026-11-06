CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id BIGSERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    report_date DATE NOT NULL,
    views BIGINT,
    watch_time_minutes NUMERIC,
    subscribers_gained BIGINT,
    subscribers_lost BIGINT,
    estimated_revenue NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, report_date)
);
CREATE INDEX IF NOT EXISTS idx_analytics_date ON analytics_snapshots(report_date);

