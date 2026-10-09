// Shared VYBE helpers (flash + polling-safe fetch).
async function vybeFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
