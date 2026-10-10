// VYBE discovery: browse (prev/next, no decision) + Pass / Interested (enquiry) / Like (fav) / Save.
// Buttons always work; gestures are progressive enhancement. No external AI.
let deck = [], idx = 0, busy = false;
let likedSet = new Set(), savedSet = new Set();

function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function val(id){ return (document.getElementById(id)||{}).value || ''; }
function status(msg){ const el = document.getElementById('swipe-status'); if(el) el.textContent = msg; }

function filtersQS(){
  const p = new URLSearchParams();
  const d = val('f-destination').trim(); if(d) p.set('destination', d);
  const mip = val('f-min-price').trim(); if(mip) p.set('min_price', mip);
  const map = val('f-max-price').trim(); if(map) p.set('max_price', map);
  const mid = val('f-min-dur').trim(); if(mid) p.set('min_duration', mid);
  const mad = val('f-max-dur').trim(); if(mad) p.set('max_duration', mad);
  const st = val('f-style').trim(); if(st) p.set('style', st);
  const ac = val('f-accom').trim(); if(ac) p.set('accommodation', ac);
  const op = val('f-operator').trim(); if(op) p.set('operator', op);
  const ms = val('f-min-score').trim(); if(ms) p.set('min_score', ms);
  const s = p.toString();
  return s ? '?' + s : '';
}

async function refreshState(){
  try {
    const j = await (await fetch('/api/interests')).json();
    likedSet = new Set((j.interests||[]).filter(i=>i.action==='like').map(i=>i.package_id));
    savedSet = new Set((j.interests||[]).filter(i=>i.action==='save').map(i=>i.package_id));
  } catch(e){}
  if (window.refreshNavCounts) window.refreshNavCounts();
}

async function loadDeck(){
  const empty = document.getElementById('empty-state');
  status('Loading trips…');
  if(empty) empty.classList.add('hidden');
  try {
    const j = await (await fetch('/api/packages/recommended' + filtersQS())).json();
    deck = j.packages || []; idx = 0;
    await refreshState();
    if(!deck.length){
      showEmpty('No packages match these filters.', 'Try widening the price or days range, or clearing filters.');
    } else {
      status(`${deck.length} trips for your VYBE — use ‹ › to browse, ♥ to decide.`);
    }
    renderCard();
  } catch(e){ status('Could not load trips — check your connection, then reload.'); showEmpty('Could not load trips.', 'Check your connection and try again.'); }
}

function showEmpty(title, text){
  const empty = document.getElementById('empty-state');
  if(!empty) return;
  const t = document.getElementById('empty-title'), x = document.getElementById('empty-text');
  if(t) t.textContent = title;
  if(x) x.textContent = text;
  empty.classList.remove('hidden');
}

function current(){ return deck[idx]; }

function renderCard(){
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  if(!stack) return;
  stack.innerHTML = '';
  if(idx >= deck.length || deck.length === 0){
    if(deck.length === 0 && empty.classList.contains('hidden')) showEmpty('All caught up!', 'You have reviewed every package. New trips appear here.');
    else empty.classList.remove('hidden');
    updateArrows(); return;
  }
  empty.classList.add('hidden');
  const p = current();
  const el = document.createElement('div');
  el.className = 'swipe-card';
  el.setAttribute('tabindex','0');
  const price = Number(p.price||0).toLocaleString('en-IN');
  const tags = [...(p.interest_tags||[]), ...(p.mood_tags||[]), ...(p.region_tags||[])].slice(0,3);
  const liked = likedSet.has(p.id);
  const saved = savedSet.has(p.id);
  const topReason = (p.match_reasons || [])[0] || '';
  el.innerHTML = `
    <div class="stamp like">INTERESTED</div><div class="stamp nope">PASS</div>
    <img src="${esc(p.cover_image || '')}" alt="${esc(p.destination||'trip')}" loading="lazy" />
    <div class="info">
      <b>${esc(p.title||'Trip')}</b><br/>
      <span class="muted">${esc(p.destination||'')} · ${esc(p.duration_days||'?')} days · ₹${price} <span class="muted small">/ person</span></span><br/>
      <span class="muted small">by ${esc((p.operator&&p.operator.company_name)||'operator')}</span>
      ${p.operator && p.operator.is_verified ? '<span class="badge verified">✓ Verified</span>' : ''}
      ${p.availability_status ? `<span class="badge">${esc(p.availability_status)}</span>` : ''}<br/>
      <span class="badge">★ ${esc(p.match_score??'—')}</span>
      ${topReason?`<span class="muted small">${esc(topReason)}</span>`:''}
      ${liked?'<span class="badge verified">♥ Liked</span>':''}
      ${saved?'<span class="badge verified">☆ Saved</span>':''}
      <p class="small">${tags.map(t=>`<span class="badge">${esc(t)}</span>`).join(' ')}</p>
      <button class="btn small ghost card-detail" type="button">View details</button>
    </div>`;
  el.querySelector('.card-detail')?.addEventListener('click', (e)=>{ e.stopPropagation(); openDetail(); });
  enableDrag(el);
  stack.appendChild(el);
  if (deck[idx+1] && deck[idx+1].cover_image){ const im = new Image(); im.src = deck[idx+1].cover_image; }
  updateArrows();
  syncActionStates();
}

