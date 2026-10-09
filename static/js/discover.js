// VYBE swipe deck: mouse + touch + buttons, posts to /api/packages/<id>/swipe.
let deck = [], idx = 0;

async function loadDeck() {
  const status = document.getElementById('swipe-status');
  try {
    const j = await (await fetch('/api/packages/recommended')).json();
    deck = j.packages || []; idx = 0;
    status.textContent = deck.length ? `${deck.length} trips for your VYBE` : '';
    renderCard();
  } catch (e) { status.textContent = 'Could not load trips. Are you logged in?'; }
}

function renderCard() {
  const stack = document.getElementById('card-stack');
  const empty = document.getElementById('empty-state');
  stack.innerHTML = '';
  if (idx >= deck.length) { empty.classList.remove('hidden'); return; }
  empty.classList.add('hidden');
  const p = deck[idx];
  const el = document.createElement('div');
  el.className = 'swipe-card';
  el.innerHTML = `
    <img src="${p.cover_image || ''}" alt="${p.destination}" />
    <div class="info">
      <b>${p.title}</b><br/>
      <span class="muted">${p.destination} · ${p.duration_days} days · ₹${Number(p.price).toLocaleString('en-IN')}</span><br/>
      <span class="badge">★ ${p.match_score} match</span>
      ${p.operator && p.operator.is_verified ? '<span class="badge verified">✓ Verified</span>' : ''}
      <p class="muted small">${(p.match_reasons || []).join(' · ')}</p>
    </div>`;
  el.addEventListener('click', (e) => { if (Math.abs(dragX) < 8) location.href = `/packages/${p.id}`; });
  enableDrag(el);
  stack.appendChild(el);
}

let dragX = 0;
function enableDrag(el) {
  let startX = 0, curX = 0, dragging = false;
  const down = (x) => { dragging = true; startX = x; };
  const move = (x) => { if (!dragging) return; curX = x - startX; dragX = curX; el.style.transform = `translateX(${curX}px) rotate(${curX / 18}deg)`; };
  const up = () => { if (!dragging) return; dragging = false;
    if (curX > 90) swipe('like'); else if (curX < -90) swipe('pass');
    else { el.style.transform = ''; dragX = 0; } curX = 0; };
  el.addEventListener('mousedown', (e) => down(e.clientX));
  window.addEventListener('mousemove', (e) => move(e.clientX));
  window.addEventListener('mouseup', up);
  el.addEventListener('touchstart', (e) => down(e.touches[0].clientX), {passive: true});
  el.addEventListener('touchmove', (e) => move(e.touches[0].clientX), {passive: true});
  el.addEventListener('touchend', up);
}

async function swipe(action) {
  const p = deck[idx];
  if (!p) return;
  document.getElementById('swipe-status').textContent = action === 'like' ? `♥ Interested in ${p.destination}!` : `Skipped ${p.destination}`;
  try {
    await fetch(`/api/packages/${p.id}/swipe`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action})});
  } catch (e) { /* offline still advances */ }
  idx++; dragX = 0; renderCard();
}

document.getElementById('btn-like')?.addEventListener('click', () => swipe('like'));
document.getElementById('btn-pass')?.addEventListener('click', () => swipe('pass'));
document.getElementById('btn-detail')?.addEventListener('click', () => { if (deck[idx]) location.href = `/packages/${deck[idx].id}`; });
loadDeck();
