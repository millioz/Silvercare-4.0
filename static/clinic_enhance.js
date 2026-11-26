/* SilverCare CLINIC — injected on every page by clinic/__init__.py.
   Staff: "CLINIC HUB" link with a live counter.  Patients: "MY CARE" link, floating SOS button, large-text mode. */
(function () {
  if (window.__scClinic) return; window.__scClinic = true;
  async function call(url, method = 'GET', body) {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SilverCare' }, body: body === undefined ? undefined : JSON.stringify(body) });
    const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || 'Request failed'); return d;
  }
  try { if (localStorage.getItem('sc_large') === '1') document.documentElement.classList.add('sc-large'); } catch (e) { }

  function addLink(text, href) {
    const nav = document.querySelector('.top-right'); if (!nav || nav.querySelector('[data-sc-clinic]')) return null;
    const a = document.createElement('a'); a.className = 'logout-link'; a.href = href; a.dataset.scClinic = '1';
    a.innerHTML = text + ' <span class="ct-badge hub" hidden>0</span>';
    nav.insertBefore(a, nav.querySelector('.logout-link')); return a.querySelector('.ct-badge');
  }
  async function start() {
    let me; try { me = await (await fetch('/api/me')).json(); } catch (e) { return; }
    if (!me || !me.role) return;
    if (me.role === 'user') {
      addLink('MY CARE', '/my-care');
      const b = document.createElement('button'); b.className = 'sc-sos'; b.title = 'I need help'; b.textContent = '🆘'; document.body.appendChild(b);
      b.addEventListener('click', async () => {
        if (!confirm('Send an urgent help request to your care team?')) return;
        try { const r = await call('/api/clinic/me/help', 'POST', { kind: 'sos' }); alert(r.text + (r.contact && r.contact.emergency_phone ? '\n\nYour emergency contact: ' + r.contact.emergency_name + ' ' + r.contact.emergency_phone : '')); }
        catch (e) { alert(e.message); }
      });
    } else {
      const badge = addLink('CLINIC HUB', '/clinic-hub');
      const poll = async () => { try { const d = await call('/api/clinic/badge'); if (badge) { badge.textContent = d.total; badge.hidden = !d.total; } } catch (e) { } };
      poll(); setInterval(poll, 30000);
    }
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
})();
