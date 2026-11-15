/* SilverCare PLUS — loaded automatically on every page by extensions.py.
   Staff pages: "Care tools" link with alert badge, Disable/Delete buttons on the user list, alert sound.
   Patient page: due-now banner, sound + notification alarm, refill warning. */
(function () {
  if (window.__scEnhance) return;
  window.__scEnhance = true;

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

  // ── sound + notification helpers (browsers only allow sound after a tap, see "Enable alerts") ──
  let audioCtx = null;
  function unlockAudio() {
    try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); audioCtx.resume(); } catch (e) { }
  }
  function beep(times = 3) {
    if (!audioCtx || localStorage.getItem('sc_sound') === 'off') return;
    for (let i = 0; i < times; i++) {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = 880; o.connect(g); g.connect(audioCtx.destination);
      const t = audioCtx.currentTime + i * 0.45;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.35, t + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
      o.start(t); o.stop(t + 0.4);
    }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  }
  function notify(title, body) {
    try { if ('Notification' in window && Notification.permission === 'granted') new Notification(title, { body }); } catch (e) { }
  }
  document.addEventListener('click', unlockAudio, { once: true });

  async function start() {
    let me;
    try { me = await (await fetch('/api/me')).json(); } catch (e) { return; }
    if (!me || !me.role) return;
    if (me.role === 'user') patient(); else staff(me);
  }

  // ───────────────────────── staff pages ─────────────────────────
  function staff(me) {
    const nav = document.querySelector('.top-right');
    let badgeEl = null;
    if (nav && !nav.querySelector('[data-sc-nav]')) {
      const a = document.createElement('a');
      a.className = 'logout-link'; a.href = '/care-tools'; a.dataset.scNav = '1';
      a.innerHTML = 'CARE TOOLS <span class="ct-badge" hidden>0</span>';
      nav.insertBefore(a, nav.querySelector('.logout-link'));
      badgeEl = a.querySelector('.ct-badge');
    }
    let lastCount = null;
    async function poll() {
      try {
        const b = await call('/api/plus/badge');
        const n = b.unacked_missed + b.overdue_now;
        if (badgeEl) { badgeEl.textContent = n; badgeEl.hidden = n === 0; }
        if (lastCount !== null && n > lastCount) { beep(2); notify('SilverCare alert', 'A patient dose needs attention.'); }
        lastCount = n;
      } catch (e) { }
    }
    poll(); setInterval(poll, 30000);

    // Delete / disable buttons on the ORIGINAL admin "Registered users" list
    const list = document.getElementById('userList');
    if (list) {
      const decorate = () => {
        list.querySelectorAll('.user-item').forEach(item => {
          if (item.querySelector('.sc-wrap')) return;
          const pick = item.querySelector('[data-pick]');
          if (!pick) return;
          const id = pick.dataset.pick;
          const email = (item.querySelector('small')?.textContent || '').trim();
          const name = (item.querySelector('strong')?.textContent || '').trim();
          const wrap = document.createElement('span'); wrap.className = 'sc-wrap';
          wrap.innerHTML = '<button type="button" class="sc-mini" data-a="off">Disable</button>' +
            (me.role === 'admin' ? '<button type="button" class="sc-mini danger" data-a="del">Delete</button>' : '');
          pick.after(wrap);
          wrap.addEventListener('click', async ev => {
            const a = ev.target.dataset.a; if (!a) return;
            try {
              if (a === 'off') {
                if (!confirm('Disable ' + name + '? They will no longer be able to sign in and reminders stop. History is kept.')) return;
                await call('/api/plus/users/' + id + '/active', 'POST', { active: false });
              } else {
                const typed = prompt('PERMANENT DELETE of ' + name + ' and ALL their medications, schedules and history.\n\nType their email to confirm:\n' + email);
                if (typed === null) return;
                await call('/api/plus/users/' + id, 'DELETE', { confirm_email: typed });
              }
              location.reload();
            } catch (err) { alert(err.message); }
          });
        });
      };
      decorate();
      new MutationObserver(decorate).observe(list, { childList: true });
    }
  }

  // ───────────────────────── patient page ─────────────────────────
  function patient() {
    const shell = document.querySelector('.app-shell'); if (!shell) return;
    const box = document.createElement('section'); box.className = 'sc-banner'; box.id = 'scBanner';
    const heading = shell.querySelector('.page-heading');
    heading ? heading.after(box) : shell.prepend(box);
    const alerted = {};   // event id -> last alert time
    let flash = null;

    function permissionRow() {
      const needs = ('Notification' in window && Notification.permission === 'default') || !audioCtx;
      return needs ? '<button class="ct-btn" id="scEnable">🔔 Enable sound &amp; notifications</button>' : '<span class="ct-small">🔔 Alerts on</span>';
    }
    function draw(s) {
      let html = '';
      if (s.due.length) {
        box.classList.add('due');
        html += '<h3>💊 Medication time</h3>' + s.due.map(e =>
          '<div class="row"><div><strong>' + E(e.medication) + '</strong><div class="ct-small">' + E(e.dosage || 'Scheduled reminder') + ' · confirm within ' + e.minutes_left + ' min</div></div>' +
          '<button class="ct-btn" data-ok="' + e.id + '">I have taken this</button></div>').join('');
      } else {
        box.classList.remove('due');
        html += '<h3>Next reminder</h3>' + (s.next
          ? '<div class="ct-small"><strong>' + E(s.next.medication) + '</strong> at ' + E(s.next.scheduled_for.slice(11, 16)) + '</div>'
          : '<div class="ct-small">No more reminders scheduled today.</div>');
      }
      if (s.low_stock.length) html += '<div class="row"><div class="ct-small">⚠️ Running low: ' + s.low_stock.map(x => E(x.medication) + ' (~' + x.days_left + ' days)').join(', ') + '. Ask your caregiver or pharmacist about a refill.</div></div>';
      html += '<div class="row">' + permissionRow() + '</div>';
      box.innerHTML = html;
    }
    async function poll() {
      try {
        const s = await call('/api/plus/me/status'); draw(s);
        const now = Date.now(); let fire = false;
        s.due.forEach(e => { if (!alerted[e.id] || now - alerted[e.id] > 120000) { alerted[e.id] = now; fire = true; } });
        if (fire) { beep(3); notify('Medication time', s.due.map(e => e.medication).join(', ')); }
        if (s.due.length && !flash) { let on = false; flash = setInterval(() => { document.title = (on = !on) ? '💊 Medicine due!' : 'SILVERCARE'; }, 1000); }
        if (!s.due.length && flash) { clearInterval(flash); flash = null; document.title = 'SILVERCARE'; }
      } catch (e) { }
    }
    box.addEventListener('click', async ev => {
      if (ev.target.id === 'scEnable') {
        unlockAudio(); if ('Notification' in window && Notification.permission === 'default') await Notification.requestPermission(); beep(1); poll();
      }
      const id = ev.target.dataset.ok;
      if (id && confirm('Confirm that you have taken this medication? This records your confirmation only.')) {
        try { await call('/api/events/' + id + '/confirm', 'POST', {}); await poll(); } catch (e) { alert(e.message); }
      }
    });
    poll(); setInterval(poll, 20000);
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
})();
