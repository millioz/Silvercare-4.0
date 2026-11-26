/* SilverCare GROWTH — injected on every page (adds files only; no old file is edited).
   1) nav link  2) 1-second live updates (dashboards, chats)  3) /growth (care team) and /growth/me (patient) pages */
(function () {
  if (window.__scGrowth) return; window.__scGrowth = true;
  const $ = id => document.getElementById(id);
  const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  async function call(url, method = 'GET', body) {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SilverCare' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Request failed (' + r.status + ')');
    return d;
  }
  const hm = s => String(s || '').slice(11, 16);
  const fdt = s => String(s || '').replace('T', ' ').slice(0, 16);
  const mm = m => m > 1 ? 'in ' + Math.round(m) + ' min' : m >= -1 ? 'due now' : Math.round(-m) + ' min late';
  const live = m => '<span class="g-live" data-m="' + m + '" data-t0="' + Date.now() + '">' + mm(m) + '</span>';
  const br = s => E(s).replace(/\n/g, '<br>');
  function toast(msg, err) {
    const t = $('gToast'); if (!t) return;
    t.hidden = false; t.className = 'ct-toast' + (err ? ' err' : ''); t.textContent = msg;
    clearTimeout(toast.h); toast.h = setTimeout(() => { t.hidden = true; }, 4500);
  }
  const mode = () => { const r = $('gRoot'); return r ? r.dataset.mode : ''; };
  const typing = () => { const a = document.activeElement; return a && ['INPUT', 'TEXTAREA', 'SELECT'].includes(a.tagName); };

  // remember which staff chat is open (so it can be refreshed live without editing clinic.js)
  const _fetch = window.fetch;
  window.fetch = function (u, o) {
    try { const m = String(u).match(/\/api\/clinic\/messages\/(\d+)(?:\?|$)/); if (m && (!o || !o.method || o.method === 'GET')) window.__gThread = m[1]; } catch (e) { }
    return _fetch.apply(this, arguments);
  };

  // ───────── 1) nav link ─────────
  async function nav() {
    let me; try { me = await (await fetch('/api/me')).json(); } catch (e) { return; }
    if (!me || !me.role) return;
    const top = document.querySelector('.top-right'); if (!top || top.querySelector('[data-g-link]')) return;
    const a = document.createElement('a'); a.className = 'logout-link'; a.dataset.gLink = '1';
    a.href = me.role === 'user' ? '/growth/me' : '/growth'; a.textContent = me.role === 'user' ? 'TODAY' : 'COMMAND';
    top.insertBefore(a, top.querySelector('.logout-link'));
  }

  // ───────── 2) live updates ─────────
  const bub = (m, me, name) => '<div class="bubble ' + (me ? 'me' : '') + '">' + E(m.body) + '<small>' + E(name) + ' · ' + fdt(m.created_at) + '</small></div>';
  async function refreshChats() {
    try {
      const p = $('chat');                                                    // patient hub chat
      if (p && document.querySelector('[data-form=msg]')) {
        const msgs = await call('/api/clinic/me/messages'); const bottom = p.scrollHeight - p.scrollTop - p.clientHeight < 80;
        p.innerHTML = msgs.map(m => bub(m, m.sender_role === 'user', m.sender_role === 'user' ? 'You' : m.sender_name)).join(''); if (bottom) p.scrollTop = p.scrollHeight;
      }
      const s = document.querySelector('#chRoot .chat');                      // staff hub chat
      if (s && window.__gThread && document.querySelector('#chRoot [data-form=send]')) {
        const th = await call('/api/clinic/messages/' + window.__gThread); const bottom = s.scrollHeight - s.scrollTop - s.clientHeight < 80;
        s.innerHTML = th.map(m => bub(m, m.sender_role !== 'user', m.sender_name)).join(''); if (bottom) s.scrollTop = s.scrollHeight;
      }
    } catch (e) { }
  }
  function legacy(ch) {                       // only if the optional realtime_update files are NOT installed
    if (window.__scPulse) return;
    if (ch.ev) {
      if (typeof loadUserDashboard === 'function' && window.SILVERCARE_ROLE === 'user') loadUserDashboard().catch(() => { });
      if (typeof loadPatientMonitor === 'function' && window.SILVERCARE_ROLE === 'staff') { const s = $('monitorPatient'); if (s && s.value) loadPatientMonitor(s.value).catch(() => { }); }
    }
    if (ch.msg) refreshChats();
  }
  function onPulse(ch) { legacy(ch); if (mode() === 'me') meLoad().catch(() => { }); if (mode() === 'staff') stLoad().catch(() => { }); }
  let last = null, busy = false, fails = 0, stopped = false;
  async function pulse() {
    if (busy || stopped || document.hidden) return;
    if (fails > 5 && Math.random() > 0.1) return;
    busy = true;
    try {
      const r = await fetch('/api/growth/pulse', { cache: 'no-store', credentials: 'same-origin' });
      if (r.status === 401 || r.status === 403 || r.status === 404) { stopped = true; return; }
      const d = await r.json(); fails = 0;
      if (last) { const ch = { msg: d.msg !== last.msg, ev: d.ev !== last.ev, other: d.other !== last.other, near: d.nearest !== last.nearest }; if (ch.msg || ch.ev || ch.other || ch.near) onPulse(ch); }
      last = d;
    } catch (e) { fails++; } finally { busy = false; }
  }
  function startPulse() {                      // wait a moment: the optional realtime_update script may load after this one
    setTimeout(() => {
      if (window.__scPulse) window.addEventListener('sc:pulse', e => onPulse(Object.assign({ near: false }, e.detail.changed)));
      else { setInterval(pulse, 1000); document.addEventListener('visibilitychange', () => { if (!document.hidden) pulse(); }); }
    }, 1200);
  }

  // live countdown text + browser alerts
  const notified = new Set();
  function notify(title) {
    try { if ('Notification' in window && Notification.permission === 'granted') new Notification(title); } catch (e) { }
    try { navigator.vibrate && navigator.vibrate([300, 150, 300]); } catch (e) { }
  }
  setInterval(() => {
    document.querySelectorAll('.g-live').forEach(el => { const m = Number(el.dataset.m) - (Date.now() - Number(el.dataset.t0)) / 60000; el.textContent = mm(m); });
    if (mode() === 'me' && ME.today && ME.today.nearest) {
      const n = ME.today.nearest, m = n.minutes_from_now - (Date.now() - ME.t0) / 60000;
      if (m <= 0 && !notified.has(n.id)) { notified.add(n.id); notify('💊 ' + n.medication_name + ' — time to take it'); const h = document.querySelector('.g-hero'); if (h) h.classList.add('g-due'); }
    }
  }, 1000);

  // ───────── 3a) patient page ─────────
  const ME = { today: null, stats: null, chat: [], t0: 0, started: false };
  const SUGG = ['What is my next medicine?', 'What did I take today?', 'How am I doing?', 'နောက်ဆေး ဘယ်အချိန်လဲ'];
  function meSkeleton() {
    $('gRoot').innerHTML = '<div id="gTop"></div><div class="pc-card" id="gAssist"><h2>Ask my helper</h2><div class="ct-small">I answer from your own schedule only. For anything else I will offer to send your question to your care team.</div>' +
      '<div class="chat" id="gChat" style="margin-top:10px"></div><div class="g-tools">' + SUGG.map(q => '<button class="ct-btn" data-q="' + E(q) + '">' + E(q) + '</button>').join('') + '</div>' +
      '<div class="g-ask"><input id="gQ" placeholder="Type your question… / မေးခွန်းရိုက်ပါ" autocomplete="off"><button class="ct-btn" id="gSend">Send</button>' +
      ((window.SpeechRecognition || window.webkitSpeechRecognition) ? '<select id="gLang" class="ct-inline"><option value="en-US">EN</option><option value="my-MM">မြန်မာ</option></select><button class="ct-btn" id="gMic" title="Speak">🎤</button>' : '') + '</div></div>';
    $('gQ').addEventListener('keydown', e => { if (e.key === 'Enter') { const q = $('gQ').value; $('gQ').value = ''; ask(q); } });
    drawChat();
  }
  async function meLoad() {
    const [t, s] = await Promise.all([call('/api/growth/me/today'), call('/api/growth/me/stats')]);
    ME.today = t; ME.stats = s; ME.t0 = Date.now(); drawMe();
  }
  function drawMe() {
    const t = ME.today, s = ME.stats, n = t.nearest, nx = t.next; let hero;
    if (n) hero = '<div class="pc-card g-hero ' + (n.minutes_from_now <= 0 ? 'g-due' : '') + '"><div class="panel-kicker">NEAREST MEDICINE</div><div class="g-big">' + E(n.medication_name) + ' <small>' + E(n.dosage || '') + '</small></div>' +
      '<div class="g-sub">' + hm(n.scheduled_for) + ' · ' + live(n.minutes_from_now) + '</div><div class="g-act"><button class="primary-btn g-take" data-take="' + n.id + '">✓ I took it</button><button class="ct-btn" data-alerts="1">🔔 Alerts</button></div>' +
      '<div class="ct-small" style="margin-top:8px">The box button confirms only this medicine — the one closest to now.</div></div>';
    else if (t.total && t.taken + t.missed === t.total) hero = '<div class="pc-card g-hero"><div class="panel-kicker">ALL DONE</div><div class="g-big">Nothing waiting 🎉</div><div class="ct-small">All of today’s reminders are finished.</div></div>';
    else if (nx) hero = '<div class="pc-card g-hero"><div class="panel-kicker">NEXT MEDICINE</div><div class="g-big">' + E(nx.medication_name) + ' <small>' + E(nx.dosage || '') + '</small></div><div class="g-sub">' + hm(nx.scheduled_for) + ' · ' + live(nx.minutes_from_now) + '</div></div>';
    else hero = '<div class="pc-card g-hero"><div class="panel-kicker">TODAY</div><div class="g-big">No reminders</div><div class="ct-small">Ask your caregiver to add a schedule.</div></div>';
    const dev = t.device;
    const metrics = '<div class="g-metrics"><div class="metric-card"><span class="metric-label">TODAY</span><strong>' + t.taken + '/' + t.total + '</strong><small>confirmed</small></div>' +
      '<div class="metric-card"><span class="metric-label">14 DAYS</span><strong>' + (s.rate === null ? '—' : s.rate + '%') + '</strong><small>confirmed</small></div>' +
      '<div class="metric-card"><span class="metric-label">GOOD DAYS</span><strong>' + s.streak_days + '</strong><small>in a row</small></div>' +
      '<div class="metric-card"><span class="metric-label">MY BOX</span><strong style="font-size:18px">' + (dev.online ? '<span class="live-dot"></span> online' : 'offline') + '</strong><small>' + (dev.last_seen ? 'seen ' + hm(dev.last_seen) : 'never seen') + '</small></div></div>';
    const rows = t.items.map(i => '<div class="event-row ' + (i.is_nearest ? 'g-near' : '') + '"><div class="event-time">' + hm(i.scheduled_for) + '</div><div><div class="event-name">' + E(i.medication_name) + '</div><div class="event-meta">' + E(i.dosage || '') +
      (i.status === 'taken' && i.confirmed_at ? ' · confirmed ' + hm(i.confirmed_at) + (i.confirmation_source === 'esp32_button' ? ' (box button)' : '') : '') + '</div>' +
      i.notes.map(x => '<div class="ct-small">📝 ' + E(x.body) + '</div>').join('') + '</div><span class="status-pill ' + E(i.status) + '">' + E(i.status.toUpperCase()) + '</span>' +
      '<div class="g-act" style="grid-column:2/4;margin:0">' + (i.status === 'pending' && !i.is_nearest ? '<button class="confirm-btn" data-take="' + i.id + '">✓ I took this one</button>' : '') + '<button class="confirm-btn" data-note="' + i.id + '">＋ note</button></div></div>').join('');
    const bars = (s.by_time_of_day || []).map(b => '<div class="bar-col" title="' + b.taken + '/' + b.decided + '"><div class="bar" style="height:' + (b.decided ? Math.max(5, b.rate) : 3) + '%"></div><span class="bar-label">' + E(b.name) + '</span></div>').join('');
    $('gTop').innerHTML = hero + metrics + '<div class="pc-card"><h2>Today’s list</h2><div class="event-list" style="margin-top:12px">' + (rows || '<div class="empty-state">No reminders today.</div>') + '</div></div>' +
      (bars ? '<div class="pc-card"><h2>When I confirm best</h2><div class="weekly-chart" style="height:90px">' + bars + '</div><div class="ct-small">Last 14 days, by time of day.</div></div>' : '');
  }
  function drawChat() {
    const c = $('gChat'); if (!c) return;
    c.innerHTML = ME.chat.length ? ME.chat.map((m, i) => '<div class="bubble ' + (m.me ? 'me' : '') + '">' + br(m.text) +
      (m.me ? '' : '<small>' + (m.ai ? '✨ AI · ' : '') + '<a href="#" data-say="' + i + '">🔊 read</a>' + (m.forward ? ' · <a href="#" data-fwd="' + i + '">send to my care team</a>' : '') + '</small>') + '</div>').join('') : '<div class="ct-small">Try one of the buttons below.</div>';
    c.scrollTop = c.scrollHeight;
  }
  async function ask(q) {
    q = String(q || '').trim(); if (!q) return;
    ME.chat.push({ me: true, text: q }); drawChat();
    try { const r = await call('/api/growth/me/ask', 'POST', { text: q }); ME.chat.push({ text: r.text, ai: r.ai, forward: r.can_forward ? q : '' }); if (r.urgent) toast(r.text, true); }
    catch (e) { ME.chat.push({ text: e.message }); }
    drawChat();
  }
  function say(text) {
    try { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.lang = /[\u1000-\u109F]/.test(text) ? 'my-MM' : 'en-US'; speechSynthesis.speak(u); } catch (e) { toast('Your browser cannot read aloud.', true); }
  }

  // ───────── 3b) care-team page ─────────
  const ST = { cmd: null, open: null, detail: null, ai: '', digest: null };
  function stSkeleton() { $('gRoot').innerHTML = '<div id="gSum"></div><div id="gDigest"></div><div id="gCards" class="ct-two"></div><div id="gDetail"></div>'; }
  async function stLoad() {
    ST.cmd = await call('/api/growth/command'); drawStaff();
    if (ST.open) { ST.detail = await call('/api/growth/patients/' + ST.open + '/detail'); drawDetail(); }
  }
  const boxLine = d => d.online ? '<span class="live-dot"></span> box online' : 'box offline' + (d.last_seen ? ' · last seen ' + fdt(d.last_seen) : ' · never seen');
  function doseLine(p) {
    if (p.nearest) return '💊 <strong>' + E(p.nearest.medication_name) + '</strong> ' + hm(p.nearest.scheduled_for) + ' · ' + live(p.nearest.minutes_from_now);
    if (p.next) return 'Next: ' + E(p.next.medication_name) + ' ' + hm(p.next.scheduled_for);
    return 'No dose waiting';
  }
  function drawStaff() {
    const c = ST.cmd, s = c.summary;
    $('gSum').innerHTML = '<div class="g-metrics"><div class="metric-card"><span class="metric-label">PATIENTS</span><strong>' + s.patients + '</strong></div><div class="metric-card highlight-card"><span class="metric-label">NEED ACTION</span><strong>' + s.act + '</strong></div>' +
      '<div class="metric-card"><span class="metric-label">DOSES DUE NOW</span><strong>' + s.due_now + '</strong></div><div class="metric-card"><span class="metric-label">BOXES OFFLINE</span><strong>' + s.offline + '</strong></div></div>' +
      '<div class="g-tools"><button class="ct-btn" data-digest="1">✨ Hand-over: who to check first' + (c.ai ? '' : ' (rules)') + '</button><a class="ct-btn" href="/clinic-hub">Clinic hub</a><a class="ct-btn" href="/">Dashboard</a></div>';
    $('gDigest').innerHTML = ST.digest ? '<div class="g-ai">' + br(ST.digest.text) + '<div class="g-sm">' + E(ST.digest.note) + '</div></div>' : '';
    $('gCards').innerHTML = c.patients.length ? c.patients.map(p => '<div class="pc-card"><div class="ct-row"><strong>' + E(p.name) + '</strong><span class="ct-chip ' + E(p.level) + '">' + E(p.level.toUpperCase()) + '</span></div>' +
      (p.reasons.length ? '<ul class="g-reasons">' + p.reasons.slice(0, 4).map(r => '<li>' + E(r) + '</li>').join('') + '</ul>' : '<div class="ct-small">Nothing urgent.</div>') +
      '<div class="g-prog"><i style="width:' + (p.total ? Math.round(p.taken / p.total * 100) : 0) + '%"></i></div><div class="ct-small">Today ' + p.taken + '/' + p.total + ' confirmed' + (p.missed ? ' · ' + p.missed + ' missed' : '') + '</div>' +
      '<div class="g-line">' + doseLine(p) + '</div><div class="ct-small" style="margin-top:6px">' + boxLine(p.device) + '</div><div class="g-act"><button class="ct-btn" data-open="' + p.id + '">Details</button></div></div>').join('') : '<div class="empty-state">No patients yet.</div>';
  }
  function drawDetail() {
    const box = $('gDetail'); if (!ST.open || !ST.detail) { box.innerHTML = ''; return; }
    const d = ST.detail, a = d.analysis, t = d.today;
    const chips = '<div class="ct-chips"><span class="ct-chip ' + (a.rate === null ? '' : a.rate >= 80 ? 'ok' : 'mid') + '">' + (a.rate === null ? '—' : a.rate + '%') + ' confirmed (14d)</span><span class="ct-chip">🔥 ' + a.streak_days + ' good days</span>' +
      (a.median_confirm_delay_min !== null ? '<span class="ct-chip">median delay ' + a.median_confirm_delay_min + ' min</span>' : '') + '<span class="ct-chip ' + (d.device.online ? 'ok' : 'bad') + '">box ' + (d.device.online ? 'online' : 'offline') + '</span></div>';
    const bars = (a.by_time_of_day || []).map(b => '<div class="bar-col" title="' + b.taken + '/' + b.decided + '"><div class="bar" style="height:' + (b.decided ? Math.max(5, b.rate) : 3) + '%"></div><span class="bar-label">' + E(b.name) + '</span></div>').join('');
    const rows = t.items.map(i => '<div class="event-row ' + (i.is_nearest ? 'g-near' : '') + '"><div class="event-time">' + hm(i.scheduled_for) + '</div><div><div class="event-name">' + E(i.medication_name) + '</div><div class="event-meta">' + E(i.dosage || '') +
      (i.confirmed_at ? ' · confirmed ' + hm(i.confirmed_at) + (i.confirmation_source === 'esp32_button' ? ' (box)' : '') : '') + '</div>' + i.notes.map(x => '<div class="ct-small">📝 ' + E(x.author) + ': ' + E(x.body) + '</div>').join('') + '</div>' +
      '<span class="status-pill ' + E(i.status) + '">' + E(i.status.toUpperCase()) + '</span><button class="confirm-btn" data-note="' + i.id + '">＋ note</button></div>').join('');
    const log = d.device_log.length ? '<div class="table-wrap"><table class="g-log"><tr><th>TIME</th><th>EVENT</th><th>DETAIL</th></tr>' + d.device_log.map(l => '<tr><td>' + fdt(l.at) + '</td><td>' + E(l.kind) + '</td><td>' + E(l.detail) + '</td></tr>').join('') + '</table></div>' : '<div class="ct-small">No box activity yet.</div>';
    box.innerHTML = '<div class="pc-card"><div class="ct-row"><h2>' + E(d.name) + '</h2><button class="ct-btn" data-close="1">Close</button></div>' + chips + '<p style="margin-top:10px">' + E(d.brief) + '</p>' +
      '<div class="g-tools"><button class="ct-btn" data-aibrief="' + ST.open + '">✨ Draft clinician summary</button></div>' + (ST.ai ? '<div class="g-ai">' + br(ST.ai.text) + '<div class="g-sm">' + E(ST.ai.note) + '</div></div>' : '') +
      (a.notes || []).map(n => '<div class="ct-note ' + (n.level === 'warn' ? 'warn' : n.level === 'good' ? 'good' : '') + '">' + E(n.text) + '</div>').join('') +
      (bars ? '<div class="g-sec">CONFIRMED BY TIME OF DAY (14 DAYS)</div><div class="weekly-chart" style="height:80px">' + bars + '</div>' : '') +
      '<div class="g-sec">TODAY</div><div class="event-list" style="margin-top:8px">' + (rows || '<div class="empty-state">No reminders today.</div>') + '</div><div class="g-sec">BOX ACTIVITY</div>' + log + '</div>';
  }

  // ───────── clicks ─────────
  document.addEventListener('click', async ev => {
    const el = ev.target.closest('[data-take],[data-note],[data-q],[data-say],[data-fwd],[data-alerts],[data-open],[data-close],[data-digest],[data-aibrief],#gSend,#gMic'); if (!el || !$('gRoot')) return;
    if (el.tagName === 'A') ev.preventDefault();
    try {
      if (el.dataset.take) { await call('/api/events/' + el.dataset.take + '/confirm', 'POST', {}); toast('Saved ✓'); await (mode() === 'me' ? meLoad() : stLoad()); }
      else if (el.dataset.note) { const b = prompt('Short note about this dose (optional detail, e.g. felt dizzy):'); if (b) { await call('/api/growth/notes', 'POST', { event_id: Number(el.dataset.note), body: b }); toast('Note saved.'); await (mode() === 'me' ? meLoad() : stLoad()); } }
      else if (el.dataset.q) ask(el.dataset.q);
      else if (el.id === 'gSend') { const q = $('gQ').value; $('gQ').value = ''; ask(q); }
      else if (el.id === 'gMic') { const SR = window.SpeechRecognition || window.webkitSpeechRecognition, r = new SR(); r.lang = $('gLang').value; r.onresult = e => ask(e.results[0][0].transcript); r.start(); }
      else if (el.dataset.say) say(ME.chat[Number(el.dataset.say)].text);
      else if (el.dataset.fwd) { await call('/api/growth/me/forward', 'POST', { text: ME.chat[Number(el.dataset.fwd)].forward }); toast('Sent to your care team.'); }
      else if (el.dataset.alerts) { if (!('Notification' in window)) return toast('This browser has no alerts.', true); const p = await Notification.requestPermission(); toast(p === 'granted' ? 'Alerts on for this page.' : 'Alerts are blocked in browser settings.', p !== 'granted'); }
      else if (el.dataset.open) { ST.open = el.dataset.open; ST.ai = ''; ST.detail = await call('/api/growth/patients/' + ST.open + '/detail'); drawDetail(); $('gDetail').scrollIntoView({ behavior: 'smooth' }); }
      else if (el.dataset.close) { ST.open = null; drawDetail(); }
      else if (el.dataset.digest) { el.disabled = true; ST.digest = await call('/api/growth/ai/digest', 'POST', {}); drawStaff(); }
      else if (el.dataset.aibrief) { el.disabled = true; ST.ai = await call('/api/growth/patients/' + el.dataset.aibrief + '/ai-brief', 'POST', {}); drawDetail(); }
    } catch (e) { toast(e.message, true); }
  });

  // ───────── start ─────────
  nav(); startPulse();
  if (mode() === 'me') { meSkeleton(); meLoad().catch(e => { $('gTop').innerHTML = '<div class="empty-state">' + E(e.message) + '</div>'; }); setInterval(() => { if (!typing()) meLoad().catch(() => { }); }, 30000); }
  if (mode() === 'staff') { stSkeleton(); stLoad().catch(e => { $('gRoot').innerHTML = '<div class="empty-state">' + E(e.message) + '</div>'; }); setInterval(() => stLoad().catch(() => { }), 30000); }
})();
