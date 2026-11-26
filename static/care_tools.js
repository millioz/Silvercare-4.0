/* SilverCare PLUS — Care Tools page (tabs: overview, alerts, patients & meds, accounts, audit, export) */
(function () {
  const ADMIN = window.SC_ROLE === 'admin';
  const API = '/api/plus';
  const $ = id => document.getElementById(id);
  const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  async function call(url, method = 'GET', body) {
    const r = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SilverCare' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Request failed (' + r.status + ')');
    return d;
  }
  function toast(msg, err, html) {
    const t = $('ctToast'); t.hidden = false; t.className = 'ct-toast' + (err ? ' err' : '');
    t.innerHTML = html || E(msg);
    if (!html) setTimeout(() => { t.hidden = true; }, 5000);
  }
  const fmt = s => String(s || '').replace('T', ' ').slice(0, 16);

  const TABS = [['overview', 'Overview'], ['alerts', 'Alerts'], ['patients', 'Patients & meds']]
    .concat(ADMIN ? [['accounts', 'Accounts'], ['audit', 'Audit log']] : []).concat([['export', 'Export']]);
  let tab = (location.hash || '#overview').slice(1);
  if (!TABS.some(t => t[0] === tab)) tab = 'overview';
  let patientId = null, refreshTimer = null, alertDays = 7;

  function drawTabs(badge) {
    $('ctTabs').innerHTML = TABS.map(([k, l]) =>
      '<button data-tab="' + k + '" class="' + (k === tab ? 'on' : '') + '">' + l +
      (k === 'alerts' && badge ? '<span class="ct-badge">' + badge + '</span>' : '') + '</button>').join('');
  }
  async function show(k) {
    tab = k; location.hash = k; drawTabs(); clearInterval(refreshTimer);
    $('ctRoot').innerHTML = '<div class="loading-line">Loading…</div>';
    try { await loaders[k](); } catch (e) { $('ctRoot').innerHTML = '<div class="empty-state">' + E(e.message) + '</div>'; }
    if (k === 'overview' || k === 'alerts') refreshTimer = setInterval(() => loaders[k]().catch(() => { }), 30000);
  }

  // ─────────── loaders ───────────
  const loaders = {
    async overview() {
      const d = await call(API + '/overview');
      const bad = d.patients.reduce((n, p) => n + p.unacked_missed + p.overdue_now, 0);
      drawTabs(bad);
      $('ctRoot').innerHTML = d.patients.length ? '<div class="ct-grid">' + d.patients.map(p => {
        const need = p.overdue_now || p.unacked_missed;
        const dev = p.device_seen_seconds_ago === null ? '<span class="ct-chip">No device yet</span>'
          : p.device_online ? '<span class="ct-chip ok">Device online</span>'
            : '<span class="ct-chip bad">Device offline ' + Math.round(p.device_seen_seconds_ago / 60) + ' min</span>';
        return '<article class="ct-card ' + (need ? 'warn' : '') + '"><h3>' + E(p.name) + (p.active ? '' : ' <span class="ct-chip">disabled</span>') + '</h3><div class="ct-small">' + E(p.email) + '</div>' +
          '<div class="ct-chips"><span class="ct-chip ok">✔ ' + p.today.taken + ' confirmed</span><span class="ct-chip mid">⏳ ' + p.today.pending + ' pending</span><span class="ct-chip bad">✖ ' + p.today.missed + ' missed</span></div>' +
          '<div class="ct-chips">' + dev + (p.low_stock ? '<span class="ct-chip mid">Low stock ×' + p.low_stock + '</span>' : '') +
          (p.overdue_now ? '<span class="ct-chip bad">Overdue now ×' + p.overdue_now + '</span>' : '') +
          (p.unacked_missed ? '<span class="ct-chip bad">Unreviewed missed ×' + p.unacked_missed + '</span>' : '') + '</div>' +
          '<div class="ct-small">7-day confirmation: <strong>' + (p.rate === null ? '—' : p.rate + '%') + '</strong></div>' +
          '<div class="ct-actions" style="margin-top:10px"><button class="ct-btn" data-act="open" data-id="' + p.id + '">Manage</button></div></article>';
      }).join('') + '</div>' : '<div class="empty-state">No patients yet. Create one on the main Care console.</div>';
    },

    async alerts() {
      const days = alertDays;
      const d = await call(API + '/alerts?days=' + days);
      const open = d.missed.filter(m => !m.acked_at);
      drawTabs(open.length + d.overdue.length);
      let h = '<div class="ct-block"><h3>Overdue right now</h3>' + (d.overdue.length ? d.overdue.map(o =>
        '<div class="ct-row"><div><strong>' + E(o.patient) + '</strong> — ' + E(o.medication) + '<div class="ct-small">Due ' + fmt(o.scheduled_for) + ' · ' + o.minutes_overdue + ' min ago · window ' + o.grace_minutes + ' min</div></div><span class="ct-chip mid">PENDING</span></div>').join('')
        : '<div class="ct-small">Nothing overdue.</div>') + '</div>';
      h += '<div class="ct-block"><h3>Low stock</h3>' + (d.low_stock.length ? d.low_stock.map(s =>
        '<div class="ct-row"><div><strong>' + E(s.patient) + '</strong> — ' + E(s.medication) + '<div class="ct-small">≈ ' + s.days_left + ' days left (' + s.remaining + ' units, estimated from confirmations)</div></div><button class="ct-btn" data-act="open" data-id="' + s.user_id + '">Update</button></div>').join('')
        : '<div class="ct-small">No low-stock medications (only tracked where stock was entered).</div>') + '</div>';
      h += '<div class="ct-block"><div class="ct-row"><h3>Missed-window events</h3><select id="alDays" class="ct-inline">' +
        [1, 3, 7, 14, 30].map(n => '<option value="' + n + '"' + (n == days ? ' selected' : '') + '>Last ' + n + ' day' + (n > 1 ? 's' : '') + '</option>').join('') + '</select></div>' +
        (d.missed.length ? d.missed.map(m => '<div class="ct-row"><div><strong>' + E(m.patient) + '</strong> — ' + E(m.medication) + ' ' + E(m.dosage) +
          '<div class="ct-small">Scheduled ' + fmt(m.scheduled_for) + (m.acked_at ? ' · reviewed by ' + E(m.acked_by_name) + (m.note ? ': “' + E(m.note) + '”' : '') : '') + '</div></div>' +
          (m.acked_at ? '<span class="ct-chip ok">REVIEWED</span>' : '<button class="ct-btn" data-act="ack" data-id="' + m.id + '">Mark reviewed</button>') + '</div>').join('')
          : '<div class="ct-small">No missed events in this period.</div>') + '</div>';
      $('ctRoot').innerHTML = h;
    },

    async patients() {
      const users = (await call(API + '/users')).filter(u => u.role === 'user');
      if (!users.length) { $('ctRoot').innerHTML = '<div class="empty-state">No patients yet.</div>'; return; }
      if (!patientId || !users.some(u => u.id == patientId)) patientId = users[0].id;
      const [meds, prof] = await Promise.all([call(API + '/patients/' + patientId + '/medications'), call(API + '/users/' + patientId + '/profile')]);
      let h = '<div class="ct-block"><select id="ptSel" class="ct-inline" style="width:100%">' + users.map(u => '<option value="' + u.id + '"' + (u.id == patientId ? ' selected' : '') + '>' + E(u.name) + (u.active ? '' : ' (disabled)') + '</option>').join('') + '</select></div>';
      h += '<div class="ct-block"><h3>Emergency contact &amp; care notes</h3><form class="ct-form" data-form="profile"><label>Contact name<input name="emergency_name" value="' + E(prof.emergency_name) + '"></label><label>Contact phone<input name="emergency_phone" value="' + E(prof.emergency_phone) + '"></label><label>Care notes (not dosing advice)<textarea name="care_notes" rows="3">' + E(prof.care_notes) + '</textarea></label><button class="ct-btn" type="submit">Save profile</button></form></div>';
      h += '<div class="ct-block"><h3>Medications</h3>' + (meds.length ? meds.map(medCard).join('') : '<div class="ct-small">No medications yet.</div>') + '</div>';
      h += '<div class="ct-block"><h3>Add medication (multiple daily times)</h3><form class="ct-form" data-form="newmed">' +
        '<label>Medication name<input name="name" required></label><label>Dosage / label (as prescribed)<input name="dosage"></label><label>Notes<input name="instructions"></label>' +
        '<label>Reminder times <span class="ct-small">(add one or more)</span><span id="timeInputs"><input type="time" name="t" required></span></label><button type="button" class="ct-btn" data-act="addtime">+ another time</button>' +
        '<label>Confirmation window<select name="grace_minutes"><option>30</option><option selected>60</option><option>90</option><option>120</option></select></label><button class="ct-btn" type="submit">Save medication</button></form></div>';
      $('ctRoot').innerHTML = h;
    },

    async accounts() {
      const users = await call(API + '/users');
      let h = '<div class="ct-block"><h3>All accounts</h3>' + users.map(u => {
        const self = false;
        return '<div class="ct-row"><div><strong>' + E(u.name) + '</strong> <span class="ct-chip">' + E(u.role) + '</span>' + (u.active ? '' : ' <span class="ct-chip bad">disabled</span>') +
          '<div class="ct-small">' + E(u.email) + (u.last_seen ? ' · device seen ' + fmt(u.last_seen) : '') + '</div></div><div class="ct-actions">' +
          '<button class="ct-btn" data-act="toggle" data-id="' + u.id + '" data-on="' + (u.active ? 0 : 1) + '">' + (u.active ? 'Disable' : 'Enable') + '</button>' +
          '<button class="ct-btn" data-act="resetpw" data-id="' + u.id + '">Reset password</button>' +
          (u.role === 'user' ? '<button class="ct-btn" data-act="token" data-id="' + u.id + '">New device token</button>' : '') +
          '<button class="ct-btn danger" data-act="deluser" data-id="' + u.id + '" data-email="' + E(u.email) + '" data-name="' + E(u.name) + '">Delete</button></div></div>';
      }).join('') + '</div>';
      h += '<div class="ct-block"><h3>Create staff or patient account</h3><form class="ct-form" data-form="newuser"><label>Full name<input name="name" required></label><label>Email<input name="email" type="email" required></label><label>Temporary password (8+)<input name="password" type="password" minlength="8" required></label><label>Role<select name="role"><option value="caregiver">Caregiver</option><option value="user">Patient</option><option value="admin">Admin</option></select></label><button class="ct-btn" type="submit">Create account</button></form></div>';
      $('ctRoot').innerHTML = h;
    },

    async audit() {
      const rows = await call(API + '/audit');
      $('ctRoot').innerHTML = '<div class="ct-block"><h3>Recent admin activity</h3>' + (rows.length ? rows.map(r =>
        '<div class="ct-row"><div><strong>' + E(r.action) + '</strong> <span class="ct-small">' + E(r.target) + '</span><div class="ct-small">' + E(r.actor_name) + ' · ' + fmt(r.created_at) + (r.detail ? ' · ' + E(r.detail) : '') + '</div></div></div>').join('') : '<div class="ct-small">No activity yet.</div>') + '</div>';
    },

    async export() {
      const users = (await call(API + '/users')).filter(u => u.role === 'user');
      $('ctRoot').innerHTML = '<div class="ct-block"><h3>Export event history (CSV)</h3><p class="ct-small">Opens in Excel / Google Sheets. Contains personal health-related data — store and share it securely.</p><div class="ct-form"><label>Patient<select id="exUser"><option value="">All patients</option>' +
        users.map(u => '<option value="' + u.id + '">' + E(u.name) + '</option>').join('') + '</select></label><label>Period<select id="exDays"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option><option value="365">1 year</option></select></label><button class="ct-btn" data-act="export">Download CSV</button></div></div>';
    }
  };

  function medCard(m) {
    const st = m.stock;
    return '<div class="ct-card ' + (st && st.low ? 'warn' : '') + '"><h3>' + E(m.name) + (m.active ? '' : ' <span class="ct-chip">paused</span>') + '</h3><div class="ct-small">' + E(m.dosage || '—') + (m.instructions ? ' · ' + E(m.instructions) : '') + '</div>' +
      '<div class="ct-times">' + m.schedules.map(s => '<span class="ct-time ' + (s.active ? '' : 'off') + '">' + E(s.time_local) + ' <button data-act="stime" data-id="' + s.id + '" data-t="' + E(s.time_local) + '">edit</button><button data-act="sflip" data-id="' + s.id + '" data-on="' + (s.active ? 0 : 1) + '">' + (s.active ? 'off' : 'on') + '</button></span>').join('') +
      '<button class="ct-btn" data-act="sadd" data-id="' + m.id + '">+ time</button></div>' +
      '<div class="ct-small">' + (st ? 'Stock ≈ <strong>' + st.remaining + '</strong> units (~' + st.days_left + ' days)' + (st.low ? ' ⚠️ LOW' : '') : 'Stock not tracked') + '</div>' +
      '<div class="ct-actions" style="margin-top:10px"><button class="ct-btn" data-act="stock" data-id="' + m.id + '">Set stock</button><button class="ct-btn" data-act="medit" data-id="' + m.id + '" data-n="' + E(m.name) + '" data-d="' + E(m.dosage) + '" data-i="' + E(m.instructions) + '">Edit</button>' +
      '<button class="ct-btn" data-act="mpause" data-id="' + m.id + '" data-on="' + (m.active ? 0 : 1) + '">' + (m.active ? 'Pause' : 'Resume') + '</button>' +
      (ADMIN ? '<button class="ct-btn danger" data-act="mdel" data-id="' + m.id + '" data-n="' + E(m.name) + '">Delete</button>' : '') + '</div></div>';
  }

  // ─────────── actions ───────────
  const reload = () => show(tab);
  const A = {
    open: b => { patientId = b.dataset.id; show('patients'); },
    async ack(b) { const note = prompt('Optional note (e.g. "called patient, dose taken late")') ; if (note === null) return; await call(API + '/alerts/' + b.dataset.id + '/ack', 'POST', { note }); reload(); },
    async toggle(b) { await call(API + '/users/' + b.dataset.id + '/active', 'POST', { active: b.dataset.on === '1' }); reload(); },
    async resetpw(b) { if (!confirm('Generate a new temporary password for this account?')) return; const r = await call(API + '/users/' + b.dataset.id + '/reset-password', 'POST', {}); toast('', false, 'New temporary password (shown once):<div class="ct-sec">' + E(r.temporary_password) + '</div>'); },
    async token(b) { if (!confirm('Create a NEW device token? The old one stops working — the ESP32 must be re-flashed with the new token.')) return; const r = await call(API + '/users/' + b.dataset.id + '/rotate-token', 'POST', {}); toast('', false, 'New device token (shown once):<div class="ct-sec">' + E(r.device_token) + '</div>'); },
    async deluser(b) { const t = prompt('PERMANENT DELETE of ' + b.dataset.name + ' and ALL linked medications, schedules and history.\nType their email to confirm:\n' + b.dataset.email); if (t === null) return; await call(API + '/users/' + b.dataset.id, 'DELETE', { confirm_email: t }); toast('Account deleted.'); reload(); },
    addtime() { $('timeInputs').insertAdjacentHTML('beforeend', '<input type="time" name="t" style="margin-top:6px">'); },
    async sadd(b) { const t = prompt('New reminder time (24-hour HH:MM)', '20:00'); if (!t) return; await call(API + '/medications/' + b.dataset.id + '/schedules', 'POST', { time: t }); reload(); },
    async stime(b) { const t = prompt('Change time (24-hour HH:MM)', b.dataset.t); if (!t) return; await call(API + '/schedules/' + b.dataset.id, 'PATCH', { time: t }); reload(); },
    async sflip(b) { await call(API + '/schedules/' + b.dataset.id, 'PATCH', { active: b.dataset.on === '1' }); reload(); },
    async stock(b) { const q = prompt('How many pills/units are on hand right now?'); if (q === null) return; const p = prompt('Units per dose (usually 1)', '1'); if (p === null) return; const d = prompt('Warn when this many days remain', '5'); if (d === null) return; await call(API + '/medications/' + b.dataset.id + '/stock', 'PUT', { quantity: q, pills_per_dose: p, low_days: d }); reload(); },
    async medit(b) { const n = prompt('Medication name', b.dataset.n); if (n === null) return; const d = prompt('Dosage / label (as prescribed)', b.dataset.d); if (d === null) return; const i = prompt('Notes', b.dataset.i); if (i === null) return; await call(API + '/medications/' + b.dataset.id, 'PATCH', { name: n, dosage: d, instructions: i }); reload(); },
    async mpause(b) { if (b.dataset.on === '0' && !confirm('Pause this medication? Reminders stop until you resume it.')) return; await call(API + '/medications/' + b.dataset.id + '/active', 'POST', { active: b.dataset.on === '1' }); reload(); },
    async mdel(b) { const t = prompt('PERMANENTLY delete this medication and its history? (Pause is usually better.)\nType the medication name to confirm:\n' + b.dataset.n); if (t === null) return; await call(API + '/medications/' + b.dataset.id, 'DELETE', { confirm_name: t }); reload(); },
    export() { const u = $('exUser').value; location.href = API + '/export/events.csv?days=' + $('exDays').value + (u ? '&user_id=' + u : ''); }
  };

  document.addEventListener('click', async ev => {
    const t = ev.target.closest('[data-tab]'); if (t) return show(t.dataset.tab);
    const b = ev.target.closest('[data-act]'); if (!b || !A[b.dataset.act]) return;
    try { await A[b.dataset.act](b); } catch (e) { toast(e.message, true); }
  });
  document.addEventListener('change', ev => {
    if (ev.target.id === 'ptSel') { patientId = ev.target.value; show('patients'); }
    if (ev.target.id === 'alDays') { alertDays = ev.target.value; show('alerts'); }
  });
  document.addEventListener('submit', async ev => {
    const f = ev.target.closest('[data-form]'); if (!f) return; ev.preventDefault();
    const d = Object.fromEntries(new FormData(f)); const kind = f.dataset.form;
    try {
      if (kind === 'profile') { await call(API + '/users/' + patientId + '/profile', 'PUT', d); toast('Profile saved.'); }
      if (kind === 'newmed') {
        const times = [...f.querySelectorAll('input[name=t]')].map(i => i.value).filter(Boolean);
        await call(API + '/patients/' + patientId + '/medications', 'POST', { name: d.name, dosage: d.dosage, instructions: d.instructions, grace_minutes: d.grace_minutes, times });
        toast('Medication saved.'); reload();
      }
      if (kind === 'newuser') {
        const r = await call(API + '/users', 'POST', d);
        toast('', false, 'Account created for <b>' + E(r.name) + '</b>. Device token (shown once):<div class="ct-sec">' + E(r.device_token) + '</div>'); reload();
      }
    } catch (e) { toast(e.message, true); }
  });

  show(tab);
})();
