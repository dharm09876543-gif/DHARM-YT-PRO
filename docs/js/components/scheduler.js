(function () {
  'use strict';
  const { h, dt, ago, chip, sectionHead, load, empty, confirmAction, toast, busy } = DY.ui;
  const ST = { pending: ['gold', 'Waiting'], published: ['green', 'Published'], failed: ['red', 'Failed'], cancelled: ['muted', 'Cancelled'] };

  DY.views.scheduler = {
    title: 'Scheduler',
    render(main) {
      const box = h('div');
      main.append(sectionHead('Scheduler', 'Videos that will publish later. Times are shown in your device\'s timezone.',
        h('a', { href: '#metadata', class: 'btn btn-gold' }, '+ New schedule')), box);

      load(box, () => DY.api.get('/api/schedules'), (d) => {
        const items = ((d && d.items) || []).slice().sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
        if (!items.length) { box.append(empty('No schedules', 'Set a publish time in the Metadata Editor to schedule a video.')); return; }
        const list = h('ul', { class: 'list' });
        const draw = () => list.replaceChildren(...items.map((s) => {
          const [tone, label] = ST[s.status] || ['muted', s.status || DY.ui.DASH];
          return h('li', { class: 'item' },
            h('div', { class: 'item-main' },
              h('div', { class: 'item-title', title: s.title }, s.title),
              h('div', { class: 'item-meta' },
                h('span', null, s.channel_name || DY.ui.DASH),
                h('span', { style: { color: 'var(--gold)' } }, '🗓 ', dt(s.scheduled_at)),
                h('span', null, ago(s.scheduled_at)),
                h('span', null, s.privacy || DY.ui.DASH))),
            h('div', { class: 'item-side' },
              chip(tone, label),
              s.status === 'pending' ? h('button', { class: 'btn btn-sm btn-danger', type: 'button', 'aria-label': `Remove schedule for ${s.title}`, onclick: async (e) => {
                const btn = e.currentTarget;
                if (!(await confirmAction(`Remove the schedule for "${s.title}"? The video will not be published.`, 'Yes, remove'))) return;
                busy(btn, async () => {
                  try { await DY.api.del(`/api/schedules/${encodeURIComponent(s.id)}`); items.splice(items.indexOf(s), 1); toast('Schedule removed', 'ok'); items.length ? draw() : box.replaceChildren(empty('No schedules', null)); }
                  catch (err) { toast(err.message, 'err'); }
                });
              } }, 'Remove') : null));
        }));
        draw();
        box.append(list);
      }, 3);
    }
  };
})();
