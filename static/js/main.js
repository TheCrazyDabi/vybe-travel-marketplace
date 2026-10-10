// Shared VYBE helpers (flash + polling-safe fetch).
async function vybeFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Header saved-count badge (likes + saves combined) + liked badge.
async function refreshNavCounts() {
  try {
    const j = await (await fetch('/api/interests/counts')).json();
    const savedEl = document.getElementById('nav-saved-count') || document.getElementById('nav-save-count');
    if (savedEl) {
      const n = (j.like || 0) + (j.save || 0);
      savedEl.textContent = n;
      savedEl.classList.toggle('hidden', n <= 0);
    }
    const likeEl = document.getElementById('nav-like-count');
    if (likeEl) {
      const n = j.like || 0;
      likeEl.textContent = n;
      likeEl.classList.toggle('hidden', n <= 0);
    }
  } catch (e) { /* anonymous users have no counts */ }
}
document.addEventListener('DOMContentLoaded', refreshNavCounts);
window.refreshNavCounts = refreshNavCounts;

// PWA-ready: register the service worker (no-op at runtime, enables future install).
window.addEventListener('load', () => {
  try {
    if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  } catch (_) {}
});

// Top-right overflow (⋮) menu: smooth open, close on select / outside / Esc.
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('nav-more-btn');
  const menu = document.getElementById('nav-more-menu');
  if (!btn || !menu) return;
  let hideTimer = null;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isOpen = () => menu.classList.contains('open');
  const close = (refocus) => {
    if (!isOpen() && menu.classList.contains('hidden')) return;
    menu.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
    clearTimeout(hideTimer);
    if (reduced) { menu.classList.add('hidden'); }
    else { hideTimer = setTimeout(() => { if (!isOpen()) menu.classList.add('hidden'); }, 180); }
    if (refocus) { try { btn.focus({ preventScroll: true }); } catch (_) { btn.focus(); } }
  };
  const open = () => {
    clearTimeout(hideTimer);
    menu.classList.remove('hidden');
    void menu.offsetWidth;
    menu.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
  };
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isOpen()) close();
    else open();
  });
  menu.addEventListener('click', (e) => {
    if (e.target.closest('a')) close();
    e.stopPropagation();
  });
  document.addEventListener('click', () => close());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(true); });
});
