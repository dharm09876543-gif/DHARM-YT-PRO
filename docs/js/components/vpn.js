(function () {
  'use strict';
  const { h, ago, dt, num, sectionHead, load, stat, toast, busy, chip, empty } = DY.ui;
  const ST = {
    verified: ['green', 'IP verified'],
    failed: ['red', 'Failed — uploads skipped'],
    not_required: ['muted', 'No VPN'],
    unknown: ['orange', 'Not checked yet']
  };

  /** Only ever show a masked IP. A full IPv4 coming from a backend is masked here too. */
  function safeIp(v) {
    if (!v) return DY.ui.DASH;
    const m = /^(\d{1,3})\.\d{1,3}\.\d{1,3}\.(\d{1,3})$/.exec(String(v));
    return m ? `${m[1]}.x.x.${m[2]}` : String(v);
  }

  DY.views.vpn = {
    title: 'VPN Status',
    render(main) {
      const box = h('div');
      const checkBtn = h('button', { class: 'btn btn-cyan', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        try { await DY.api.post('/api/vpn/check'); toast(`VPN check done${DY.api.isDemo() ? ' (demo)' : ''}`, 'ok'); draw(); }
        catch (err) { toast(err.message, 'err'); }
      }) }, 'Check now');
      main.append(sectionHead('VPN Status', 'Surfshark WireGuard — optional, one outgoing IP per channel for uploads. Configs live only in GitHub Secrets (WG_CONF_<PROFILE>), never here.', checkBtn), box);
      const draw = () => load(box, () => DY.api.get('/api/vpn'), (d) => {
        const rows = d.channels || [];
        const withProfile = rows.filter((r) => r.vpn_profile);
        const verified = rows.filter((r) => r.status === 'verified').length;
        const failed = rows.filter((r) => r.status === 'failed').length;
        box.append(
          h('div', { class: 'grid grid-stats', style: { marginBottom: '12px' } },
            stat('VPN', d.enabled ? 'On' : 'Off (disabled)', d.provider || DY.ui.DASH, d.enabled ? 'green' : 'muted'),
            stat('Channels with a profile', num(withProfile.length), `of ${num(rows.length)}`, 'cyan'),
            stat('Verified', num(verified), 'IP changed before upload', 'green'),
            stat('Failed', num(failed), d.require_for_channels_with_profile === false ? 'Uploaded without VPN' : 'Uploads skipped, stay queued', failed ? 'red' : 'muted')),
          rows.length
            ? h('div', { class: 'table-wrap' }, h('table', null,
                h('caption', { class: 'sr-only' }, 'VPN profile per channel'),
                h('thead', null, h('tr', null, h('th', null, 'Channel'), h('th', null, 'Profile'), h('th', null, 'Upload IP (masked)'), h('th', null, 'Status'), h('th', null, 'Last check'))),
                h('tbody', null, rows.map((r) => {
                  const [tone, label] = ST[r.status] || ST.unknown;
                  return h('tr', null,
                    h('td', null, r.channel_name || r.channel_id || DY.ui.DASH),
                    h('td', { class: 'mono' }, r.vpn_profile || DY.ui.DASH),
                    h('td', { class: 'mono' }, safeIp(r.masked_ip)),
                    h('td', null, chip(tone, label)),
                    h('td', { title: dt(r.last_check_at) }, ago(r.last_check_at)));
                }))))
            : empty('No channels', null),
          h('p', { class: 'callout small', style: { marginTop: '12px' } }, d.note || 'A VPN does not change YouTube API quota (quota is per Google Cloud project).'));
      }, 4);
      draw();
    }
  };
})();
