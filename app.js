const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json',...(options.headers||{})}, ...options});
  const data = await response.json().catch(()=>({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function statusPill(status){return `<span class="status-pill ${esc(status)}">${esc(status.toUpperCase())}</span>`;}
function eventMarkup(e, allowConfirm=true){
  const dt = new Date(e.scheduled_for);
  const time = Number.isNaN(dt.getTime()) ? e.scheduled_for.slice(11,16) : dt.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  const confirmed = e.confirmed_at ? new Date(e.confirmed_at.replace(' ','T')).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
  return `<div class="event-row"><div class="event-time">${esc(time)}</div><div><div class="event-name">${esc(e.medication_name)}</div><div class="event-meta">${esc(e.dosage || 'Scheduled reminder')} · ${e.status==='missed'?'Confirmation window passed':e.status==='taken'?'User/device confirmation recorded':'Awaiting response'}</div></div>${statusPill(e.status)}${allowConfirm && e.status!=='taken' ? `<button class="confirm-btn" data-confirm="${e.id}">I have taken this</button>`:''}</div>`;
}
async function confirmDose(id){
  if(!confirm('Confirm that you have taken this medication? This records your confirmation only.')) return;
  try{await api(`/api/events/${id}/confirm`,{method:'POST',body:JSON.stringify({})}); await loadUserDashboard();}
  catch(err){alert(err.message);}
}
function attachConfirmButtons(root){root.querySelectorAll('[data-confirm]').forEach(b=>b.addEventListener('click',()=>confirmDose(b.dataset.confirm)));}
function renderWeekly(rows){
  const target=$('weeklyChart'); if(!target)return;
  const days=[]; const map=new Map(rows.map(r=>[r.day,r]));
  for(let i=6;i>=0;i--){const d=new Date();d.setDate(d.getDate()-i);const key=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;days.push({key,label:d.toLocaleDateString([], {weekday:'short'}),row:map.get(key)});}
  target.innerHTML=days.map(({label,row})=>{const n=row?(row.taken+row.missed):0;const pct=n?Math.round(row.taken/n*100):0;return `<div class="bar-col" title="${n?`${row.taken} confirmed / ${row.missed} missed window`:'No decided events'}"><div class="bar" style="height:${n?Math.max(5,pct):3}%"></div><span class="bar-label">${label}</span></div>`;}).join('');
}
async function loadUserDashboard(){
  const [summary,events]=await Promise.all([api('/api/summary'),api('/api/events')]);
  $('takenCount').textContent=summary.today.taken; $('pendingCount').textContent=summary.today.pending; $('missedCount').textContent=summary.today.missed;
  const rate=summary.confirmation_rate; $('rateValue').textContent=rate===null?'—':`${rate}%`; $('ringValue').textContent=rate===null?'—':`${rate}%`; $('rateRing').style.setProperty('--rate',`${rate||0}%`);
  $('rateCaption').textContent=rate===null?'No decided events yet':'Confirmed ÷ (confirmed + missed-window events)';
  $('insightText').textContent=rate===null?'No completed event data yet. Your dashboard will show a trend after the first scheduled reminders.':rate>=90?'Your recent confirmation pattern is consistent. Keep following the prescribed schedule.':rate>=70?'Some scheduled reminders have not been confirmed. Review the timeline and discuss any concerns with your caregiver.':'Your recent records show several unconfirmed reminders. Please check in with your caregiver; do not change or repeat doses based on this score.';
  const now=new Date(); const todayKey=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
  const today=events.filter(e=>e.scheduled_for.slice(0,10)===todayKey);
  const list=$('eventList'); list.innerHTML=today.length?today.sort((a,b)=>a.scheduled_for.localeCompare(b.scheduled_for)).map(e=>eventMarkup(e)).join(''):'<div class="empty-state">No reminders are scheduled for today.<br>Ask your caregiver to add a schedule.</div>';
  const history=$('historyRows'); history.innerHTML=events.length?events.slice(0,20).map(e=>`<tr><td>${esc(e.medication_name)}</td><td>${esc(e.scheduled_for.replace('T',' '))}</td><td>${statusPill(e.status)}</td><td>${e.confirmed_at?esc(e.confirmed_at.replace('T',' ')):'—'}</td></tr>`).join(''):'<tr><td colspan="4" class="muted">No medication events have been recorded.</td></tr>';
  renderWeekly(summary.weekly); attachConfirmButtons(list);
}
async function loadStaff(){
  const users=await api('/api/users');
  const list=$('userList'), select=$('patientSelect'), monitor=$('monitorPatient');
  list.innerHTML=users.length?users.map(u=>`<div class="user-item"><div><strong>${esc(u.name)}</strong><small>${esc(u.email)}</small></div><button type="button" data-pick="${u.id}">Monitor</button></div>`).join(''):'<div class="empty-state">No patient accounts yet. Create the first account below.</div>';
  const opts='<option value="">Choose a patient</option>'+users.map(u=>`<option value="${u.id}">${esc(u.name)}</option>`).join('');
  select.innerHTML=opts; monitor.innerHTML=opts;
  list.querySelectorAll('[data-pick]').forEach(b=>b.addEventListener('click',()=>{monitor.value=b.dataset.pick;loadPatientMonitor(b.dataset.pick);}));
  if(users.length){monitor.value=users[0].id;loadPatientMonitor(users[0].id);}
}
async function loadPatientMonitor(uid){
  if(!uid)return;
  const [summary,events]=await Promise.all([api(`/api/summary?user_id=${uid}`),api(`/api/events?user_id=${uid}`)]);
  $('takenCount').textContent=summary.today.taken;$('pendingCount').textContent=summary.today.pending;$('missedCount').textContent=summary.today.missed;$('rateValue').textContent=summary.confirmation_rate===null?'—':`${summary.confirmation_rate}%`;
  $('adminEvents').innerHTML=events.length?events.slice(0,30).map(e=>eventMarkup(e,false)).join(''):'<div class="empty-state">No events recorded for this patient.</div>';
}
function setupStaffForms(){
  $('userForm').addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const msg=$('userMessage');msg.className='form-message';try{const result=await api('/api/users',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});msg.innerHTML=`Account created for <b>${esc(result.name)}</b>. ESP32 device token (copy and store securely):<div class="token-output">${esc(result.device_token)}</div>`;e.currentTarget.reset();await loadStaff();}catch(err){msg.textContent=err.message;msg.classList.add('error');}});
  $('medForm').addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const data=Object.fromEntries(f);data.user_id=Number(data.user_id);data.grace_minutes=Number(data.grace_minutes);const msg=$('medMessage');msg.className='form-message';try{await api('/api/medications',{method:'POST',body:JSON.stringify(data)});msg.textContent='Reminder saved. The daily event will appear automatically.';e.currentTarget.reset();}catch(err){msg.textContent=err.message;msg.classList.add('error');}});
  $('monitorPatient').addEventListener('change',e=>loadPatientMonitor(e.target.value));
}
document.addEventListener('DOMContentLoaded',()=>{
  if(window.SILVERCARE_ROLE==='user'){loadUserDashboard().catch(e=>{$('eventList').innerHTML=`<div class="empty-state">${esc(e.message)}</div>`;});setInterval(()=>loadUserDashboard().catch(()=>{}),30000);}
  if(window.SILVERCARE_ROLE==='staff'){setupStaffForms();loadStaff().catch(e=>{$('userList').textContent=e.message;});setInterval(()=>{const selected=$('monitorPatient')?.value;if(selected)loadPatientMonitor(selected).catch(()=>{});},30000);}
  const label=$('todayLabel');if(label)label.textContent=`LOCAL DATE · ${new Date().toLocaleDateString([], {weekday:'long',month:'short',day:'numeric'})}`;
});