function updateArrows(){
  const prev = document.getElementById('btn-prev'), next = document.getElementById('btn-next');
  if(prev) prev.disabled = idx <= 0;
  if(next) next.disabled = idx >= deck.length - 1 && deck.length > 0;
}

function syncActionStates(){
  const p = current();
  const likeBtn = document.getElementById('btn-like');
  const saveBtn = document.getElementById('btn-save');
  if(likeBtn && p) { likeBtn.classList.toggle('active', likedSet.has(p.id)); likeBtn.textContent = likedSet.has(p.id) ? '♥' : '♡'; }
  if(saveBtn && p) { saveBtn.classList.toggle('active', savedSet.has(p.id)); saveBtn.textContent = savedSet.has(p.id) ? '★' : '☆'; }
}

// ---- browse (no decision recorded) ----
function prev(){ if(idx > 0){ idx--; renderCard(); } }
function next(){ if(idx < deck.length - 1){ idx++; renderCard(); } else { status('End of list — no more packages with current filters.'); } }

// ---- Pass: record hide, advance ----
async function doPass(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const r = await fetch(`/api/packages/${p.id}/swipe`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'pass'})});
    if(!r.ok) throw new Error('pass failed');
    status(`Passed ${p.destination} — hidden unless you revisit it.`);
    deck.splice(idx, 1); // remove from session deck
    if(idx >= deck.length) idx = Math.max(0, deck.length - 1);
    await refreshState(); renderCard();
  } catch(e){ status('Could not record pass. Check connection.'); }
  busy = false;
}

// ---- Interested: creates ENQUIRY (not booking), advances ----
async function doInterested(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const r = await fetch('/api/enquiries', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({package_id:p.id, num_travellers:2})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || 'enquiry failed');
    status(`♥ Interested in ${p.destination}! Enquiry ${j.enquiry.status} (#${j.enquiry.id}) — operator will quote. No charge.`);
    deck.splice(idx, 1);
    if(idx >= deck.length) idx = Math.max(0, deck.length - 1);
    await refreshState(); renderCard();
  } catch(e){ status('Could not create enquiry: ' + e.message); }
  busy = false;
}

// ---- Like: favourite toggle, stays on card, never creates enquiry ----
async function doLike(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const isLiked = likedSet.has(p.id);
    const r = await fetch(`/api/packages/${p.id}/like`, {method: isLiked ? 'DELETE' : 'POST'});
    if(!r.ok) throw new Error('like failed');
    if(isLiked) likedSet.delete(p.id); else likedSet.add(p.id);
    if (window.refreshNavCounts) window.refreshNavCounts();
    renderCard();
  } catch(e){ status('Could not update favourite.'); }
  busy = false;
}

// ---- Save: bookmark toggle, stays ----
async function doSave(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const isSaved = savedSet.has(p.id);
    const r = await fetch(`/api/packages/${p.id}/save`, {method: isSaved ? 'DELETE' : 'POST'});
    if(!r.ok) throw new Error('save failed');
    if(isSaved) savedSet.delete(p.id); else savedSet.add(p.id);
    if (window.refreshNavCounts) window.refreshNavCounts();
    renderCard();
  } catch(e){ status('Could not update saved list.'); }
  busy = false;
}

