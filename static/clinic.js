/* SilverCare CLINIC — staff hub: triage, messages, symptoms, refills, patient file */
(function () {
  const $ = id => document.getElementById(id);
  const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const API = '/api/clinic';
  async function call(url, method = 'GET', body) {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SilverCare' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Request failed (' + r.status + ')');
    return d;
  }
  function toast(msg, err, html) {
    const t = $('chToast'); t.hidden = false; t.className = 'ct-toast' + (err ? ' err' : ''); t.innerHTML = html || E(msg);
    if (!html) setTimeout(() => { t.hidden = true; }, 5000);
  }
  const fmt = s => String(s || '').replace('T', ' ').slice(0, 16);
  const TABS = [['triage', 'Triage'], ['messages', 'Messages'], ['symptoms', 'Symptoms'], ['refills', 'Refills'], ['patient', 'Patient file']];
  let tab = (location.hash || '#triage').slice(1); if (!TABS.some(t => t[0] === tab)) tab = 'triage';
  let pid = null, msgPid = null, timer = null, users = [];

  function drawTabs(badges = {}) {
    $('chTabs').innerHTML = TABS.map(([k, l]) => '<button data-tab="' + k + '" class="' + (k === tab ? 'on' : '') + '">' + l + (badges[k] ? '<span class="ct-badge">' + badges[k] + '</span>' : '') + '</button>').join('');
  }
  async function refreshBadges() {
    try { const b = await call(API + '/badge'); drawTabs({ triage: b.open_help, messages: b.unread_messages, symptoms: b.flagged_symptoms, refills: b.pending_refills }); } catch (e) { drawTabs(); }
  }
  async function show(k) {
    tab = k; location.hash = k; clearInterval(timer); drawTabs();
    $('chRoot').innerHTML = '<div class="loading-line">Loading…</div>';
    try { await L[k](); } catch (e) { $('chRoot').innerHTML = '<div class="empty-state">' + E(e.message) + '</div>'; }
    refreshBadges();
    if (['triage', 'messages', 'symptoms', 'refills'].includes(k)) timer = setInterval(() => { if (!document.activeElement || !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) L[k]().catch(() => { }); refreshBadges(); }, 30000);
  }
  async function loadUsers() { users = (await call('/api/plus/users')).filter(u => u.role === 'user'); if (!pid && users.length) pid = users[0].id; return users; }
  const pSel = (id, cur) => '<select id="' + id + '" class="ct-inline" style="width:100%">' + users.map(u => '<option value="' + u.id + '"' + (u.id == cur ? ' selected' : '') + '>' + E(u.name) + '</option>').join('') + '</select>';

  const L = {
    // ───────── triage ─────────
    async triage() {
      const [board, help] = await Promise.all([call(API + '/cohort'), call(API + '/help')]);
      let h = '<div class="ct-block"><h3>🆘 Help requests</h3>' + (help.length ? help.map(x =>
        '<div class="ct-row"><div><strong>' + E(x.patient) + '</strong> <span class="ct-chip bad">' + E(x.kind.replace('_', ' ')) + '</span><div class="ct-small">' + fmt(x.created_at) + (x.note ? ' · ' + E(x.note) : '') +
        (x.emergency_phone ? ' · contact: ' + E(x.emergency_name) + ' <a href="tel:' + E(x.emergency_phone) + '">' + E(x.emergency_phone) + '</a>' : '') + '</div></div>' +
        '<button class="ct-btn" data-act="resolve" data-id="' + x.id + '">Mark handled</button></div>').join('') : '<div class="ct-small">No open help requests.</div>') + '</div>';
      h += '<div class="ct-block"><h3>Who needs a check-in? <span class="ct-small">(ranked by simple counted rules, last 14 days)</span></h3>' + (board.length ? board.map(p =>
        '<div class="ct-row"><div><strong>' + E(p.name) + '</strong> <span class="ct-chip ' + p.priority + '">' + p.priority.toUpperCase() + '</span>' +
        '<div class="ct-small">' + (p.reasons.length ? p.reasons.map(E).join(' · ') : 'Nothing needs attention.') + '</div></div>' +
        '<div class="ct-actions"><button class="ct-btn" data-act="file" data-id="' + p.id + '">Open file</button><button class="ct-btn" data-act="msg" data-id="' + p.id + '">Message</button></div></div>').join('') : '<div class="ct-small">No patients yet.</div>') + '</div>';
      $('chRoot').innerHTML = h;
    },

    // ───────── messages ─────────
    async messages() {
      const inbox = await call(API + '/messages/inbox');
      let h = '<div class="ct-block"><h3>Conversations</h3>' + inbox.map(i =>
        '<div class="ct-row"><div><strong>' + E(i.name) + '</strong>' + (i.unread ? ' <span class="ct-badge">' + i.unread + '</span>' : '') +
        '<div class="ct-small">' + E((i.last_body || 'No messages yet').slice(0, 70)) + '</div></div><button class="ct-btn" data-act="thread" data-id="' + i.id + '">Open</button></div>').join('') + '</div>';
      if (msgPid) {
        const th = await call(API + '/messages/' + msgPid); const who = inbox.find(i => i.id == msgPid);
        h += '<div class="ct-block"><h3>Chat with ' + E(who ? who.name : '') + '</h3><div class="chat">' + (th.length ? th.map(m =>
          '<div class="bubble ' + (m.sender_role === 'user' ? '' : 'me') + '">' + E(m.body) + '<small>' + E(m.sender_name) + ' · ' + fmt(m.created_at) + '</small></div>').join('') : '<div class="ct-small">No messages yet.</div>') +
          '</div><form class="ct-form" data-form="send"><textarea name="body" rows="2" placeholder="Write a message (don’t give dose-change advice here)…" required></textarea><button class="ct-btn" type="submit">Send</button></form></div>';
      }
      $('chRoot').innerHTML = h;
      const c = document.querySelector('.chat'); if (c) c.scrollTop = c.scrollHeight;
    },

    // ───────── symptoms ─────────
    async symptoms() {
      const rows = await call(API + '/symptoms');
      $('chRoot').innerHTML = '<div class="ct-block"><h3>Side-effect & symptom reports</h3>' + (rows.length ? rows.map(s =>
        '<div class="ct-row"><div><strong>' + E(s.patient) + '</strong> <span class="ct-chip ' + (s.severity >= 4 ? 'bad' : 'mid') + '">severity ' + s.severity + '/5</span>' + (s.flagged ? ' <span class="ct-chip bad">FLAGGED</span>' : '') +
        '<div>' + E(s.body) + '</div><div class="ct-small">' + fmt(s.created_at) + (s.medication ? ' · ' + E(s.medication) : '') + (s.reviewed_at ? ' · reviewed by ' + E(s.reviewed_by) + (s.staff_note ? ': “' + E(s.staff_note) + '”' : '') : '') + '</div></div>' +
        (s.reviewed_at ? '<span class="ct-chip ok">REVIEWED</span>' : '<button class="ct-btn" data-act="review" data-id="' + s.id + '">Mark reviewed</button>') + '</div>').join('') : '<div class="ct-small">No reports yet.</div>') + '</div>';
    },

    // ───────── refills ─────────
    async refills() {
      const rows = await call(API + '/refills?status=pending');
      $('chRoot').innerHTML = '<div class="ct-block"><h3>Refill requests waiting</h3>' + (rows.length ? rows.map(r =>
        '<div class="ct-row"><div><strong>' + E(r.patient) + '</strong> — ' + E(r.med_name) + '<div class="ct-small">' + fmt(r.created_at) + (r.note ? ' · “' + E(r.note) + '”' : '') + '</div></div>' +
        '<div class="ct-actions"><button class="ct-btn" data-act="approve" data-id="' + r.id + '">Approve</button><button class="ct-btn danger" data-act="deny" data-id="' + r.id + '">Deny</button></div></div>').join('') : '<div class="ct-small">No pending requests.</div>') + '</div>';
    },

    // ───────── patient file ─────────
    async patient() {
      await loadUsers();
      if (!users.length) { $('chRoot').innerHTML = '<div class="empty-state">No patients yet.</div>'; return; }
      if (!users.some(u => u.id == pid)) pid = users[0].id;
      const [prof, scan, ins, notes, qs, appts, shares, ai] = await Promise.all([
        call(API + '/patients/' + pid + '/clinical'), call(API + '/patients/' + pid + '/safety-scan'), call(API + '/patients/' + pid + '/insights'),
        call(API + '/patients/' + pid + '/notes'), call(API + '/patients/' + pid + '/questions'), call(API + '/appointments?user_id=' + pid),
        call(API + '/patients/' + pid + '/shares'), call(API + '/ai/status')]);
      let h = '<div class="ct-block">' + pSel('pfSel', pid) + '<div class="ct-actions" style="margin-top:10px"><a class="ct-btn" target="_blank" href="/report/' + pid + '">📄 Printable report</a>' +
        '<button class="ct-btn" data-act="share">🔗 Link for outside doctor</button><button class="ct-btn" data-act="brief">✨ ' + (ai.available ? 'AI' : 'Quick') + ' summary</button></div><div id="briefBox"></div></div>';
      h += '<div class="ct-two"><div class="ct-block"><h3>Pattern insights (30 days)</h3><div class="ct-chips"><span class="ct-chip ok">' + (ins.rate === null ? '—' : ins.rate + '%') + ' confirmed</span><span class="ct-chip">' + ins.taken + '/' + ins.decided + ' decided</span><span class="ct-chip">streak ' + ins.streak_days + 'd</span>' +
        (ins.median_confirm_delay_min !== null ? '<span class="ct-chip">median delay ' + ins.median_confirm_delay_min + ' min</span>' : '') + '</div>' +
        ins.by_time_of_day.map(b => '<div class="ct-small">' + b.name + ': ' + b.taken + '/' + b.decided + ' (' + b.rate + '%)</div>').join('') +
        (ins.notes.length ? ins.notes.map(n => '<div class="ct-note ' + n.level + '">' + E(n.text) + '</div>').join('') : '') + '<div class="ct-small" style="margin-top:8px">' + E(ins.disclaimer) + '</div></div>' +
        '<div class="ct-block"><h3>Safety scan</h3>' + scan.map(s => '<div class="ct-note ' + (s.level === 'danger' ? 'danger' : s.level === 'warn' ? 'warn' : '') + '">' + E(s.text) + '</div>').join('') + '</div></div>';
      h += '<div class="ct-block"><h3>Doctor, allergies &amp; conditions</h3><form class="ct-form" data-form="clinical"><label>Doctor<input name="doctor_name" value="' + E(prof.doctor_name) + '"></label><label>Doctor contact<input name="doctor_contact" value="' + E(prof.doctor_contact) + '"></label><label>Pharmacy<input name="pharmacy" value="' + E(prof.pharmacy) + '"></label>' +
        '<label>Allergies (comma separated)<input name="allergies" value="' + E(prof.allergies) + '"></label><label>Conditions<input name="conditions" value="' + E(prof.conditions) + '"></label><button class="ct-btn" type="submit">Save</button></form></div>';
      h += '<div class="ct-block"><h3>Visit notes</h3><form class="ct-form" data-form="note"><label>Internal note (staff only)<textarea name="internal_note" rows="3" id="noteInternal"></textarea></label>' +
        '<button type="button" class="ct-btn" data-act="plain">✨ ' + (ai.available ? 'AI-draft' : 'Draft') + ' plain-language version</button>' +
        '<label>Plain-language summary for the patient (they will see this)<textarea name="plain_summary" rows="4" id="notePlain" placeholder="What to remember, in simple words…"></textarea></label><div id="plainNote" class="ct-small"></div><button class="ct-btn" type="submit">Save note</button></form>' +
        notes.map(n => '<div class="ct-row"><div><div class="ct-small">' + fmt(n.created_at) + ' · ' + E(n.author) + '</div>' + (n.internal_note ? '<div>🔒 ' + E(n.internal_note) + '</div>' : '') + (n.plain_summary ? '<div>👤 ' + E(n.plain_summary).replace(/\n/g, '<br>') + '</div>' : '') + '</div><button class="ct-btn danger" data-act="delnote" data-id="' + n.id + '">Delete</button></div>').join('') + '</div>';
      h += '<div class="ct-block"><h3>Patient’s questions</h3>' + (qs.length ? qs.map(q => '<div class="ct-row"><div>' + E(q.question) + (q.answer ? '<div class="ct-note good">' + E(q.answer) + ' — ' + E(q.answered_by) + '</div>' : '') + '</div>' + (q.answer ? '' : '<button class="ct-btn" data-act="answer" data-id="' + q.id + '">Answer</button>') + '</div>').join('') : '<div class="ct-small">No questions.</div>') + '</div>';
      h += '<div class="ct-block"><h3>Appointments</h3><form class="ct-form" data-form="appt"><label>Title<input name="title" required placeholder="e.g. Blood pressure check"></label><label>With<input name="with_name" placeholder="Doctor / clinic"></label><label>When<input type="datetime-local" name="starts_at" required></label><label>Place<input name="location"></label><button class="ct-btn" type="submit">Add appointment</button></form>' +
        appts.map(a => '<div class="ct-row"><div><strong>' + E(a.title) + '</strong> <span class="ct-chip">' + E(a.status) + '</span><div class="ct-small">' + fmt(a.starts_at) + ' · ' + E(a.with_name) + ' ' + E(a.location) + '</div></div><div class="ct-actions">' +
          (a.status === 'scheduled' ? '<button class="ct-btn" data-act="adone" data-id="' + a.id + '">Done</button><button class="ct-btn" data-act="acancel" data-id="' + a.id + '">Cancel</button>' : '') + '<button class="ct-btn danger" data-act="adel" data-id="' + a.id + '">Delete</button></div></div>').join('') + '</div>';
      h += '<div class="ct-block"><h3>Share links</h3>' + (shares.length ? shares.map(s => '<div class="ct-row"><div class="ct-small">' + fmt(s.created_at) + ' by ' + E(s.created_by) + ' · expires ' + fmt(s.expires_at) + ' · ' + s.views + ' views ' + (s.active ? '<span class="ct-chip ok">active</span>' : '<span class="ct-chip">inactive</span>') + '</div>' + (s.active ? '<button class="ct-btn danger" data-act="revoke" data-id="' + s.id + '">Revoke</button>' : '') + '</div>').join('') : '<div class="ct-small">No links yet.</div>') + '</div>';
      $('chRoot').innerHTML = h;
    }
  };

  // ───────── actions ─────────
  const again = () => show(tab);
  const A = {
    async resolve(b) { await call(API + '/help/' + b.dataset.id + '/resolve', 'POST', {}); again(); },
    file(b) { pid = b.dataset.id; show('patient'); },
    msg(b) { msgPid = b.dataset.id; show('messages'); },
    thread(b) { msgPid = b.dataset.id; again(); },
    async review(b) { const n = prompt('Note (optional)'); if (n === null) return; await call(API + '/symptoms/' + b.dataset.id + '/review', 'POST', { note: n }); again(); },
    async approve(b) { const q = prompt('Units received to add to the stock estimate (leave 0 to skip):', '0'); if (q === null) return; const n = prompt('Note for the patient (optional)') || ''; await call(API + '/refills/' + b.dataset.id + '/decide', 'POST', { decision: 'approved', add_quantity: q, note: n }); again(); },
    async deny(b) { const n = prompt('Reason for the patient (e.g. "please call the clinic")'); if (n === null) return; await call(API + '/refills/' + b.dataset.id + '/decide', 'POST', { decision: 'denied', note: n }); again(); },
    async share() {
      const hrs = prompt('Link valid for how many hours? (1–336)', '48'); if (!hrs) return;
      const r = await call(API + '/patients/' + pid + '/share', 'POST', { hours: Number(hrs) }); const url = location.origin + r.path;
      toast('', false, 'Read-only link for an outside doctor (valid until ' + fmt(r.expires_at) + '). Shown once:<div class="ct-sec">' + E(url) + '</div>'); again();
    },
    async revoke(b) { if (!confirm('Revoke this link now?')) return; await call(API + '/shares/' + b.dataset.id + '/revoke', 'POST', {}); again(); },
    async brief() {
      if (!confirm('Create a summary of the confirmation data?\n(If AI is enabled, only de-identified numbers are sent. The result is a draft to review.)')) return;
      $('briefBox').innerHTML = '<div class="ct-small">Working…</div>';
      const r = await call(API + '/ai/brief', 'POST', { user_id: Number(pid) });
      $('briefBox').innerHTML = '<div class="ct-note good">' + E(r.text) + '<div class="ct-small">' + E(r.note) + '</div></div>';
    },
    async plain() {
      const t = $('noteInternal').value.trim(); if (!t) return toast('Write the internal note first.', true);
      if (!confirm('Draft a simple-language version?\n(If AI is enabled, the note is sent after names, emails and phone numbers are stripped. Avoid other identifying details.)')) return;
      const r = await call(API + '/ai/plain-language', 'POST', { text: t, user_id: Number(pid) });
      $('notePlain').value = r.text; $('plainNote').textContent = r.note;
    },
    async delnote(b) { if (!confirm('Delete this note?')) return; await call(API + '/notes/' + b.dataset.id, 'DELETE'); again(); },
    async answer(b) { const a = prompt('Your answer to the patient'); if (!a) return; await call(API + '/questions/' + b.dataset.id + '/answer', 'POST', { answer: a }); again(); },
    async adone(b) { await call(API + '/appointments/' + b.dataset.id, 'PATCH', { status: 'done' }); again(); },
    async acancel(b) { await call(API + '/appointments/' + b.dataset.id, 'PATCH', { status: 'cancelled' }); again(); },
    async adel(b) { if (!confirm('Delete this appointment?')) return; await call(API + '/appointments/' + b.dataset.id, 'DELETE'); again(); }
  };
  document.addEventListener('click', async ev => {
    const t = ev.target.closest('[data-tab]'); if (t) return show(t.dataset.tab);
    const b = ev.target.closest('[data-act]'); if (!b || !A[b.dataset.act]) return;
    try { await A[b.dataset.act](b); } catch (e) { toast(e.message, true); }
  });
  document.addEventListener('change', ev => { if (ev.target.id === 'pfSel') { pid = ev.target.value; show('patient'); } });
  document.addEventListener('submit', async ev => {
    const f = ev.target.closest('[data-form]'); if (!f) return; ev.preventDefault();
    const d = Object.fromEntries(new FormData(f));
    try {
      if (f.dataset.form === 'send') { await call(API + '/messages/' + msgPid, 'POST', d); again(); }
      if (f.dataset.form === 'clinical') { await call(API + '/patients/' + pid + '/clinical', 'PUT', d); toast('Saved.'); again(); }
      if (f.dataset.form === 'note') { await call(API + '/patients/' + pid + '/notes', 'POST', d); toast('Note saved.'); again(); }
      if (f.dataset.form === 'appt') { d.user_id = Number(pid); await call(API + '/appointments', 'POST', d); toast('Appointment added.'); again(); }
    } catch (e) { toast(e.message, true); }
  });
  show(tab);
})();
