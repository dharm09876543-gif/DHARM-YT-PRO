(function () {
  'use strict';
  const { h, bytes, ago, statusChip, sectionHead, load, empty, progress, confirmAction, toast, busy, STATUS } = DY.ui;

  const ORDER = ['DISCOVERED', 'QUEUED', 'DOWNLOADING', 'READY', 'UPLOADING', 'PROCESSING', 'VERIFYING', 'COMPLETED', 'FAILED', 'RETRY_WAIT', 'CANCELLED'];
  const ACTIVE = ['DISCOVERED', 'QUEUED', 'DOWNLOADING', 'READY', 'UPLOADING', 'PROCESSING', 'VERIFYING', 'RETRY_WAIT'];

  DY.views.queue = {
    title: 'Batch Upload',
    render(main) {
      let items = [];
      let filter = 'active';
      const summary = h('div', { class: 'tag-list', style: { marginBottom: '12px' } });
      const seg = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Queue filter' });
      const listBox = h('div');
      [['active', 'Chal rahe'], ['FAILED', 'Fail'], ['COMPLETED', 'Ho gaye'], ['all', 'Sab']].forEach(([k, l]) =>
        seg.append(h('button', { type: 'button', 'aria-pressed': String(k === filter), onclick: (e) => {
          filter = k; seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); draw();
        } }, l)));

      main.append(
        sectionHead('Batch Upload Queue', 'Har video ka live status. Fail hua to Retry dabao.', seg),
        h('p', { class: 'hint' }, 'Flow: ', ORDER.slice(0, 8).map((s, i) => [i ? ' → ' : '', STATUS[s][1]])),
        summary,
        listBox
      );

      function draw() {
        const counts = {};
        items.forEach((j) => { counts[j.status] = (counts[j.status] || 0) + 1; });
        summary.replaceChildren(...ORDER.filter((s) => counts[s]).map((s) => h('span', null, statusChip(s), ' ', h('span', { class: 'small muted' }, `×${counts[s]}`))));
        const rows = items.filter((j) => filter === 'all' ? true : filter === 'active' ? ACTIVE.includes(j.status) : j.status === filter);
        if (!items.length) { listBox.replaceChildren(empty('Queue khaali hai', 'Drive folder mein video daalo, agla scan inhe yahan le aayega.', h('a', { href: '#drive', class: 'btn btn-gold' }, 'Drive dekho'))); return; }
        if (!rows.length) { listBox.replaceChildren(empty('Is filter mein kuch nahi', null)); return; }
        listBox.replaceChildren(h('ul', { class: 'list' }, rows.map(row)));
      }

      function row(j) {
        const tone = j.status === 'COMPLETED' ? 'ok' : j.status === 'FAILED' ? 'bad' : '';
        const showPct = ['DOWNLOADING', 'UPLOADING', 'FAILED', 'RETRY_WAIT'].includes(j.status);
        const actions = h('div', { class: 'btn-row' });
        if (['FAILED', 'RETRY_WAIT', 'CANCELLED'].includes(j.status)) {
          actions.append(h('button', { class: 'btn btn-sm btn-cyan', type: 'button', 'aria-label': `${j.file_name} retry karein`, onclick: (e) => busy(e.currentTarget, async () => {
            try { await DY.api.post(`/api/queue/${encodeURIComponent(j.id)}/retry`); j.status = 'QUEUED'; j.error = null; j.progress = 0; toast('Retry line mein daal diya ✓', 'ok'); draw(); }
            catch (err) { toast(err.message, 'err'); }
          }) }, '↻ Retry'));
        }
        if (ACTIVE.includes(j.status)) {
          actions.append(h('button', { class: 'btn btn-sm btn-danger', type: 'button', 'aria-label': `${j.file_name} cancel karein`, onclick: async (e) => {
            const btn = e.currentTarget;
            const ok = await confirmAction(`"${j.file_name}" ka upload cancel karna hai? Drive file safe rahegi, sirf yeh job rukega.`, 'Haan, cancel karo');
            if (!ok) return;
            busy(btn, async () => {
              try { await DY.api.post(`/api/queue/${encodeURIComponent(j.id)}/cancel`); j.status = 'CANCELLED'; toast('Cancel ho gaya', 'ok'); draw(); }
              catch (err) { toast(err.message, 'err'); }
            });
          } }, 'Cancel'));
        }
        return h('li', { class: 'item', style: { flexDirection: 'column', alignItems: 'stretch' } },
          h('div', { style: { display: 'flex', gap: '10px', alignItems: 'flex-start', justifyContent: 'space-between' } },
            h('div', { class: 'item-main' },
              h('div', { class: 'item-title mono', title: j.file_name }, j.file_name),
              h('div', { class: 'item-meta' },
                h('span', null, j.channel_name || DY.ui.DASH),
                h('span', null, bytes(j.size_bytes)),
                h('span', null, `Try: ${j.attempts ?? DY.ui.DASH}`),
                h('span', null, ago(j.updated_at)))),
            statusChip(j.status)),
          showPct || tone ? h('div', null, progress(j.progress, tone, `${j.file_name} progress`), showPct ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, j.progress == null ? DY.ui.DASH : `${j.progress}%`) : null) : null,
          j.error ? h('div', { class: 'callout bad small', style: { marginTop: '8px' } }, j.error) : null,
          actions.childNodes.length ? h('div', { style: { marginTop: '10px' } }, actions) : null
        );
      }

      load(listBox, () => DY.api.get('/api/queue'), (d) => { items = (d && d.items) || []; draw(); }, 4);
    }
  };
})();