async function doUndo(){
  status('Undo: use header Saved/Liked to revisit; swipes persist server-side. Reloading deck…');
  await loadDeck();
}

function openDetail(){
  const p = current(); if(!p) return;
  const m = document.getElementById('detail-modal');
  const body = document.getElementById('dm-body');
  document.getElementById('dm-title').textContent = p.title || 'Trip';
  const orEmpty = v => (v==null || v==='' || (Array.isArray(v)&&v.length===0)) ? 'Not provided' : v;
  const price = Number(p.price||0).toLocaleString('en-IN');
  body.innerHTML = `
    <img src="${esc(p.cover_image||'')}" alt="" style="width:100%;border-radius:12px;max-height:280px;object-fit:cover" />
    <p class="muted">${esc(p.destination||'')} · ${esc(p.duration_days||'?')} days${p.nights!=null?` / ${esc(p.nights)} nights`:''} · <b>₹${price}</b> / person</p>
    <p><b>Operator:</b> ${esc((p.operator&&p.operator.company_name)||'Not provided')} ${p.operator&&p.operator.is_verified?'<span class="badge verified">✓ Verified</span>':'<span class="badge">Unverified</span>'}</p>
    <p><b>Availability:</b> ${esc(p.availability_status||'Not provided')} ${p.seats_remaining!=null?`(${esc(p.seats_remaining)} seats)`:''}</p>
    <p><b>Why it matches:</b> ${esc(p.match_explanation||'Not provided')}</p>
    <p>${esc(p.short_desc||'Not provided')}</p>
    <h4>Itinerary</h4><p>${esc(p.itinerary||'Not provided')}</p>
    <div class="cols"><div><h4>Included</h4><p>${esc((p.included||[]).join(', ')||'Not provided')}</p>
    <h4>Excluded</h4><p>${esc((p.excluded||[]).join(', ')||'Not provided')}</p></div>
    <div><h4>Stay</h4><p>${esc(p.accommodation||'Not provided')}</p>
    <h4>Transport</h4><p>${esc(p.transportation||'Not provided')}</p>
    <h4>Dates</h4><p>${esc((p.departure_dates_list||[]).join(', ')||p.available_dates||'Not provided')}</p>
    <h4>Group</h4><p>${esc(p.group_size||'Not provided')}${p.min_group_size!=null||p.max_group_size!=null?` (${esc(p.min_group_size??'?')}–${esc(p.max_group_size??'?')})`:''} Capacity: ${esc(p.capacity??'Not provided')}</p></div></div>
    <h4>Cancellation</h4><p>${esc(p.cancellation_terms||'Not provided')}</p>
    <div class="cta-row"><a class="btn small ghost" href="/packages/${p.id}">Open full page</a></div>`;
  m.classList.remove('hidden');
}
function closeDetail(){ document.getElementById('detail-modal').classList.add('hidden'); }

async function doShare(){
  const p = current(); if(!p) return;
  const url = location.origin + '/packages/' + p.id;
  try {
    if(navigator.share){ await navigator.share({title:p.title, url}); }
    else { await navigator.clipboard.writeText(url); status('Link copied: ' + url); }
  } catch(e){ try{ await navigator.clipboard.writeText(url); status('Link copied.'); }catch(_){ status(url); } }
}

