// Shared VYBE helpers (flash + polling-safe fetch).
async function vybeFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Header favourite/saved counts (liked vs saved kept separate).
async function refreshNavCounts() {
  const likeEl = document.getElementById('nav-like-count');
  const saveEl = document.getElementById('nav-save-count');
  if (!likeEl && !saveEl) return;
  try {
    const j = await (await fetch('/api/interests/counts')).json();
    if (likeEl) {
      const n = j.like || 0;
      likeEl.textContent = n;
      likeEl.classList.toggle('hidden', n <= 0);
    }
    if (saveEl) {
      const n = j.save || 0;
      saveEl.textContent = n;
      saveEl.classList.toggle('hidden', n <= 0);
    }
  } catch (e) { /* anonymous users have no counts */ }
}
document.addEventListener('DOMContentLoaded', refreshNavCounts);
window.refreshNavCounts = refreshNavCounts;
