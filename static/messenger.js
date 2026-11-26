/* SilverCare MESSENGER — injected on every page (adds files only).
   1) CHAT link + unread badge   2) incoming-call screen on ANY page   3) /chat messenger page   4) WebRTC video / voice calls */
(function () {
  if (window.__scMessenger) return; window.__scMessenger = true;
  const $ = id => document.getElementById(id);
  const E = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  async function call(url, method = 'GET', body) {
    const o = { method, headers: { 'X-Requested-With': 'SilverCare' }, credentials: 'same-origin' };
    if (body instanceof FormData) o.body = body; else if (body !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(body); }
    const r = await fetch(url, o), d = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(d.error || 'Request failed (' + r.status + ')'); e.status = r.status; throw e; }
    return d;
  }
  const hm = s => String(s || '').slice(11, 16);
  const day = s => String(s || '').slice(0, 10);
  let SRV_DAY = '';
  const today = () => { if (SRV_DAY) return SRV_DAY; const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const dayLabel = s => s === today() ? 'Today' : s;
  const initials = n => (String(n || '?').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2) || '?').toUpperCase();
  const isTouch = matchMedia('(pointer:coarse)').matches;
  function toast(msg, err) {
    const t = $('mToast'); if (!t) return alert(msg);
    t.hidden = false; t.className = 'ct-toast' + (err ? ' err' : ''); t.textContent = msg; clearTimeout(toast.h); toast.h = setTimeout(() => { t.hidden = true; }, 5000);
  }
  const ME = { id: 0, role: '', name: '' };
  const CH = { cur: 0, name: '', list: [], lastId: 0, seen: 0, more: false, firstId: 0, lastDay: '', lastSid: 0, lastTs: 0, typingSent: 0, lastPulse: -1 };
  let stopped = false;

  // ───────── nav link, title badge ─────────
  function setBadge(n) {
    const a = document.querySelector('[data-m-link]'); if (a) a.innerHTML = 'CHAT' + (n ? '<span class="m-badge">' + n + '</span>' : '');
    document.title = document.title.replace(/^\(\d+\)\s*/, '') ; if (n) document.title = '(' + n + ') ' + document.title;
  }
  function navLink() {
    const top = document.querySelector('.top-right'); if (!top || top.querySelector('[data-m-link]')) return;
    const a = document.createElement('a'); a.className = 'logout-link'; a.dataset.mLink = '1'; a.href = '/chat'; a.textContent = 'CHAT';
    top.insertBefore(a, top.querySelector('.logout-link'));
  }

  // ───────── 1-second pulse ─────────
  let pBusy = false, prevUnread = 0;
  async function pulse() {
    if (pBusy || stopped) return; pBusy = true;
    try {
      const r = await fetch('/api/chat/pulse' + (CH.cur && $('mMsgs') ? '?t=' + CH.cur : ''), { cache: 'no-store', credentials: 'same-origin' });
      if ([401, 403, 404].includes(r.status)) { stopped = true; return; }
      onPulse(await r.json());
    } catch (e) { } finally { pBusy = false; }
  }
  function onPulse(d) {
    setBadge(d.unread); if (d.now) SRV_DAY = d.now.slice(0, 10);
    if (d.unread > prevUnread && document.hidden) { try { if (Notification.permission === 'granted') new Notification('💬 New message in SilverCare'); } catch (e) { } }
    prevUnread = d.unread;
    if (d.incoming && !CALL.id && RING.id !== d.incoming.id) showIncoming(d.incoming);
    if (!d.incoming && RING.id && !CALL.id) hideIncoming();
    if ($('mMsgs')) {
      if (d.last !== CH.lastPulse) { CH.lastPulse = d.last; loadList(); if (CH.cur) fetchNew(); }
      if (CH.cur) { setTyping(d.typing); if (d.seen !== undefined && d.seen !== CH.seen) { CH.seen = d.seen; markSeen(); } }
    }
  }

  // ───────── messenger page ─────────
  function skeleton() {
    $('mRoot').innerHTML = '<aside class="m-side"><div class="m-side-head"><h2>Chats</h2></div><input class="m-search" id="mSearch" placeholder="Search patients" autocomplete="off"><div class="m-list" id="mList"></div></aside><section class="m-main" id="mMain"></section>';
    $('mSearch').addEventListener('input', renderList);
    $('mMain').innerHTML = '<div class="m-empty">Select a chat<br><small>Messages, photos, voice notes and calls stay private between the patient and the care team.</small></div>';
  }
  async function loadList() {
    try { CH.list = await call('/api/chat/threads'); } catch (e) { return; } renderList();
    const t = CH.list.find(x => x.id === CH.cur); if (t && $('mHsub') && ME.role !== 'user') $('mHsub').textContent = t.online ? 'Online now' : 'Offline';
  }
  function renderList() {
    const q = ($('mSearch') ? $('mSearch').value : '').toLowerCase(), box = $('mList'); if (!box) return;
    box.innerHTML = CH.list.filter(t => !q || t.name.toLowerCase().includes(q)).map(t => {
      const mine = t.last_role && (ME.role === 'user' ? t.last_role === 'user' : t.last_role !== 'user');
      return '<button class="m-item ' + (t.id === CH.cur ? 'on ' : '') + (t.unread ? 'unread' : '') + '" data-open="' + t.id + '"><span class="m-av">' + E(initials(t.name)) + (t.online ? '<i class="m-dot"></i>' : '') + '</span><span class="m-meta"><b>' + E(t.name) + '</b><span>' +
        (t.last_body ? (mine ? 'You: ' : '') + E(t.last_body) : 'No messages yet') + '</span></span><span class="m-when">' + (t.last_at ? (day(t.last_at) === today() ? hm(t.last_at) : t.last_at.slice(5, 10)) : '') + (t.unread ? '<span class="m-badge">' + t.unread + '</span>' : '') + '</span></button>';
    }).join('') || '<div class="m-empty" style="padding:30px 10px">No chats yet.</div>';
  }
  async function openThread(id) {
    const t = CH.list.find(x => x.id === id); if (!t) return;
    Object.assign(CH, { cur: id, name: t.name, lastId: 0, seen: 0, more: false, firstId: 0, lastDay: '', lastSid: 0, lastTs: 0 });
    $('mRoot').classList.add('open'); renderList();
    $('mMain').innerHTML = '<div class="m-head"><button class="m-back" data-back="1">‹</button><span class="m-av sm">' + E(initials(t.name)) + '</span><span class="m-meta"><b>' + E(t.name) + '</b><span id="mHsub">' + (ME.role === 'user' ? 'Doctors & caregivers' : (t.online ? 'Online now' : 'Offline')) + '</span></span>' +
      '<span class="m-head-actions"><button class="m-ic" data-call="audio" title="Voice call">📞</button><button class="m-ic" data-call="video" title="Video call">🎥</button></span></div>' +
      '<div class="m-msgs" id="mMsgs"></div><div class="m-typing" id="mTyp"></div>' +
      '<div class="m-comp" id="mComp"><button class="m-ic" data-attach="1" title="Photo, video or file">📎</button><input type="file" id="mFile" hidden multiple accept="image/*,video/*,audio/*,application/pdf">' +
      '<textarea id="mTa" rows="1" placeholder="Message…"></textarea><div class="m-rec"><i></i><span id="mRecT">0:00</span><button class="m-ic" data-reccancel="1" title="Cancel">✕</button></div>' +
      '<button class="m-ic" data-rec="1" id="mRecBtn" title="Voice message">🎤</button><button class="m-send" data-send="1" title="Send">➤</button></div>';
    const ta = $('mTa'); ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'; if (Date.now() - CH.typingSent > 2500) { CH.typingSent = Date.now(); call('/api/chat/threads/' + CH.cur + '/typing', 'POST', {}).catch(() => { }); } });
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !isTouch) { e.preventDefault(); sendText(); } });
    ta.addEventListener('paste', e => { const f = [...(e.clipboardData?.files || [])]; if (f.length) { e.preventDefault(); sendFiles(f); } });
    $('mFile').addEventListener('change', e => { sendFiles([...e.target.files]); e.target.value = ''; });
    const m = $('mMsgs'); ['dragover', 'dragenter'].forEach(ev => m.addEventListener(ev, e => { e.preventDefault(); m.classList.add('m-drop'); }));
    ['dragleave', 'drop'].forEach(ev => m.addEventListener(ev, e => { e.preventDefault(); m.classList.remove('m-drop'); if (ev === 'drop') sendFiles([...e.dataTransfer.files]); }));
    m.addEventListener('scroll', () => { if (m.scrollTop < 40 && CH.more) loadOlder(); });
    if (ME.role !== 'user') location.hash = id;
    await fetchNew(true); if (!isTouch) ta.focus();
  }
  function msgHtml(m, prevSid, prevTs, prevDay) {
    const d = day(m.created_at), sep = d !== prevDay ? '<div class="m-day">' + E(dayLabel(d)) + '</div>' : '';
    const t = '<time>' + hm(m.created_at) + '</time>', f = m.files[0], ts = Date.parse(m.created_at);
    if (!f && /^[📹📞]/u.test(m.body)) return sep + '<div class="m-note" data-id="' + m.id + '">' + E(m.body) + ' · ' + hm(m.created_at) + '</div>';
    const mine = m.sender_id === ME.id, gap = (m.sender_id !== prevSid || ts - prevTs > 300000) ? ' gap' : '';
    const who = (!mine && gap) ? '<span class="m-who">' + E(m.sender_name) + '</span>' : '';
    let inner;
    if (f && f.kind === 'image') inner = '<div class="m-b media">' + '<img src="/api/chat/files/' + f.id + '" data-lb="' + f.id + '" loading="lazy" alt="photo">' + t + '</div>';
    else if (f && f.kind === 'video') inner = '<div class="m-b media"><video controls preload="metadata" playsinline src="/api/chat/files/' + f.id + '"></video>' + t + '</div>';
    else if (f && f.kind === 'audio') inner = '<div class="m-b">' + who + '<audio controls preload="metadata" src="/api/chat/files/' + f.id + '"></audio>' + t + '</div>';
    else if (f) inner = '<div class="m-b">' + who + '<a class="m-file" href="/api/chat/files/' + f.id + '?dl=1"><i>📄</i><span>' + E(f.name) + '<small>' + Math.max(1, Math.round(f.size / 1024)) + ' KB · tap to download</small></span></a>' + t + '</div>';
    else inner = '<div class="m-b">' + who + E(m.body) + t + '</div>';
    return sep + '<div class="m-row ' + (mine ? 'me' : '') + gap + '" data-id="' + m.id + '"' + (mine ? ' data-mine="1"' : '') + '>' + inner + '</div>';
  }
  function append(msgs, stick) {
    const box = $('mMsgs'); if (!box || !msgs.length) return;
    const near = box.scrollHeight - box.scrollTop - box.clientHeight < 120; let html = '';
    if (!CH.lastId) box.innerHTML = '';
    msgs.forEach(m => { if (m.id <= CH.lastId) return; html += msgHtml(m, CH.lastSid, CH.lastTs, CH.lastDay); CH.lastId = m.id; CH.lastSid = m.sender_id; CH.lastTs = Date.parse(m.created_at); CH.lastDay = day(m.created_at); });
    box.querySelectorAll('[data-temp]').forEach(x => x.remove());
    box.insertAdjacentHTML('beforeend', html); markSeen();
    if (stick || near || msgs.some(m => m.sender_id === ME.id)) box.scrollTop = box.scrollHeight;
  }
  async function fetchNew(first) {
    if (!CH.cur) return; const id = CH.cur;
    try {
      const d = await call('/api/chat/threads/' + id + '/messages' + (CH.lastId ? '?after=' + CH.lastId : '')); if (id !== CH.cur) return;
      if (first) { CH.more = d.has_more; CH.firstId = d.messages.length ? d.messages[0].id : 0; if (!d.messages.length && $('mMsgs')) $('mMsgs').innerHTML = '<div class="m-empty">Say hello 👋<br><small>Your messages are private.</small></div>'; }
      CH.seen = d.last_read_id; append(d.messages, first); setTyping(d.typing); loadList();
    } catch (e) { if (first) toast(e.message, true); }
  }
  async function loadOlder() {
    CH.more = false; const box = $('mMsgs'), h0 = box.scrollHeight;
    try {
      const d = await call('/api/chat/threads/' + CH.cur + '/messages?before=' + CH.firstId); if (!d.messages.length) return;
      let html = '', sid = 0, ts = 0, dd = ''; d.messages.forEach(m => { html += msgHtml(m, sid, ts, dd); sid = m.sender_id; ts = Date.parse(m.created_at); dd = day(m.created_at); });
      CH.firstId = d.messages[0].id; CH.more = d.has_more; box.insertAdjacentHTML('afterbegin', html); box.scrollTop = box.scrollHeight - h0;
    } catch (e) { }
  }
  function markSeen() {
    const box = $('mMsgs'); if (!box) return; box.querySelectorAll('.m-seen').forEach(x => x.remove());
    const mine = box.querySelectorAll('[data-mine]'), last = mine[mine.length - 1]; if (!last) return;
    const seen = Number(last.dataset.id) <= CH.seen; last.insertAdjacentHTML('afterend', '<div class="m-seen">' + (seen ? '✓✓ Seen' : '✓ Sent') + '</div>');
  }
  function setTyping(on) { const t = $('mTyp'); if (t) t.innerHTML = on ? '<span></span><span></span><span></span> typing…' : ''; }
  function addTemp(html) { const box = $('mMsgs'); if (!box) return; if (!CH.lastId) box.innerHTML = ''; box.insertAdjacentHTML('beforeend', '<div class="m-row me gap" data-temp="1" style="opacity:.6"><div class="m-b">' + html + '<time>sending…</time></div></div>'); box.scrollTop = box.scrollHeight; }
  async function sendText() {
    const ta = $('mTa'); if (!ta || !CH.cur) return; const t = ta.value.trim(); if (!t) return; ta.value = ''; ta.style.height = 'auto'; addTemp(E(t));
    try { const r = await call('/api/chat/threads/' + CH.cur + '/messages', 'POST', { body: t }); if (r.urgent) toast(r.urgent, true); await fetchNew(); }
    catch (e) { document.querySelectorAll('[data-temp]').forEach(x => x.remove()); ta.value = t; toast(e.message, true); }
  }
  async function sendFiles(files) {
    if (!CH.cur) return;
    for (const f of files) {
      if (f.size > 25 * 1024 * 1024) { toast('“' + f.name + '” is bigger than 25 MB.', true); continue; }
      addTemp('⏫ ' + E(f.name));
      try { const fd = new FormData(); fd.append('file', f, f.name); await call('/api/chat/threads/' + CH.cur + '/messages', 'POST', fd); await fetchNew(); }
      catch (e) { document.querySelectorAll('[data-temp]').forEach(x => x.remove()); toast(e.message, true); }
    }
  }

  // voice message recorder
  const REC = { mr: null, chunks: [], t: 0, timer: null, stream: null };
  async function recStart() {
    if (!window.MediaRecorder) return alert('This browser cannot record voice messages. Please update Safari/iPadOS or use Chrome.\n\nဒီ browser မှာ အသံသွင်းလို့မရပါ။ Safari/iPadOS ကို update လုပ်ပါ၊ ဒါမှမဟုတ် Chrome သုံးပါ။');
    try { REC.stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { return mediaProblem(e, 'the voice recorder'); }
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(m => MediaRecorder.isTypeSupported(m)) || '';
    REC.mr = new MediaRecorder(REC.stream, mime ? { mimeType: mime } : {}); REC.chunks = []; REC.mr.ondataavailable = e => { if (e.data.size) REC.chunks.push(e.data); }; REC.mr.start(250);
    REC.t = Date.now(); $('mComp').classList.add('rec'); $('mRecBtn').textContent = '■';
    REC.timer = setInterval(() => { const s = Math.floor((Date.now() - REC.t) / 1000); const el = $('mRecT'); if (el) el.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); if (s >= 300) recStop(true); }, 500);
  }
  function recStop(send) {
    const mr = REC.mr; if (!mr) return; clearInterval(REC.timer); REC.mr = null;
    mr.onstop = () => {
      REC.stream.getTracks().forEach(t => t.stop()); const type = mr.mimeType || 'audio/webm';
      if (send && REC.chunks.length && Date.now() - REC.t > 700) sendFiles([new File([new Blob(REC.chunks, { type })], 'voice-' + Date.now() + '.' + (type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'), { type })]);
    };
    mr.stop(); const c = $('mComp'); if (c) c.classList.remove('rec'); const b = $('mRecBtn'); if (b) b.textContent = '🎤';
  }

  // ───────── calls (WebRTC; signalling by polling) ─────────
  const CALL = { id: 0, kind: 'video', pc: null, pcP: null, local: null, after: 0, role: '', loop: null, offered: false, queue: [], peer: '', t0: 0, timer: null };
  const RING = { id: 0, t: null, inc: null }; let ICE = null, actx = null;
  function ringStart() {
    ringStop(); try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return; }
    const beep = () => { try { const o = actx.createOscillator(), g = actx.createGain(); o.frequency.value = 880; g.gain.value = .07; o.connect(g); g.connect(actx.destination); o.start(); o.stop(actx.currentTime + .3); navigator.vibrate && navigator.vibrate([250, 150, 250]); } catch (e) { } };
    beep(); RING.t = setInterval(beep, 1600);
  }
  function ringStop() { clearInterval(RING.t); RING.t = null; }
  function callEl() {
    let el = $('mCall'); if (el) return el;
    el = document.createElement('div'); el.id = 'mCall'; el.className = 'm-call'; el.hidden = true;
    el.innerHTML = '<video class="remote" id="mRemote" autoplay playsinline></video><video class="local" id="mLocal" autoplay playsinline muted></video><div class="m-who"><div class="m-av" id="mCav"></div><h2 id="mCname"></h2><p id="mCstate"></p></div><div class="m-dbg" id="mCdbg"></div><div class="m-ctl" id="mCctl"></div>';
    document.body.appendChild(el); return el;
  }
  function callUI(mode, kind, name, state) {
    const el = callEl(); el.hidden = false; el.className = 'm-call ' + (kind === 'audio' ? 'audio ' : 'video ') + (mode === 'incoming' ? 'ring ' : mode === 'outgoing' ? 'ring ' : 'live');
    $('mCav').textContent = initials(name); $('mCname').textContent = name; $('mCstate').textContent = state;
    $('mCctl').innerHTML = mode === 'incoming' ? '<button class="no" data-cdecline="1" title="Decline">✕</button><button class="yes" data-caccept="1" title="Answer">📞</button>'
      : '<button data-cmute="1" title="Mute">🎤</button>' + (kind === 'video' ? '<button data-ccam="1" title="Camera">🎥</button>' : '') + '<button class="end" data-cend="1" title="End call">📵</button>';
    if (CALL.local && kind === 'video') $('mLocal').srcObject = CALL.local;
  }
  const hideCallUI = () => { const el = $('mCall'); if (el) { el.hidden = true; $('mRemote').srcObject = null; $('mLocal').srcObject = null; } };
  async function iceServers() { if (!ICE) { try { ICE = (await call('/api/chat/ice')).iceServers; } catch (e) { ICE = [{ urls: 'stun:stun.l.google.com:19302' }]; } } return ICE; }
  async function media(kind) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('nomedia');
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: kind === 'video' ? { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } } : false });
  }
  function mediaProblem(e, what) {
    let en, my; const n = e && e.name;
    if (!window.isSecureContext) { en = 'Camera and microphone only work on a secure address (https://).'; my = 'Camera/mic သုံးဖို့ https:// လိပ်စာနဲ့ ဖွင့်ရပါမယ်။'; }
    else if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { en = 'This browser window blocks the camera/microphone. Open the site directly in Safari or Chrome (not inside the VS Code preview or another app’s built-in browser).'; my = 'ဒီ browser window က camera/mic ကို ပိတ်ထားပါတယ်။ VS Code preview ဒါမှမဟုတ် app ထဲက browser မဟုတ်ဘဲ Safari/Chrome ကို တိုက်ရိုက်ဖွင့်ပါ။'; }
    else if (n === 'NotAllowedError' || n === 'SecurityError') { en = 'Permission is blocked. iPad/iPhone: tap “aA” in the address bar → Website Settings → set Camera and Microphone to Allow, then reload. Chrome: tap the 🔒 icon → Permissions.'; my = 'ခွင့်ပြုချက် ပိတ်ထားပါတယ်။ iPad/iPhone: address bar က “aA” → Website Settings → Camera နဲ့ Microphone ကို Allow ပြောင်းပြီး page ကို reload လုပ်ပါ။'; }
    else if (n === 'NotFoundError') { en = 'No camera or microphone was found on this device.'; my = 'ဒီစက်မှာ camera/mic မတွေ့ပါ။'; }
    else if (n === 'NotReadableError') { en = 'The camera/microphone is being used by another app. Close that app and try again.'; my = 'Camera/mic ကို တခြား app က သုံးနေပါတယ်။ အဲဒီ app ကို ပိတ်ပြီး ပြန်စမ်းပါ။'; }
    else { en = 'Could not start ' + what + (e && e.message ? ' (' + e.message + ')' : '') + '.'; my = what + ' မစတင်နိုင်ပါ။'; }
    alert(en + '\n\n' + my + '\n\nTest page / စစ်ဆေးရန်: /static/callcheck.html');
  }
  const sig = (kind, payload) => call('/api/chat/calls/' + CALL.id + '/signal', 'POST', { kind, payload }).catch(() => { });
  function ensurePC() {
    if (CALL.pcP) return CALL.pcP;
    CALL.pcP = (async () => {
      const pc = new RTCPeerConnection({ iceServers: await iceServers() }); CALL.pc = pc;
      CALL.local.getTracks().forEach(t => pc.addTrack(t, CALL.local));
      CALL.mine = new Set(); CALL.theirs = new Set();
      const dbg = () => { const el = $('mCdbg'); if (el && CALL.pc) el.textContent = 'link: ' + CALL.pc.iceConnectionState + ' · my routes: ' + ([...CALL.mine].join('/') || 'none') + ' · their routes: ' + ([...CALL.theirs].join('/') || 'none'); };
      CALL.dbg = dbg; pc.oniceconnectionstatechange = () => { dbg(); if (pc.iceConnectionState === 'failed') netFail(); };
      clearTimeout(CALL.connTimer); CALL.connTimer = setTimeout(() => { if (CALL.id && !CALL.t0) netFail(); }, 25000);
      pc.onicecandidate = e => { if (e.candidate) { const m = / typ (\w+)/.exec(e.candidate.candidate || ''); if (m) CALL.mine.add(m[1]); dbg(); sig('ice', e.candidate.toJSON()); } };
      pc.ontrack = e => { const r = $('mRemote'); if (r.srcObject !== e.streams[0]) r.srcObject = e.streams[0]; if (r.play) r.play().catch(() => { const st = $('mCstate'); if (st) st.textContent = 'Tap the screen to hear / အသံကြားဖို့ နှိပ်ပါ'; document.addEventListener('click', () => r.play().catch(() => { }), { once: true }); }); };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'connected' && !CALL.t0) {
          CALL.t0 = Date.now(); callUI('live', CALL.kind, CALL.peer, '0:00');
          CALL.timer = setInterval(() => { const s = Math.floor((Date.now() - CALL.t0) / 1000); const el = $('mCstate'); if (el) el.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }, 1000);
        }
        if (pc.connectionState === 'failed') netFail();
      };
      return pc;
    })();
    return CALL.pcP;
  }
  async function flushQueue() { const pc = CALL.pc; while (CALL.queue.length) { try { await pc.addIceCandidate(CALL.queue.shift()); } catch (e) { } } }
  async function handleSignal(s) {
    const pc = await ensurePC();
    if (s.kind === 'offer') { await pc.setRemoteDescription(s.payload); await flushQueue(); const a = await pc.createAnswer(); await pc.setLocalDescription(a); await sig('answer', { type: a.type, sdp: a.sdp }); }
    else if (s.kind === 'answer') { await pc.setRemoteDescription(s.payload); await flushQueue(); }
    else if (s.kind === 'ice') { const m = / typ (\w+)/.exec((s.payload && s.payload.candidate) || ''); if (m && CALL.theirs) { CALL.theirs.add(m[1]); CALL.dbg && CALL.dbg(); } if (pc.remoteDescription) { try { await pc.addIceCandidate(s.payload); } catch (e) { } } else CALL.queue.push(s.payload); }
  }
  async function loopCall() {
    const id = CALL.id; if (!id) return;
    try {
      const d = await call('/api/chat/calls/' + id + '/poll?after=' + CALL.after); if (CALL.id !== id) return;
      if (['ended', 'declined', 'missed'].includes(d.state)) { toast(d.state === 'declined' ? 'Call declined.' : d.state === 'missed' ? 'No answer.' : 'Call ended.'); return endCall(false); }
      if (d.state === 'active' && CALL.role === 'caller' && !CALL.offered) {
        CALL.offered = true; if (!CALL.t0) callUI('live', CALL.kind, CALL.peer, 'Connecting…');
        const pc = await ensurePC(), o = await pc.createOffer(); await pc.setLocalDescription(o); await sig('offer', { type: o.type, sdp: o.sdp });
      }
      for (const s of d.signals) { CALL.after = Math.max(CALL.after, s.id); await handleSignal(s); }
    } catch (e) { }
    if (CALL.id === id) CALL.loop = setTimeout(loopCall, 600);
  }
  function netFail() {
    if (!CALL.id) return; const mine = [...(CALL.mine || [])], noRelay = !mine.includes('relay');
    alert('The call could not connect through the network.\n' + (noRelay ? 'No relay (TURN) route was available, so phones on different networks/mobile data often cannot reach each other. Try both devices on the same WiFi, or ask the admin to set up a TURN server.' : 'Please try again.') +
      '\n\nကွန်ရက်ကြောင့် ခေါ်ဆိုမှု မချိတ်မိပါ။ ' + (noRelay ? 'စက်နှစ်ခုကို WiFi တစ်ခုတည်းမှာ ချိတ်ပြီး ပြန်စမ်းပါ၊ ဒါမှမဟုတ် admin က TURN server ထည့်ပေးရပါမယ်။' : 'ပြန်စမ်းကြည့်ပါ။') + '\n\nroutes: ' + (mine.join('/') || 'none'));
    endCall(true);
  }
  async function startCall(kind) {
    if (CALL.id) return toast('You are already in a call.', true); if (!CH.cur) return;
    let stream; try { stream = await media(kind); } catch (e) { return mediaProblem(e, kind + ' call'); }
    try { const r = await call('/api/chat/threads/' + CH.cur + '/call', 'POST', { kind }); Object.assign(CALL, { id: r.id, kind: r.kind, local: stream, role: 'caller', after: 0, offered: false, queue: [], pc: null, pcP: null, t0: 0, peer: CH.name }); }
    catch (e) { stream.getTracks().forEach(t => t.stop()); return toast(e.message, true); }
    callUI('outgoing', kind, CH.name, 'Calling… (they must have SilverCare open)'); loopCall();
  }
  function showIncoming(inc) {
    RING.id = inc.id; RING.inc = inc; callUI('incoming', inc.kind, inc.from, 'Incoming ' + inc.kind + ' call'); ringStart();
    try { if (document.hidden && Notification.permission === 'granted') new Notification('📞 ' + inc.from + ' is calling'); } catch (e) { }
  }
  function hideIncoming() { ringStop(); RING.id = 0; RING.inc = null; if (!CALL.id) hideCallUI(); }
  async function acceptCall() {
    const inc = RING.inc; if (!inc) return; ringStop();
    let stream; try { stream = await media(inc.kind); } catch (e) { mediaProblem(e, 'the call'); call('/api/chat/calls/' + inc.id + '/decline', 'POST', {}).catch(() => { }); return hideIncoming(); }
    try { await call('/api/chat/calls/' + inc.id + '/accept', 'POST', {}); } catch (e) { stream.getTracks().forEach(t => t.stop()); toast(e.message, true); return hideIncoming(); }
    Object.assign(CALL, { id: inc.id, kind: inc.kind, local: stream, role: 'callee', after: 0, offered: false, queue: [], pc: null, pcP: null, t0: 0, peer: inc.from }); RING.id = 0; RING.inc = null;
    callUI('live', inc.kind, inc.from, 'Connecting…'); ensurePC(); loopCall();
  }
  function declineCall() { const inc = RING.inc; if (inc) call('/api/chat/calls/' + inc.id + '/decline', 'POST', {}).catch(() => { }); hideIncoming(); }
  function endCall(tell) {
    const id = CALL.id; clearTimeout(CALL.loop); clearInterval(CALL.timer); clearTimeout(CALL.connTimer);
    if (tell && id) call('/api/chat/calls/' + id + '/end', 'POST', {}).catch(() => { });
    try { CALL.pc && CALL.pc.close(); } catch (e) { } if (CALL.local) CALL.local.getTracks().forEach(t => t.stop());
    Object.assign(CALL, { id: 0, pc: null, pcP: null, local: null, t0: 0, role: '' }); hideCallUI(); if ($('mMsgs')) fetchNew();
  }
  window.addEventListener('pagehide', () => { if (CALL.id) fetch('/api/chat/calls/' + CALL.id + '/end', { method: 'POST', keepalive: true, headers: { 'X-Requested-With': 'SilverCare', 'Content-Type': 'application/json' }, body: '{}' }); });

  // ───────── clicks ─────────
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-open],[data-back],[data-call],[data-send],[data-attach],[data-rec],[data-reccancel],[data-lb],[data-cmute],[data-ccam],[data-cend],[data-caccept],[data-cdecline]'); if (!el) return;
    if (el.dataset.open) openThread(Number(el.dataset.open));
    else if (el.dataset.back) { $('mRoot').classList.remove('open'); CH.cur = 0; renderList(); }
    else if (el.dataset.call) startCall(el.dataset.call);
    else if (el.dataset.send) sendText();
    else if (el.dataset.attach) $('mFile').click();
    else if (el.dataset.rec) { REC.mr ? recStop(true) : recStart(); }
    else if (el.dataset.reccancel) recStop(false);
    else if (el.dataset.lb) { const lb = document.createElement('div'); lb.className = 'm-lb'; lb.innerHTML = '<img src="/api/chat/files/' + el.dataset.lb + '">'; lb.onclick = () => lb.remove(); document.body.appendChild(lb); }
    else if (el.dataset.cmute) { const t = CALL.local && CALL.local.getAudioTracks()[0]; if (t) { t.enabled = !t.enabled; el.classList.toggle('off', !t.enabled); } }
    else if (el.dataset.ccam) { const t = CALL.local && CALL.local.getVideoTracks()[0]; if (t) { t.enabled = !t.enabled; el.classList.toggle('off', !t.enabled); } }
    else if (el.dataset.cend) endCall(true);
    else if (el.dataset.caccept) acceptCall();
    else if (el.dataset.cdecline) declineCall();
  });

  // ───────── start ─────────
  (async function init() {
    if (!document.querySelector('.user-chip') && !$('mRoot')) { stopped = true; return; }   // login page: nothing to do
    try { Object.assign(ME, await call('/api/me')); } catch (e) { stopped = true; return; }
    navLink(); setInterval(pulse, 1000); pulse();
    try { if ('Notification' in window && Notification.permission === 'default') document.addEventListener('click', () => Notification.requestPermission(), { once: true }); } catch (e) { }
    if ($('mRoot')) {
      skeleton(); await loadList();
      if (ME.role === 'user') { if (CH.list[0]) openThread(CH.list[0].id); }
      else { const h = Number(location.hash.slice(1)); if (h) openThread(h); }
    }
  })();
})();
