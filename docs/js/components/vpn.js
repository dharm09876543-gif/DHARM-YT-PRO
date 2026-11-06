(function () {
  'use strict';
  const { h, ago, dt, sectionHead, load, stat, toast, busy } = DY.ui;

  DY.views.vpn = {
    title: 'VPN Status',
    render(main) {
      const box = h('div');
      const checkBtn = h('button', { class: 'btn btn-cyan', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        try { await DY.api.post('/api/vpn/check'); toast(`VPN check ho gaya${DY.api.isDemo() ? ' (demo)' : ''}`, 'ok'); draw(); }
        catch (err) { toast(err.message, 'err'); }
      }) }, 'Abhi check karo');
      main.append(sectionHead('VPN Status', 'Surfshark WireGuard — optional. Config sirf backend/GitHub Secrets mein, yahan kabhi nahi.', checkBtn), box);
      const draw = () => load(box, () => DY.api.get('/api/vpn'), (d) => {
        const up = d.status === 'connected';
        box.append(
          h('div', { class: 'grid grid-stats', style: { marginBottom: '12px' } },
            stat('Status', up ? 'Connected' : d.enabled ? 'Disconnected' : 'Band (off)', d.provider || DY.ui.DASH, up ? 'green' : d.enabled ? 'red' : 'muted'),
            stat('Server', d.server || DY.ui.DASH, 'Location', 'cyan'),
            stat('Public IP', d.public_ip || DY.ui.DASH, 'Bahar se dikhne wala', 'gold'),
            stat('Last check', ago(d.last_check_at), dt(d.last_check_at), 'muted')),
          h('p', { class: 'callout small' }, d.note || 'VPN se YouTube quota nahi badhta.'));
      }, 4);
      draw();
    }
  };
})();