// ---- gestures: right = interested (enquiry), left = pass ----
let dragX = 0;
function enableDrag(el){
  let startX=0, startY=0, curX=0, dragging=false, modalOpen=false;
  const like = ()=>el.querySelector('.stamp.like'), nope = ()=>el.querySelector('.stamp.nope');
  const isModal = ()=>!document.getElementById('detail-modal').classList.contains('hidden');
  const down = (x,y)=>{ if(isModal()) return; dragging=true; startX=x; startY=y; el.style.transition=''; };
  const move = (x,y)=>{
    if(!dragging || isModal()) return;
    if(Math.abs(y-startY) > 60 && Math.abs(x-startX) < 20) return; // let vertical scroll win
    curX = x-startX; dragX = curX;
    el.style.transform = `translateX(${curX}px) rotate(${curX/18}deg)`;
    const l=like(), n=nope();
    if(l) l.style.opacity = curX>40 ? Math.min(1,curX/120):0;
    if(n) n.style.opacity = curX<-40 ? Math.min(1,-curX/120):0;
  };
  const up = ()=>{
    if(!dragging) return; dragging=false;
    if(isModal()){ el.style.transform=''; return; }
    if(curX > 90) doInterested();
    else if(curX < -90) doPass();
    else { el.style.transition='transform .2s'; el.style.transform=''; dragX=0; }
    curX=0;
  };
  el.addEventListener('pointerdown', e=>{ if(e.target.closest('button,a')) return; down(e.clientX,e.clientY); });
  window.addEventListener('pointermove', e=>move(e.clientX,e.clientY));
  window.addEventListener('pointerup', up);
  el.addEventListener('touchstart', e=>{ if(e.target.closest('button,a')) return; down(e.touches[0].clientX,e.touches[0].clientY); }, {passive:true});
  el.addEventListener('touchmove', e=>move(e.touches[0].clientX,e.touches[0].clientY), {passive:true});
  el.addEventListener('touchend', up);
  el.style.touchAction = 'pan-y';
}

document.getElementById('btn-prev')?.addEventListener('click', prev);
document.getElementById('btn-next')?.addEventListener('click', next);
document.getElementById('btn-pass')?.addEventListener('click', doPass);
document.getElementById('btn-interested')?.addEventListener('click', doInterested);
document.getElementById('btn-like')?.addEventListener('click', doLike);
document.getElementById('btn-save')?.addEventListener('click', doSave);
document.getElementById('btn-undo')?.addEventListener('click', doUndo);
document.getElementById('btn-detail')?.addEventListener('click', openDetail);
document.getElementById('dm-close')?.addEventListener('click', closeDetail);
document.getElementById('detail-modal')?.addEventListener('click', e=>{ if(e.target.id==='detail-modal') closeDetail(); });
document.getElementById('btn-share')?.addEventListener('click', doShare);
document.getElementById('f-apply')?.addEventListener('click', loadDeck);
document.getElementById('f-clear')?.addEventListener('click', ()=>{
  ['f-destination','f-min-price','f-max-price','f-min-dur','f-max-dur','f-style','f-accom','f-operator','f-min-score'].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=''; });
  loadDeck();
});
document.getElementById('empty-clear')?.addEventListener('click', ()=>{
  ['f-destination','f-min-price','f-max-price','f-min-dur','f-max-dur','f-style','f-accom','f-operator','f-min-score'].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=''; });
  loadDeck();
});
const moreBtn = document.getElementById('btn-more'), moreMenu = document.getElementById('more-menu');
moreBtn?.addEventListener('click', ()=>moreMenu.classList.toggle('hidden'));
document.getElementById('m-hide')?.addEventListener('click', async ()=>{
  const p=current(); if(!p) return; moreMenu.classList.add('hidden');
  await fetch(`/api/packages/${p.id}/hide`, {method:'POST'});
  deck.splice(idx,1); if(idx>=deck.length) idx=Math.max(0,deck.length-1); renderCard(); status(`Hidden ${p.destination}`);
});
document.getElementById('m-report')?.addEventListener('click', async ()=>{
  const p=current(); if(!p) return; moreMenu.classList.add('hidden');
  const reason = prompt('What is wrong with this package?', 'incorrect info') || 'incorrect info';
  const r = await fetch('/api/reports', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target_type:'package', target_id:p.id, reason:reason.slice(0,120)})});
  status(r.ok ? 'Report recorded — thank you.' : 'Could not record report.');
});
document.getElementById('m-operator')?.addEventListener('click', ()=>{
  const p=current(); if(!p) return; moreMenu.classList.add('hidden'); openDetail();
});
document.addEventListener('keydown', e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;
  if(!document.getElementById('detail-modal').classList.contains('hidden')){ if(e.key==='Escape') closeDetail(); return; }
  if(e.key==='ArrowRight') next();
  if(e.key==='ArrowLeft') prev();
});
loadDeck();
