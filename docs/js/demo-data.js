/* FAKE (sample) data for DEMO MODE. No real channel, ID, email or token.
 * Every name contains "Sample"/"Demo" so it is never mistaken for real data. */
(function () {
  'use strict';
  const DY = (window.DY = window.DY || {});

  // Deterministic pseudo-random (same sample every time)
  let seed = 42;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  const pick = (a) => a[Math.floor(rnd() * a.length)];
  const now = Date.now();
  const H = 3600e3;
  const iso = (ms) => new Date(ms).toISOString();

  const niches = ['Devotional', 'Comedy', 'Tech', 'Cooking', 'Gaming', 'News', 'Kids', 'Shorts', 'Music', 'Travel', 'Fitness', 'Motivation'];
  const channels = Array.from({ length: 64 }, (_, i) => {
    const n = String(i + 1).padStart(2, '0');
    const auth = i % 17 === 5 ? 'expired' : i % 23 === 7 ? 'not_connected' : 'active';
    const enabled = i % 9 !== 4;
    const subs = Math.round(500 + rnd() * 250000 * (i < 10 ? 3 : 1));
    return {
      id: `demo-ch-${n}`,
      youtube_channel_id: `UC_SAMPLE_${n}`,
      name: `Sample ${niches[i % niches.length]} Channel ${n}`,
      thumbnail_url: null,
      auth_status: auth,
      enabled,
      drive_folder_name: `Demo Folder ${n}`,
      drive_folder_id: `SAMPLE_FOLDER_${n}`,
      uploaded: Math.round(rnd() * 400),
      queued: Math.round(rnd() * 12),
      failed: i % 6 === 0 ? Math.round(rnd() * 4) : 0,
      subscribers: subs,
      views_28d: i % 13 === 3 ? null : Math.round(subs * (2 + rnd() * 12)),
      watch_hours_28d: i % 13 === 3 ? null : Math.round(subs * (0.05 + rnd() * 0.4)),
      ctr: i % 13 === 3 ? null : +(2 + rnd() * 9).toFixed(1),
      last_upload_at: iso(now - rnd() * 96 * H),
      timezone: 'Asia/Kolkata'
    };
  });

  const states = ['DISCOVERED', 'QUEUED', 'DOWNLOADING', 'READY', 'UPLOADING', 'PROCESSING', 'VERIFYING', 'COMPLETED', 'FAILED', 'RETRY_WAIT', 'CANCELLED'];
  const queue = Array.from({ length: 18 }, (_, i) => {
    const status = i < 11 ? states[i] : pick(['QUEUED', 'UPLOADING', 'COMPLETED', 'COMPLETED', 'FAILED']);
    const ch = channels[i % channels.length];
    const progress = { DISCOVERED: 0, QUEUED: 0, DOWNLOADING: 35, READY: 0, UPLOADING: 62, PROCESSING: 100, VERIFYING: 100, COMPLETED: 100, FAILED: 48, RETRY_WAIT: 20, CANCELLED: 0 }[status];
    return {
      id: `demo-job-${i + 1}`,
      file_name: `sample_video_${String(i + 1).padStart(3, '0')}.mp4`,
      channel_id: ch.id,
      channel_name: ch.name,
      status,
      progress,
      size_bytes: Math.round((40 + rnd() * 900) * 1024 * 1024),
      attempts: status === 'FAILED' || status === 'RETRY_WAIT' ? 2 : status === 'COMPLETED' ? 1 : 0,
      error: status === 'FAILED' ? 'Sample error: quotaExceeded (demo)' : status === 'RETRY_WAIT' ? 'Sample: network timeout, retry in 5 min' : null,
      updated_at: iso(now - i * 0.4 * H),
      youtube_video_id: status === 'COMPLETED' ? null : null
    };
  });

  const schedules = Array.from({ length: 7 }, (_, i) => ({
    id: `demo-sch-${i + 1}`,
    title: `Sample scheduled video ${i + 1}`,
    channel_name: channels[(i * 3) % channels.length].name,
    scheduled_at: iso(now + (i + 1) * 5 * H),
    privacy: 'private',
    status: i === 6 ? 'failed' : 'pending'
  }));

  const errors = [
    { at: iso(now - 0.3 * H), source: 'upload', message: 'Sample: quotaExceeded — today\'s quota used up (demo)' },
    { at: iso(now - 2.1 * H), source: 'oauth', message: 'Sample: Sample Kids Channel 07 token expired (demo)' },
    { at: iso(now - 5.4 * H), source: 'drive', message: 'Sample: no permission on Demo Folder 12 (demo)' }
  ];

  function series(days) {
    return Array.from({ length: days }, (_, i) => {
      const d = new Date(now - (days - 1 - i) * 24 * H);
      const isLatest = i === days - 1; // today's data often arrives late in YouTube Analytics
      return {
        date: d.toISOString().slice(0, 10),
        views: isLatest ? null : Math.round(8000 + rnd() * 20000 + i * 150),
        watch_minutes: isLatest ? null : Math.round(20000 + rnd() * 60000),
        subscribers_gained: isLatest ? null : Math.round(40 + rnd() * 300),
        revenue: null
      };
    });
  }

  function analytics(range, customDays) {
    const days = customDays || { today: 1, '7d': 7, '28d': 28, '90d': 90 }[range] || 28;
    const s = series(days);
    const sum = (k) => { const v = s.map((r) => r[k]).filter((x) => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) : null; };
    return {
      range, sample: true,
      totals: { views: sum('views'), watch_minutes: sum('watch_minutes'), subscribers_gained: sum('subscribers_gained'), revenue: null, avg_ctr: days === 1 ? null : 5.8 },
      series: s,
      top_videos: Array.from({ length: 5 }, (_, i) => ({ title: `Sample top video #${i + 1}`, channel_name: channels[i].name, views: days === 1 ? null : Math.round(50000 / (i + 1)) }))
    };
  }

  const active = channels.filter((c) => c.enabled && c.auth_status === 'active').length;
  const disabled = channels.filter((c) => !c.enabled).length;

  DY.demo = {
    overview: {
      sample: true,
      channels: { total: channels.length, active, disabled },
      uploaded_total: channels.reduce((a, c) => a + c.uploaded, 0),
      queue: queue.filter((q) => ['DISCOVERED', 'QUEUED', 'READY', 'RETRY_WAIT'].includes(q.status)).length,
      processing: queue.filter((q) => ['DOWNLOADING', 'UPLOADING', 'PROCESSING', 'VERIFYING'].includes(q.status)).length,
      failed: queue.filter((q) => q.status === 'FAILED').length,
      scheduled: schedules.filter((s) => s.status === 'pending').length,
      views_28d: 1840000,
      subscribers_total: channels.reduce((a, c) => a + c.subscribers, 0),
      quota: { used: 6400, limit: 10000 },
      last_run: { at: iso(now - 0.6 * H), status: 'success', workflow: 'upload.yml (sample)' },
      latest_errors: errors
    },
    channels,
    queue,
    drive: {
      sample: true,
      connected: true,
      account_label: 'Demo Drive (sample)',
      folders: channels.slice(0, 12).map((c, i) => ({
        id: c.drive_folder_id, name: c.drive_folder_name, channel_name: c.name,
        pending_files: i % 4 === 1 ? 0 : Math.round(rnd() * 9), trashed_after_upload: Math.round(rnd() * 40),
        last_scan_at: iso(now - (i + 1) * 0.7 * H), status: i === 11 ? 'no_access' : 'ok'
      })),
      storage: { used_bytes: 412 * 1024 ** 3, limit_bytes: 2048 * 1024 ** 3 }
    },
    schedules,
    analytics,
    quota: {
      sample: true,
      projects: [
        { name: 'demo-project-1 (sample)', used: 6400, limit: 10000, uploads_today: 4 },
        { name: 'demo-project-2 (sample)', used: 1600, limit: 10000, uploads_today: 1 }
      ],
      cost: { upload: 1600, thumbnail: 50, metadata_update: 50, list: 1 },
      resets_at: (() => { const d = new Date(); d.setUTCHours(8, 0, 0, 0); if (d.getTime() < now) d.setUTCDate(d.getUTCDate() + 1); return d.toISOString(); })(),
      history: Array.from({ length: 7 }, (_, i) => ({ date: new Date(now - (6 - i) * 24 * H).toISOString().slice(0, 10), used: Math.round(3000 + rnd() * 7000) }))
    },
    health: {
      sample: true,
      checks: [
        { name: 'Database', status: 'ok', detail: 'Sample: connected' },
        { name: 'YouTube API', status: 'ok', detail: 'Sample: reachable' },
        { name: 'Google Drive API', status: 'ok', detail: 'Sample: reachable' },
        { name: 'Gemini API', status: 'warn', detail: 'Sample: key not set (demo)' },
        { name: 'OAuth tokens', status: 'warn', detail: 'Sample: 4 channels have expired/missing tokens' },
        { name: 'Encryption key', status: 'ok', detail: 'Sample: loaded' },
        { name: 'GitHub Actions', status: 'ok', detail: 'Sample: last run success' }
      ],
      audit: Array.from({ length: 10 }, (_, i) => ({
        at: iso(now - i * 1.3 * H),
        actor: i % 3 === 0 ? 'system' : 'admin (sample)',
        action: pick(['channel.enable', 'channel.disable', 'upload.retry', 'schedule.create', 'login', 'drive.scan', 'metadata.update']),
        target: pick(channels).name
      }))
    },
    vpn: {
      sample: true,
      enabled: true,
      provider: 'Surfshark WireGuard (optional)',
      require_for_channels_with_profile: true,
      last_check_at: iso(now - 0.2 * H),
      // Sample only: masked IPs (documentation ranges), no real servers or configs.
      channels: channels.slice(0, 8).map((c, i) => {
        const profile = i < 6 ? `ch${String(i + 1).padStart(2, '0')}` : null;
        const status = !profile ? 'not_required' : i === 4 ? 'failed' : i === 5 ? 'unknown' : 'verified';
        return {
          channel_id: c.youtube_channel_id,
          channel_name: c.name,
          vpn_profile: profile,
          status,
          masked_ip: status === 'verified' ? `185.x.x.${10 + i * 7}` : null,
          last_check_at: status === 'unknown' || !profile ? null : iso(now - (i + 1) * 0.5 * H)
        };
      }),
      note: 'Sample data. A VPN does not change YouTube API quota (quota is per Google Cloud project). Normal Surfshark servers give shared IPs that can change; a fixed unique IP per channel needs the Dedicated IP add-on (one per IP).'
    }
  };
})();
