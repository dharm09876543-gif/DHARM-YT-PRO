(function () {
  'use strict';
  const { h, dt, ago, chip, sectionHead, load, empty, confirmAction, toast, busy } = DY.ui;
  const ST = { pending: ['gold', 'Intezaar'], published: ['green', 'Publish ho gaya'], failed: ['red', 'Fail'], cancelled: ['muted', 'Cancel'] };

  DY.views.scheduler = {
    title: 'Scheduler',
    render(main) {
      const box = h('div');
      main.append(sectionHead('Scheduler', 'Aage publish hone wale videos. Time aapke device ke timezone mein dikhte hain.',
        h('a', { href: '#metadata', class: 'btn btn-gold' }, '+ Naya schedule')), box);

      load(box, () => DY.api.get('/api/schedules'), (d) => {
        const items = ((d && d.items) || []).slice().sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
        if (!items.length) { box.append(empty('Koi schedule nahi', 'Metadata Editor mein publish time daal ke schedule karo.')); return; }
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
              s.status === 'pending' ? h('button', { class: 'btn btn-sm btn-danger', type: 'button', 'aria-label': `${s.title} ka schedule hatao`, onclick: async (e) => {
                const btn = e.currentTarget;
                if (!(await confirmAction(`"${s.title}" ka schedule hata dein? Video publish nahi hoga.`, 'Haan, hatao'))) return;
                busy(btn, async () => {
                  try { await DY.api.del(`/api/schedules/${encodeURIComponent(s.id)}`); items.splice(items.indexOf(s), 1); toast('Schedule hata diya', 'ok'); items.length ? draw() : box.replaceChildren(empty('Koi schedule nahi', null)); }
                  catch (err) { toast(err.message, 'err'); }
                });
              } }, 'Hatao') : null));
        }));
        draw();
        box.append(list);
      }, 3);
    }
  };
})();
