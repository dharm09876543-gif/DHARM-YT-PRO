(function () {
  'use strict';
  const { h, num, compact, ago, dt, stat, sectionHead, load, chip, empty, progress } = DY.ui;

  DY.views.overview = {
    title: 'Overview',
    render(main) {
      const box = h('div');
      main.append(sectionHead('Aaj ka haal', 'Saare channels aur uploads ek nazar mein'), box);
      load(box, () => DY.api.get('/api/overview'), (d) => {
        const c = d.channels || {};
        const q = d.quota || {};
        const qPct = q.limit && !DY.ui.isNil(q.used) ? Math.round((q.used / q.limit) * 100) : null;
        const run = d.last_run || {};
        box.append(
          h('div', { class: 'grid grid-stats' },
            stat('Channels', num(c.total), `${num(c.active)} active · ${num(c.disabled)} band`, 'gold'),
            stat('Active channels', num(c.active), 'Enabled + auth OK', 'green'),
            stat('Disabled', num(c.disabled), 'Band kiye hue', 'muted'),
            stat('Uploaded', num(d.uploaded_total), 'Kul videos', 'green'),
            stat('Queue', num(d.queue), 'Line mein videos', 'cyan'),
            stat('Processing', num(d.processing), 'Abhi chal rahe', 'cyan'),
            stat('Failed', num(d.failed), 'Dhyan do', d.failed ? 'red' : 'muted'),
            stat('Scheduled', num(d.scheduled), 'Aage publish honge', 'gold'),
            stat('Views (28 din)', compact(d.views_28d), 'Saare channels', 'cyan'),
            stat('Subscribers', compact(d.subscribers_total), 'Kul', 'green'),
            (() => {
              const card = stat('Quota used', qPct === null ? DY.ui.DASH : `${qPct}%`, `${num(q.used)} / ${num(q.limit)} units`, qPct !== null && qPct >= 85 ? 'red' : 'gold');
              card.append(progress(qPct, qPct >= 85 ? 'bad' : '', 'Quota used'));
              return card;
            })(),
            stat('Last run', ago(run.at), [run.workflow || DY.ui.DASH, ' · ', run.status === 'success' ? 'OK ✓' : run.status ? 'Fail ✕' : DY.ui.DASH], run.status === 'failed' ? 'red' : 'green')
          ),
          h('div', { class: 'card', style: { marginTop: '12px' } },
            h('div', { class: 'card-head' }, h('h3', null, 'Latest errors'), h('a', { href: '#health', class: 'btn btn-sm btn-ghost' }, 'Health dekho')),
            (d.latest_errors && d.latest_errors.length)
              ? h('ul', { class: 'err-list' }, d.latest_errors.map((e) => h('li', null,
                  chip('red', e.source || 'error'),
                  h('span', { class: 'msg' }, e.message),
                  h('span', { class: 'when', title: dt(e.at) }, ago(e.at)))))
              : empty('Koi error nahi 🎉', 'Sab theek chal raha hai.')
          )
        );
      }, 12);
    }
  };
})();
