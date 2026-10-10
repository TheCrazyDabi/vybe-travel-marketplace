// VYBE discovery: refine screen first, swipe screen after "Find my trips".
// No packages fetched until filters applied. History/favourites/saved preserved.
let deck = [], idx = 0, busy = false, sessionStarted = false;
let likedSet = new Set(), savedSet = new Set();
let appliedFilters = {};

function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function val(id){ return (document.getElementById(id)||{}).value || ''; }
function setVal(id, v){ const el = document.getElementById(id); if(el) el.value = v ?? ''; }
function status(msg){ const el = document.getElementById('swipe-status'); if(el) el.textContent = msg; }
function rstatus(msg){ const el = document.getElementById('refine-status'); if(el) el.textContent = msg; }
function checkedVals(sel){ return [...document.querySelectorAll(sel + ' input:checked')].map(i=>i.value); }
function setChecked(sel, vals){
  const set = new Set((vals||[]).map(v=>String(v).toLowerCase()));
  document.querySelectorAll(sel + ' input').forEach(i=>{
    i.checked = set.has(i.value.toLowerCase());
    i.closest('.chip')?.classList.toggle('selected', i.checked);
  });
}

function showRefine(){
  document.getElementById('refine-screen')?.classList.remove('hidden');
  document.getElementById('swipe-screen')?.classList.add('hidden');
  // prepopulate with currently applied filters (Edit preserves values)
  if(appliedFilters){
    setVal('f-destination', appliedFilters.destination || '');
    setVal('f-operator', appliedFilters.operator || '');
    setVal('f-min-price', appliedFilters.min_price || '');
    setVal('f-max-price', appliedFilters.max_price || '');
    setVal('f-min-dur', appliedFilters.min_duration || '');
    setVal('f-max-dur', appliedFilters.max_duration || '');
    setVal('f-accom', appliedFilters.accommodation || '');
    setVal('f-style', appliedFilters.style || '');
    setVal('f-min-score', appliedFilters.min_score || '');
    setVal('f-include', appliedFilters.include || '');
    setVal('f-avoid', appliedFilters.avoid || '');
    setVal('f-dates', appliedFilters.dates || '');
    setVal('f-group', appliedFilters.group || '');
    if(appliedFilters.landscape) setChecked('#f-landscape', appliedFilters.landscape);
    if(appliedFilters.styles) setChecked('#f-styles', appliedFilters.styles);
  }
}
function showSwipe(){
  document.getElementById('refine-screen')?.classList.add('hidden');
  document.getElementById('swipe-screen')?.classList.remove('hidden');
}

