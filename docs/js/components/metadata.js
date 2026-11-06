(function () {
  'use strict';
  const { h, icon, sectionHead, toast, busy } = DY.ui;

  // src/upload/metadata.py ke same limits
  const TITLE_MAX = 100;
  const DESC_MAX = 5000;        // bytes
  const TAGS_TOTAL_MAX = 500;   // characters (sab tags milake)
  const CATEGORIES = { 1: 'Film & Animation', 2: 'Autos', 10: 'Music', 15: 'Pets & Animals', 17: 'Sports', 19: 'Travel', 20: 'Gaming', 22: 'People & Blogs', 23: 'Comedy', 24: 'Entertainment', 25: 'News & Politics', 26: 'Howto & Style', 27: 'Education', 28: 'Science & Technology' };
  const enc = new TextEncoder();
  const byteLen = (s) => enc.encode(s).length;
  const tagCost = (tags) => tags.reduce((a, t, i) => a + t.length + (t.includes(' ') ? 2 : 0) + (i ? 1 : 0), 0);

  DY.views.metadata = {
    title: 'Metadata Editor',
    render(main) {
      let tags = [];
      const uid = (n) => `md-${n}`;
      const counter = () => h('span', { class: 'counter', 'aria-live': 'polite' });

      const channel = h('select', { id: uid('channel') }, h('option', { value: '' }, 'Channel chuno...'));
      const fileName = h('input', { id: uid('file'), type: 'text', placeholder: 'video_file.mp4 (optional)', autocomplete: 'off' });
      const notes = h('textarea', { id: uid('notes'), rows: 3, placeholder: 'Video kis baare mein hai? 1-2 line likho, AI isse title banayega.', style: { minHeight: '80px' } });
      const language = h('select', { id: uid('lang') }, ['Hindi', 'Hinglish', 'English'].map((l) => h('option', { value: l }, l)));
      const title = h('input', { id: uid('title'), type: 'text', maxlength: 120, placeholder: 'Video ka title', required: true, autocomplete: 'off', 'aria-describedby': uid('title-c') });
      const titleC = counter(); titleC.id = uid('title-c');
      const desc = h('textarea', { id: uid('desc'), rows: 8, placeholder: 'Description...', 'aria-describedby': uid('desc-c') });
      const descC = counter(); descC.id = uid('desc-c');
      const tagInput = h('input', { id: uid('tags'), type: 'text', placeholder: 'Tag likho aur Enter dabao', autocomplete: 'off', 'aria-describedby': uid('tags-c') });
      const tagC = counter(); tagC.id = uid('tags-c');
      const tagList = h('div', { class: 'tag-list', 'aria-label': 'Tags' });
      const category = h('select', { id: uid('cat') }, Object.entries(CATEGORIES).map(([k, v]) => h('option', { value: k, selected: k === '22' }, `${v} (${k})`)));
      const privacy = h('select', { id: uid('privacy') }, [['private', 'Private'], ['unlisted', 'Unlisted'], ['public', 'Public']].map(([k, v]) => h('option', { value: k }, v)));
      const schedule = h('input', { id: uid('sched'), type: 'datetime-local', 'aria-describedby': uid('sched-h') });
      const kids = h('input', { id: uid('kids'), type: 'checkbox' });
      const errBox = h('div', { class: 'callout bad small', role: 'alert', hidden: true });

      function update() {
        const tl = title.value.length;
        titleC.textContent = `${tl} / ${TITLE_MAX}`;
        titleC.className = `counter${tl > TITLE_MAX ? ' over' : tl > TITLE_MAX - 10 ? ' warn' : ''}`;
        title.classList.toggle('input-error', tl > TITLE_MAX || /[<>]/.test(title.value));
        const dl = byteLen(desc.value);
        descC.textContent = `${dl} / ${DESC_MAX} bytes`;
        descC.className = `counter${dl > DESC_MAX ? ' over' : dl > DESC_MAX - 300 ? ' warn' : ''}`;
        desc.classList.toggle('input-error', dl > DESC_MAX || /[<>]/.test(desc.value));
        const tc = tagCost(tags);
        tagC.textContent = `${tags.length} tags · ${tc} / ${TAGS_TOTAL_MAX}`;
        tagC.className = `counter${tc > TAGS_TOTAL_MAX ? ' over' : ''}`;
        if (schedule.value) { privacy.value = 'private'; privacy.disabled = true; } else privacy.disabled = false;
      }
      function drawTags() {
        tagList.replaceChildren(...tags.map((t, i) => h('span', { class: 'tag' }, t,
          h('button', { type: 'button', 'aria-label': `Tag ${t} hatao`, onclick: () => { tags.splice(i, 1); drawTags(); } }, '×'))));
        update();
      }
      function addTags(raw) {
        raw.split(',').map((t) => t.replace(/[<>]/g, '').trim()).filter(Boolean).forEach((t) => {
          if (!tags.some((x) => x.toLowerCase() === t.toLowerCase())) tags.push(t);
        });
        drawTags();
      }
      tagInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTags(tagInput.value); tagInput.value = ''; }
        else if (e.key === 'Backspace' && !tagInput.value && tags.length) { tags.pop(); drawTags(); }
      });
      tagInput.addEventListener('blur', () => { if (tagInput.value.trim()) { addTags(tagInput.value); tagInput.value = ''; } });
      [title, desc, schedule].forEach((el) => el.addEventListener('input', update));

      function validate() {
        const e = [];
        if (!title.value.trim()) e.push('Title khaali hai.');
        if (title.value.length > TITLE_MAX) e.push(`Title ${TITLE_MAX} akshar se lamba hai.`);
        if (byteLen(desc.value) > DESC_MAX) e.push('Description 5000 bytes se lambi hai.');
        if (/[<>]/.test(title.value + desc.value)) e.push('< aur > allowed nahi hain.');
        if (tagCost(tags) > TAGS_TOTAL_MAX) e.push('Tags 500 akshar se zyada hain.');
        if (!channel.value) e.push('Channel chuno.');
        if (schedule.value && new Date(schedule.value).getTime() <= Date.now()) e.push('Schedule time future mein hona chahiye.');
        return e;
      }

      const aiBtn = h('button', { class: 'btn btn-gold', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        if (!notes.value.trim() && !fileName.value.trim()) { toast('Pehle notes ya file name likho.', 'warn'); notes.focus(); return; }
        if ((title.value || desc.value || tags.length) && !(await DY.ui.confirmAction('AI ka result abhi likha hua title, description aur tags badal dega. Theek hai?', 'Haan, badlo'))) return;
        try {
          const opt = channel.selectedOptions[0];
          const r = await DY.api.post('/api/ai/metadata', {
            notes: notes.value.trim(), file_name: fileName.value.trim() || null, language: language.value,
            channel_id: channel.value || null, channel_name: channel.value && opt ? opt.textContent : null
          });
          title.value = String(r.title || '').slice(0, TITLE_MAX);
          desc.value = String(r.description || '');
          tags = []; addTags((r.tags || []).join(','));
          toast(DY.api.isDemo() ? 'Sample AI result (demo mode — Gemini call nahi hua)' : 'Gemini ne bana diya ✓ Ek baar padh lo.', DY.api.isDemo() ? 'warn' : 'ok');
        } catch (err) { toast(err.message, 'err'); }
      }) }, icon('spark'), ' AI se banao (Gemini)');
      aiBtn.querySelector('svg').style.width = '18px';

      const saveBtn = h('button', { class: 'btn btn-gold', type: 'submit' }, 'Save karo');
      const form = h('form', { class: 'stack', novalidate: true, onsubmit: (e) => {
        e.preventDefault();
        const errs = validate();
        errBox.hidden = !errs.length;
        errBox.replaceChildren(...errs.map((x) => h('div', null, '• ', x)));
        if (errs.length) { errBox.focus(); return; }
        busy(saveBtn, async () => {
          try {
            await DY.api.post('/api/metadata', {
              channel_id: channel.value, file_name: fileName.value.trim() || null,
              title: title.value.trim(), description: desc.value, tags, category_id: category.value,
              privacy_status: schedule.value ? 'private' : privacy.value,
              publish_at: schedule.value ? new Date(schedule.value).toISOString() : null,
              made_for_kids: kids.checked
            });
            toast(`Save ho gaya ✓${DY.api.isDemo() ? ' (demo — kuch save nahi hua)' : ''}`, 'ok');
          } catch (err) { toast(err.message, 'err'); }
        });
      } },
        h('div', { class: 'card stack' },
          h('div', { class: 'card-head' }, h('h3', null, '1. Video aur AI'), h('span', { class: 'chip chip-gold' }, 'Gemini')),
          h('div', { class: 'form-grid two' },
            h('div', { class: 'field' }, h('label', { for: uid('channel') }, 'Channel'), channel),
            h('div', { class: 'field' }, h('label', { for: uid('file') }, 'File name'), fileName),
            h('div', { class: 'field span-2' }, h('label', { for: uid('notes') }, 'Video ke notes'), notes),
            h('div', { class: 'field' }, h('label', { for: uid('lang') }, 'Bhasha'), language),
            h('div', { class: 'field', style: { justifyContent: 'flex-end' } }, aiBtn)),
          h('p', { class: 'hint' }, 'AI ka result hamesha ek baar khud padh lo. Gemini key sirf backend par rehti hai, is page par nahi.')),
        h('div', { class: 'card stack' },
          h('h3', null, '2. Title, description, tags'),
          h('div', { class: 'field' }, h('div', { class: 'field-row' }, h('label', { for: uid('title') }, 'Title'), titleC), title),
          h('div', { class: 'field' }, h('div', { class: 'field-row' }, h('label', { for: uid('desc') }, 'Description'), descC), desc),
          h('div', { class: 'field' }, h('div', { class: 'field-row' }, h('label', { for: uid('tags') }, 'Tags'), tagC), tagInput, tagList)),
        h('div', { class: 'card stack' },
          h('h3', null, '3. Category, privacy, schedule'),
          h('div', { class: 'form-grid two' },
            h('div', { class: 'field' }, h('label', { for: uid('cat') }, 'Category'), category),
            h('div', { class: 'field' }, h('label', { for: uid('privacy') }, 'Privacy'), privacy),
            h('div', { class: 'field' }, h('label', { for: uid('sched') }, 'Schedule (publish time)'), schedule,
              h('span', { class: 'hint', id: uid('sched-h') }, 'Schedule lagane par privacy apne aap Private ho jaati hai (YouTube rule). Time aapke phone ke timezone mein.')),
            h('div', { class: 'field', style: { justifyContent: 'center' } },
              h('label', { style: { display: 'flex', gap: '8px', alignItems: 'center', fontWeight: 600 } }, kids, 'Made for kids'))),
          errBox,
          h('div', { class: 'btn-row' }, saveBtn,
            h('button', { class: 'btn btn-ghost', type: 'button', onclick: async () => {
              if (await DY.ui.confirmAction('Form ki saari likhi cheezein mit jaayengi.', 'Haan, saaf karo')) { form.reset(); tags = []; drawTags(); errBox.hidden = true; }
            } }, 'Saaf karo')))
      );
      errBox.tabIndex = -1;

      main.append(sectionHead('Metadata Editor', 'Title 100 akshar, description 5000 bytes, tags 500 akshar — YouTube ki limits'), form);
      update();

      DY.api.get('/api/channels').then((d) => {
        ((d && d.items) || []).filter((c) => c.enabled).forEach((c) => channel.append(h('option', { value: c.id }, c.name)));
      }).catch((e) => toast(`Channels load nahi hue: ${e.message}`, 'err'));
    }
  };
})();
