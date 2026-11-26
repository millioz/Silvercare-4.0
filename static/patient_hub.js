/* SilverCare CLINIC — patient page: help, weekly summary, messages, symptom diary, questions, refills, report for doctor */
(function () {
  const $ = id => document.getElementById(id);
  const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const API = '/api/clinic/me';
  async function call(url, method = 'GET', body) {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SilverCare' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Something went wrong (' + r.status + ')');
    return d;
  }
  function toast(msg, err, html) {
    const t = $('pcToast'); t.hidden = false; t.className = 'ct-toast' + (err ? ' err' : ''); t.innerHTML = html || E(msg);
    if (!html) setTimeout(() => { t.hidden = true; }, 6000);
  }
  const fmt = s => String(s || '').replace('T', ' ').slice(0, 16);
  const SEV = ['', '1 – very mild', '2 – mild', '3 – moderate', '4 – strong', '5 – severe'];
  let draft = { msg: '' };

  async function render() {
    const keep = document.activeElement && document.activeElement.name === 'body' ? document.activeElement.value : null;
    const [ins, msgs, notes, appts, syms, qs, refills, meds, shares, clin] = await Promise.all([
      call(API + '/insights'), call(API + '/messages'), call(API + '/notes'), call(API + '/appointments'), call(API + '/symptoms'),
      call(API + '/questions'), call(API + '/refills'), call('/api/medications'), call(API + '/shares'), call(API + '/clinical')]);
    const activeMeds = meds.filter(m => m.active);
    let h = '';
    h += '<div class="pc-card"><div class="pc-help"><button class="pc-big" data-act="sos">🆘 I need help now</button><button class="pc-big alt" data-act="callme">📞 Please call me</button></div><div class="ct-small" style="margin-top:8px">Pressing a button alerts your care team immediately.</div></div>';
    h += '<div class="pc-card"><h2>My week</h2><div class="ct-chips"><span class="ct-chip ok">' + (ins.rate === null ? '—' : ins.rate + '%') + ' confirmed (14 days)</span><span class="ct-chip">🔥 ' + ins.streak_days + ' good days in a row</span></div><p>' + E(ins.message) + '</p>' + ins.good_notes.map(n => '<div class="ct-note good">' + E(n) + '</div>').join('') + '</div>';
    if (appts.length) h += '<div class="pc-card"><h2>Next visits</h2>' + appts.map(a => '<div class="ct-row"><div><strong>' + E(a.title) + '</strong><div class="ct-small">' + fmt(a.starts_at) + ' · ' + E(a.with_name) + ' ' + E(a.location) + '</div></div></div>').join('') + '</div>';
    if (notes.length) h += '<div class="pc-card"><h2>From your care team</h2>' + notes.map(n => '<div class="ct-note">' + E(n.plain_summary).replace(/\n/g, '<br>') + '<div class="ct-small">' + fmt(n.created_at) + ' · ' + E(n.author) + '</div></div>').join('') + '</div>';
    h += '<div class="pc-card"><h2>Messages</h2><div class="chat" id="chat">' + (msgs.length ? msgs.map(m => '<div class="bubble ' + (m.sender_role === 'user' ? 'me' : '') + '">' + E(m.body) + '<small>' + (m.sender_role === 'user' ? 'You' : E(m.sender_name)) + ' · ' + fmt(m.created_at) + '</small></div>').join('') : '<div class="ct-small">No messages yet. Ask your care team anything about your routine.</div>') +
      '</div><form class="ct-form" data-form="msg"><textarea name="body" rows="2" placeholder="Write to your care team…" required></textarea><button class="ct-btn" type="submit">Send message</button></form></div>';
    h += '<div class="pc-card"><h2>How do I feel?</h2><form class="ct-form" data-form="symptom"><label>Which medicine (if you think it is related)<select name="medication_id"><option value="">Not sure / not related</option>' + activeMeds.map(m => '<option value="' + m.id + '">' + E(m.name) + '</option>').join('') + '</select></label>' +
      '<label>How strong is it?<select name="severity">' + [1, 2, 3, 4, 5].map(i => '<option value="' + i + '"' + (i === 2 ? ' selected' : '') + '>' + SEV[i] + '</option>').join('') + '</select></label><label>What do you notice?<textarea name="body" rows="2" required placeholder="e.g. dizzy after the morning pill"></textarea></label><button class="ct-btn" type="submit">Tell my care team</button></form>' +
      syms.slice(0, 5).map(s => '<div class="ct-row"><div>' + E(s.body) + '<div class="ct-small">' + fmt(s.created_at) + ' · severity ' + s.severity + (s.medication ? ' · ' + E(s.medication) : '') + (s.staff_note ? ' · care team: ' + E(s.staff_note) : '') + '</div></div>' + (s.reviewed_at ? '<span class="ct-chip ok">SEEN</span>' : '') + '</div>').join('') + '</div>';
    h += '<div class="pc-card"><h2>Questions for my doctor</h2><form class="ct-form" data-form="question"><input name="question" required placeholder="Write it now so you don’t forget…"><button class="ct-btn" type="submit">Save question</button></form>' +
      qs.map(q => '<div class="ct-row"><div>' + E(q.question) + (q.answer ? '<div class="ct-note good">' + E(q.answer) + '<div class="ct-small">' + E(q.answered_by) + '</div></div>' : '') + '</div>' + (q.answer ? '' : '<button class="ct-btn danger" data-act="delq" data-id="' + q.id + '">Remove</button>') + '</div>').join('') + '</div>';
    h += '<div class="pc-card"><h2>Running low?</h2><form class="ct-form" data-form="refill"><label>Medicine<select name="medication_id" required>' + activeMeds.map(m => '<option value="' + m.id + '">' + E(m.name) + '</option>').join('') + '</select></label><input name="note" placeholder="Note (optional)"><button class="ct-btn" type="submit">Ask for a refill</button></form>' +
      refills.map(r => '<div class="ct-row"><div>' + E(r.med_name) + '<div class="ct-small">' + fmt(r.created_at) + (r.decision_note ? ' · ' + E(r.decision_note) : '') + '</div></div><span class="ct-chip ' + (r.status === 'approved' ? 'ok' : r.status === 'denied' ? 'bad' : 'mid') + '">' + r.status.toUpperCase() + '</span></div>').join('') + '</div>';
    h += '<div class="pc-card"><h2>Bring to my doctor</h2><p class="ct-small">A one-page report of your reminders, side effects and questions. ' + (clin.doctor_name ? 'Doctor on file: ' + E(clin.doctor_name) + '.' : '') + '</p><div class="ct-actions"><a class="ct-btn" target="_blank" href="/my-report">📄 Open printable report</a><button class="ct-btn" data-act="share">🔗 Make a link for my doctor (48 h)</button></div>' +
      shares.filter(s => s.active).map(s => '<div class="ct-row"><div class="ct-small">Link expires ' + fmt(s.expires_at) + ' · opened ' + s.views + '×</div><button class="ct-btn danger" data-act="revoke" data-id="' + s.id + '">Stop sharing</button></div>').join('') + '</div>';
    h += '<div class="pc-card"><h2>Easier to read</h2><div class="ct-actions"><button class="ct-btn" data-act="large">🔍 Bigger text on / off</button><button class="ct-btn" data-act="read">🔊 Read today’s schedule aloud</button></div></div>';
    $('pcRoot').innerHTML = h;
    const c = $('chat'); if (c) c.scrollTop = c.scrollHeight;
    if (keep !== null) { const t = document.querySelector('[data-form=msg] textarea'); if (t) { t.value = keep; t.focus(); } }
  }

  const A = {
    async sos() { if (!confirm('Send an URGENT help request to your care team?')) return; const r = await call(API + '/help', 'POST', { kind: 'sos' }); toast('', false, E(r.text) + (r.contact && r.contact.emergency_phone ? '<br>Your emergency contact: <b>' + E(r.contact.emergency_name) + '</b> ' + E(r.contact.emergency_phone) : '')); },
    async callme() { const r = await call(API + '/help', 'POST', { kind: 'call_me' }); toast(r.text); },
    async delq(b) { await call(API + '/questions/' + b.dataset.id, 'DELETE'); render(); },
    async share() { if (!confirm('Create a read-only link your doctor can open for 48 hours? Anyone with the link can read the report until it expires or you stop sharing.')) return; const r = await call(API + '/share', 'POST', { hours: 48 }); toast('', false, 'Send this link to your doctor (valid until ' + fmt(r.expires_at) + '). Shown once:<div class="ct-sec">' + E(location.origin + r.path) + '</div>'); render(); },
    async revoke(b) { await call('/api/clinic/shares/' + b.dataset.id + '/revoke', 'POST', {}); render(); },
    large() { const on = document.documentElement.classList.toggle('sc-large'); try { localStorage.setItem('sc_large', on ? '1' : '0'); } catch (e) { } },
    async read() {
      if (!('speechSynthesis' in window)) return toast('Your browser cannot read aloud.', true);
      const ev = await call('/api/events'); const today = new Date().toLocaleDateString('en-CA');
      const list = ev.filter(e => e.scheduled_for.slice(0, 10) === today);
      const text = list.length ? 'Your medicines today. ' + list.map(e => 'At ' + e.scheduled_for.slice(11, 16) + ', ' + e.medication_name + '. ' + (e.status === 'taken' ? 'Already confirmed.' : e.status === 'missed' ? 'Window passed.' : 'Waiting.')).join(' ') : 'You have no reminders today.';
      speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    }
  };
  document.addEventListener('click', async ev => {
    const b = ev.target.closest('[data-act]'); if (!b || !A[b.dataset.act]) return;
    try { await A[b.dataset.act](b); } catch (e) { toast(e.message, true); }
  });
  document.addEventListener('submit', async ev => {
    const f = ev.target.closest('[data-form]'); if (!f) return; ev.preventDefault();
    const d = Object.fromEntries(new FormData(f)); const k = f.dataset.form;
    try {
      if (k === 'msg') { const r = await call(API + '/messages', 'POST', d); if (r.urgent) toast(r.urgent_text, true); }
      if (k === 'symptom') { const r = await call(API + '/symptoms', 'POST', d); toast(r.urgent ? r.urgent_text : 'Sent to your care team. Thank you.', !!r.urgent); }
      if (k === 'question') { await call(API + '/questions', 'POST', d); toast('Saved.'); }
      if (k === 'refill') { await call(API + '/refills', 'POST', d); toast('Request sent to your care team.'); }
      render();
    } catch (e) { toast(e.message, true); }
  });
  render().catch(e => { $('pcRoot').innerHTML = '<div class="empty-state">' + E(e.message) + '</div>'; });
  setInterval(() => { if (!document.activeElement || !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) render().catch(() => { }); }, 30000);
})();
