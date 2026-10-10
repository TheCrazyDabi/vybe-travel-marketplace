// Shared VYBE helpers (flash + polling-safe fetch).
async function vybeFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Header saved-count badge (likes + saves combined).
async function refreshNavCounts() {
  const el = document.getElementById('nav-saved-count');
  if (!el) return;
  try {
    const j = await (await fetch('/api/interests/counts')).json();
    const n = (j.like || 0) + (j.save || 0);
    el.textContent = n;
    el.classList.toggle('hidden', n <= 0);
  } catch (e) { /* anonymous users have no counts */ }
}
document.addEventListener('DOMContentLoaded', refreshNavCounts);
window.refreshNavCounts = refreshNavCounts;