function readRefine(){
  const f = {
    destination: val('f-destination').trim(),
    operator: val('f-operator').trim(),
    min_price: val('f-min-price').trim(),
    max_price: val('f-max-price').trim(),
    min_duration: val('f-min-dur').trim(),
    max_duration: val('f-max-dur').trim(),
    accommodation: val('f-accom').trim(),
    style: val('f-style').trim(),
    min_score: val('f-min-score').trim(),
    include: val('f-include').trim(),
    avoid: val('f-avoid').trim(),
    dates: val('f-dates').trim(),
    group: val('f-group').trim(),
    landscape: checkedVals('#f-landscape'),
    styles: checkedVals('#f-styles'),
  };
  return f;
}
function validateFilters(f){
  const num = v => v === '' ? null : Number(v);
  if(f.min_price !== '' && (isNaN(num(f.min_price)) || num(f.min_price) < 0)) return 'Minimum budget must be 0 or more.';
  if(f.max_price !== '' && (isNaN(num(f.max_price)) || num(f.max_price) < 0)) return 'Maximum budget must be 0 or more.';
  if(f.min_price !== '' && f.max_price !== '' && num(f.min_price) > num(f.max_price)) return 'Minimum budget cannot exceed maximum.';
  if(f.min_duration !== '' && f.max_duration !== '' && Number(f.min_duration) > Number(f.max_duration)) return 'Minimum days cannot exceed maximum days.';
  if(f.min_score !== '' && (isNaN(Number(f.min_score)) || Number(f.min_score) < 0 || Number(f.min_score) > 100)) return 'Match score must be 0–100.';
  return null;
}
function filtersQS(f){
  const p = new URLSearchParams();
  if(f.destination) p.set('destination', f.destination);
  if(f.operator) p.set('operator', f.operator);
  if(f.min_price) p.set('min_price', f.min_price);
  if(f.max_price) p.set('max_price', f.max_price);
  if(f.min_duration) p.set('min_duration', f.min_duration);
  if(f.max_duration) p.set('max_duration', f.max_duration);
  if(f.accommodation) p.set('accommodation', f.accommodation);
  const styleAll = [...(f.styles || [])];
  if(f.style.trim()) styleAll.push(f.style.trim());
  if(styleAll.length) p.set('style', styleAll.join(','));
  if(f.min_score) p.set('min_score', f.min_score);
  if(f.landscape && f.landscape.length) p.set('region', f.landscape.join(','));
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

async function prefillFromProfile(){
  try {
    const j = await (await fetch('/api/profile')).json();
    const p = j.profile || {};
    if(!appliedFilters.destination && (p.destination_text || (p.preferred_destinations||[])[0]))
      setVal('f-destination', p.destination_text || (p.preferred_destinations||[])[0]);
    if(!appliedFilters.max_price && (p.budget_per_person || p.budget_max))
      setVal('f-max-price', p.budget_per_person || p.budget_max);
    if(!appliedFilters.min_duration && p.duration_days) setVal('f-min-dur', Math.max(1, p.duration_days - 1));
    if(!appliedFilters.max_duration && p.duration_days) setVal('f-max-dur', p.duration_days + 2);
    if(p.group_size_pref || p.num_travellers) setVal('f-group', p.num_travellers || '');
  } catch(e){}
}

function setChrome(state){
  // loading|ready|empty — swipe controls visible only when a package is shown
  const loading = state === 'loading', empty = state === 'empty';
  document.getElementById('loading-state')?.classList.toggle('hidden', !loading);
  const showActions = state === 'ready';
  document.querySelector('.swipe-actions')?.classList.toggle('hidden', !showActions);
  document.querySelector('#swipe-screen .toolbar')?.classList.toggle('hidden', !showActions);
  const prev = document.getElementById('btn-prev'), next = document.getElementById('btn-next');
  if(prev) prev.classList.toggle('hidden', empty || loading);
  if(next) next.classList.toggle('hidden', empty || loading);
  document.getElementById('fab-edit')?.classList.toggle('hidden', loading);
}

async function findTrips(){
  const f = readRefine();
  const err = validateFilters(f);
  if(err){ rstatus(err); return; }
  rstatus('');
  appliedFilters = f; // preserved for Edit
  setChrome('loading');
  status('');
  try {
    const qs = filtersQS(f);
    const url = '/api/packages/recommended' + (qs ? qs + '&deck=1' : '?deck=1');
    const j = await (await fetch(url)).json();
    deck = j.packages || []; idx = 0; sessionStarted = true;
    await refreshState();
    showSwipe();
    if(!deck.length){
      const msg = j.empty_reason || 'Nothing in the catalogue fits these filters yet.';
      showEmpty('No trips match just yet.', msg);
      status('Tip: widen the budget or duration, or edit preferences and try again.');
    } else {
      if(j.note) status(j.note + (j.clarification ? ' ' + j.clarification : ''));
      else if(deck.length < 5)
        status(`Only ${deck.length} trip${deck.length > 1 ? 's' : ''} matched these filters — widen the budget or dates for more options.`);
      else status(`${deck.length} trips found — ‹ › to browse, ♥ to decide.` + (j.clarification ? ' ' + j.clarification : ''));
    }
    renderCard();
  } catch(e){ showSwipe(); setChrome('empty'); status('Could not load trips — check connection.'); showEmpty('Could not load trips.', 'Check your connection and try again.'); }
}

function current(){ return deck[idx]; }

function renderCard(){
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  if(!stack) return;
  stack.innerHTML = '';
  if(idx >= deck.length || deck.length === 0){
    if(deck.length === 0 && empty.classList.contains('hidden')) showEmpty('All caught up!', 'You have reviewed every package.');
    else empty.classList.remove('hidden');
    setChrome('empty'); updateArrows(); return;
  }
  empty.classList.add('hidden');
  setChrome('ready');
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
    <img src="${esc(p.cover_image || '')}" alt="${esc(p.destination||'trip')}" loading="lazy" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80&auto=format&fit=crop'" />
    <div class="info">
      <b>${esc(p.title||'Trip')}</b><br/>
      <span class="muted">${esc(p.destination||'')} · ${esc(p.duration_days||'?')} days · ₹${price} <span class="muted small">/ person</span></span><br/>
      <span class="muted small">by ${esc((p.operator&&p.operator.company_name)||'operator')}</span>
      ${p.operator && p.operator.is_verified && !p.is_demo && !(p.operator.company_name||'').includes('(demo)') ? '<span class="badge verified">✓ Verified</span>' : ''}
      ${p.is_demo ? '<span class="badge">Sample data</span>' : ''}
      ${p.availability_status ? `<span class="badge">${esc(p.availability_status)}</span>` : ''}<br/>
      <span class="badge">★ ${esc(p.match_score??'—')}</span>
      ${topReason?`<span class="muted small">Why this matches you: ${esc(topReason)}</span>`:''}
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

function showEmpty(title, text){
  const empty = document.getElementById('empty-state');
  if(!empty) return;
  const t = document.getElementById('empty-title'), x = document.getElementById('empty-text');
  if(t) t.textContent = title;
  if(x) x.textContent = text;
  empty.classList.remove('hidden');
  updateArrows();
}

function updateArrows(){
  const prev = document.getElementById('btn-prev'), next = document.getElementById('btn-next');
  if(prev) prev.disabled = idx <= 0;
  if(next) next.disabled = idx >= deck.length - 1 && deck.length > 0;
}
function syncActionStates(){
  const p = current();
  const likeBtn = document.getElementById('btn-like');
  if(likeBtn && p) { likeBtn.classList.toggle('active', likedSet.has(p.id)); likeBtn.textContent = likedSet.has(p.id) ? '♥' : '♡'; }
  const saveBtn = document.getElementById('btn-save');
  if(saveBtn && p) { saveBtn.classList.toggle('active', savedSet.has(p.id)); saveBtn.textContent = savedSet.has(p.id) ? '★ Saved' : '☆ Save'; }
}

function prev(){ if(idx > 0){ idx--; renderCard(); } }
function next(){ if(idx < deck.length - 1){ idx++; renderCard(); } else { status('End of list — edit preferences for more.'); } }

async function doPass(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const r = await fetch(`/api/packages/${p.id}/swipe`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({action:'pass'})});
    if(!r.ok) throw new Error('pass failed');
    status(`Passed ${p.destination}.`);
    deck.splice(idx, 1);
    if(idx >= deck.length) idx = Math.max(0, deck.length - 1);
    await refreshState(); renderCard();
  } catch(e){ status('Could not record pass. Check connection.'); }
  busy = false;
}
async function doInterested(){
  const p = current(); if(!p || busy) return; busy = true;
  try {
    const r = await fetch('/api/enquiries', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({package_id:p.id, num_travellers:2})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || 'enquiry failed');
    status(`♥ Interested in ${p.destination}! Enquiry ${j.enquiry.status} (#${j.enquiry.id}) — no charge, no booking yet.`);
    deck.splice(idx, 1);
    if(idx >= deck.length) idx = Math.max(0, deck.length - 1);
    await refreshState(); renderCard();
  } catch(e){ status('Could not create enquiry: ' + e.message); }
  busy = false;
}
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

function openDetail(){
  const p = current(); if(!p) return;
  const m = document.getElementById('detail-modal');
  const body = document.getElementById('dm-body');
  document.getElementById('dm-title').textContent = p.title || 'Trip';
  const price = Number(p.price||0).toLocaleString('en-IN');
  const demoBadge = p.is_demo ? '<span class="badge">Sample data — not live</span>' : '';
  const priceLabel = p.price_kind === 'demo_estimate' ? 'illustrative demo price' : (p.price_kind === 'confirmed' ? 'confirmed price' : (p.price_kind === 'operator_quote' ? 'operator quotation' : 'per-person estimate'));
  let breakdown = '<p>Detailed breakdown: Not provided — <b>needs operator confirmation</b>.</p>';
  if(p.price_breakdown){
    const b = p.price_breakdown;
    const row = (k,l)=>`<tr><td>${l}</td><td>₹${Number(b[k]||0).toLocaleString('en-IN')}</td></tr>`;
    breakdown = `<table class="table">${row('base','Base')}${row('accommodation','Stay')}${row('transport','Transport')}${row('meals','Meals')}${row('activities','Activities & entry')}${row('taxes','Taxes & charges')}<tr><td><b>Est. total / person</b></td><td><b>₹${price}</b></td></tr></table><p class="muted small">Illustrative demo split — not a final quote. Exclusions: ${esc((p.excluded||[]).join(', ')||'Not provided')}</p>`;
  }
  body.innerHTML = `
    <img src="${esc(p.cover_image||'')}" alt="" style="width:100%;border-radius:12px;max-height:280px;object-fit:cover" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80&auto=format&fit=crop'" />
    <p class="muted">${esc(p.destination||'')} · ${esc(p.duration_days||'?')} days${p.nights!=null?` / ${esc(p.nights)} nights`:''} · <b>₹${price}</b> / person <span class="muted small">(${priceLabel})</span> ${demoBadge}</p>
    <p><b>Operator:</b> ${esc((p.operator&&p.operator.company_name)||'Not provided')} ${p.operator&&p.operator.is_verified?'<span class="badge verified">✓ Verified</span>':''}</p>
    <p><b>Availability:</b> ${esc(p.availability_status||'Not provided')} ${p.seats_remaining!=null?`(${esc(p.seats_remaining)} seats)`:''}</p>
    <p><b>Why it matches:</b> ${esc(p.match_explanation||'Not provided')}</p>
    <p>${esc(p.short_desc||'Not provided')}</p>
    <h4>Itinerary</h4><p>${esc(p.itinerary||'Not provided')}</p>
    <div class="cols"><div><h4>Included</h4><p>${esc((p.included||[]).join(', ')||'Not provided')}</p>
    <h4>Excluded</h4><p>${esc((p.excluded||[]).join(', ')||'Not provided')}</p></div>
    <div><h4>Stay</h4><p>${esc(p.accommodation||'Not provided')}</p>
    <h4>Transport</h4><p>${esc(p.transportation||'Not provided')}</p>
    <h4>Dates</h4><p>${esc((p.departure_dates_list||[]).join(', ')||p.available_dates||'Not provided')}</p>
    <h4>Group</h4><p>${esc(p.group_size||'Not provided')} Capacity: ${esc(p.capacity??'Not provided')}</p></div></div>
    <h4>Cancellation</h4><p>${esc(p.cancellation_terms||'Unavailable — ask the operator before booking.')}</p>
    <h4>Price breakdown</h4>${breakdown}
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

let dragX = 0;
function enableDrag(el){
  let startX=0, startY=0, curX=0, dragging=false;
  const like = ()=>el.querySelector('.stamp.like'), nope = ()=>el.querySelector('.stamp.nope');
  const isModal = ()=>!document.getElementById('detail-modal').classList.contains('hidden');
  const down = (x,y)=>{ if(isModal()) return; dragging=true; startX=x; startY=y; el.style.transition=''; };
  const move = (x,y)=>{
    if(!dragging || isModal()) return;
    if(Math.abs(y-startY) > 60 && Math.abs(x-startX) < 20) return;
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

document.getElementById('btn-find')?.addEventListener('click', ()=>findTrips());
document.getElementById('fab-edit')?.addEventListener('click', showRefine);
document.getElementById('f-reset')?.addEventListener('click', async ()=>{
  ['f-destination','f-operator','f-min-price','f-max-price','f-min-dur','f-max-dur','f-accom','f-style','f-min-score','f-include','f-avoid','f-dates','f-group'].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=''; });
  setChecked('#f-landscape', []); setChecked('#f-styles', []);
  appliedFilters = {};
  await prefillFromProfile();
  rstatus('Filters reset to your saved preferences.');
});
document.querySelectorAll('#f-landscape input, #f-styles input').forEach(i=>{
  i.addEventListener('change', ()=>i.closest('.chip')?.classList.toggle('selected', i.checked));
});
document.getElementById('btn-edit-prefs')?.addEventListener('click', showRefine);
document.getElementById('empty-edit')?.addEventListener('click', showRefine);
document.getElementById('empty-clear')?.addEventListener('click', ()=>{
  appliedFilters = {};
  showRefine();
});
document.getElementById('btn-prev')?.addEventListener('click', prev);
document.getElementById('btn-next')?.addEventListener('click', next);
document.getElementById('btn-pass')?.addEventListener('click', doPass);
document.getElementById('btn-interested')?.addEventListener('click', doInterested);
document.getElementById('btn-like')?.addEventListener('click', doLike);
document.getElementById('btn-save')?.addEventListener('click', doSave);
document.getElementById('btn-detail')?.addEventListener('click', openDetail);
document.getElementById('dm-close')?.addEventListener('click', closeDetail);
document.getElementById('detail-modal')?.addEventListener('click', e=>{ if(e.target.id==='detail-modal') closeDetail(); });
document.getElementById('btn-share')?.addEventListener('click', doShare);
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
  if(document.getElementById('swipe-screen').classList.contains('hidden')) return;
  if(e.key==='ArrowRight') next();
  if(e.key==='ArrowLeft') prev();
});
// init: refine screen only — no package fetch until Find my trips
showRefine();
prefillFromProfile();
refreshState();
