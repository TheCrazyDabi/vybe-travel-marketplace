// Shared VYBE helpers (flash + polling-safe fetch).
async function vybeFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Unified navbar count and user interest preloader (single request)
async function refreshNavCounts() {
  try {
    const savedEl = document.getElementById('nav-saved-count') || document.getElementById('nav-save-count');
    const likeEl = document.getElementById('nav-like-count');
    const res = await fetch('/api/interests');
    if (res.ok) {
      const j = await res.json();
      const interests = j.interests || [];
      const likes = interests.filter(i => i.action === 'like');
      const saves = interests.filter(i => i.action === 'save');
      window.likedSet = new Set(likes.map(i => i.package_id));
      window.savedSet = new Set(saves.map(i => i.package_id));
      if (savedEl) {
        const n = likes.length + saves.length;
        savedEl.textContent = n;
        savedEl.classList.toggle('hidden', n <= 0);
      }
      if (likeEl) {
        const n = likes.length;
        likeEl.textContent = n;
        likeEl.classList.toggle('hidden', n <= 0);
      }
    }
  } catch (e) { /* anonymous users */ }
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

// ==========================================================================
// Unified Package Details Modal & Bottom-Sheet Behavior
// ==========================================================================
(function() {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function fmtDate(d) {
    if (!d) return null;
    try {
      const dt = new Date(d);
      if (isNaN(dt.getTime())) return String(d);
      return dt.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (_) { return String(d); }
  }

  let activeModalPkg = null;
  let activeModalOpts = {};
  let originalUrl = null;

  window.closePackageModal = function(opts = {}) {
    const modal = document.getElementById('pkg-detail-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    activeModalPkg = null;

    if (opts.revertUrl !== false && originalUrl && window.location.href !== originalUrl) {
      if (window.history.state && window.history.state.packageModal) {
        window.history.back();
      } else {
        window.history.replaceState(null, '', originalUrl);
      }
    }
    originalUrl = null;
  };

  window.openPackageModal = async function(pkgOrId, opts = {}) {
    const modal = document.getElementById('pkg-detail-modal');
    const body = document.getElementById('pdm-body');
    const headerTitle = document.getElementById('pdm-header-title');
    if (!modal || !body) return;

    activeModalOpts = opts;
    if (!originalUrl) originalUrl = window.location.href;

    // Show initial loading state if given an ID
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    let pkg = typeof pkgOrId === 'object' ? pkgOrId : null;
    if (!pkg) {
      headerTitle.textContent = 'Loading trip details...';
      body.innerHTML = '<div style="text-align:center; padding:40px 20px; color:var(--color-text-muted);">Loading complete package information…</div>';
      try {
        const res = await vybeFetch(`/api/packages/${pkgOrId}`);
        pkg = res.package;
      } catch (err) {
        body.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger);">Unable to load package: ${esc(err.message)}<br><br><button type="button" class="btn small ghost" onclick="window.closePackageModal()">Close</button></div>`;
        return;
      }
    }

    activeModalPkg = pkg;
    renderPackageDetail(pkg);

    // If initial pkg was from card summary, asynchronously refresh complete database record
    if (typeof pkgOrId === 'object' && pkg.id) {
      vybeFetch(`/api/packages/${pkg.id}`).then(res => {
        if (res.package && activeModalPkg && activeModalPkg.id === pkg.id) {
          activeModalPkg = res.package;
          renderPackageDetail(res.package, { preserveScroll: true });
        }
      }).catch(() => {});
    }

    // Preserve URL & history so device back button cleanly closes sheet
    if (opts.syncUrl !== false && window.history && window.history.pushState) {
      const targetUrl = `/packages/${pkg.id}`;
      if (window.location.pathname !== targetUrl) {
        window.history.pushState({ packageModal: pkg.id }, '', targetUrl);
      }
    }
  };

  function renderPackageDetail(p, renderOpts = {}) {
    const body = document.getElementById('pdm-body');
    const headerTitle = document.getElementById('pdm-header-title');
    if (!body) return;

    const scrollPos = renderOpts.preserveScroll ? body.scrollTop : 0;
    headerTitle.textContent = p.title || 'Trip Details';

    const priceNum = Number(p.price || 0);
    const priceStr = priceNum.toLocaleString('en-IN');
    const isExpired = p.status === 'expired' || (p.valid_until && new Date(p.valid_until) < new Date());
    const isSoldOut = (p.seats_remaining != null && p.seats_remaining <= 0);
    const isBookable = !isExpired && !isSoldOut && p.is_active !== false;

    // Badges
    let statusBadge = '';
    if (isExpired) {
      statusBadge = '<span class="badge" style="background:#b91c1c; color:#fff; font-weight:700;">● Expired / Booking Closed</span>';
    } else if (isSoldOut) {
      statusBadge = '<span class="badge" style="background:#d97706; color:#fff; font-weight:700;">● Sold Out</span>';
    } else {
      const seatsText = p.seats_remaining != null ? `${p.seats_remaining} seats remaining` : 'Available';
      statusBadge = `<span class="badge verified" style="font-weight:700;">● ${esc(seatsText)}</span>`;
    }

    const demoBadge = p.is_demo ? '<span class="badge">Sample data</span>' : '';
    const operatorName = (p.operator && p.operator.company_name) || 'Independent Operator';
    const operatorVerified = p.operator && p.operator.is_verified && !p.is_demo && !(p.operator.company_name || '').includes('(demo)');
    const operatorBadge = operatorVerified ? '<span class="badge verified">✓ Verified</span>' : '';

    // Gallery thumbnails
    let galleryHtml = '';
    const allImages = [p.cover_image, ...(p.images || [])].filter(Boolean);
    const uniqueImages = [...new Set(allImages)];
    if (uniqueImages.length > 1) {
      galleryHtml = `<div class="pdm-thumbs-row">
        ${uniqueImages.map(img => `<img src="${esc(img)}" alt="" class="pdm-thumb-img" onclick="document.getElementById('pdm-main-img').src='${esc(img)}'" onerror="this.style.display='none'" />`).join('')}
      </div>`;
    }

    // Dates & Validity
    const tripStartFmt = fmtDate(p.trip_start_date);
    const tripEndFmt = fmtDate(p.trip_end_date);
    let tripDatesText = p.available_dates || 'Flexible departures';
    if (tripStartFmt && tripEndFmt) {
      tripDatesText = `${tripStartFmt} – ${tripEndFmt}`;
    } else if (p.departure_dates_list && p.departure_dates_list.length) {
      tripDatesText = p.departure_dates_list.join(', ');
    }

    const bookingDeadlineFmt = fmtDate(p.booking_deadline);
    const validUntilFmt = fmtDate(p.valid_until);

    // TruePrice breakdown table
    let breakdownHtml = '';
    if (p.price_breakdown && typeof p.price_breakdown === 'object') {
      const b = p.price_breakdown;
      const row = (lbl, key) => (b[key] != null ? `<tr><td>${lbl}</td><td>₹${Number(b[key] || 0).toLocaleString('en-IN')}</td></tr>` : '');
      breakdownHtml = `
        <div class="pdm-section">
          <div class="pdm-section-title">Price Breakdown (TruePrice)</div>
          <table class="table" style="margin:6px 0;">
            ${row('Base package', 'base')}
            ${row('Stay / Accommodation', 'accommodation')}
            ${row('Transport & transfers', 'transport')}
            ${row('Meals & dining', 'meals')}
            ${row('Activities & entry permits', 'activities')}
            ${row('Taxes & service fees', 'taxes')}
            <tr style="border-top:2px solid var(--color-accent-border);">
              <td><b>Total / person</b></td>
              <td><b>₹${priceStr}</b></td>
            </tr>
          </table>
          <p class="muted small" style="margin:4px 0 0;">${p.price_kind === 'demo_estimate' ? 'Illustrative demo split — confirm with operator.' : 'Verified price estimate per person.'}</p>
        </div>`;
    }

    // Inclusions & Exclusions
    const incList = Array.isArray(p.included) ? p.included : [];
    const excList = Array.isArray(p.excluded) ? p.excluded : [];

    body.innerHTML = `
      <div class="pdm-hero-wrap">
        <img id="pdm-main-img" class="pdm-hero-img" src="${esc(p.cover_image || '')}" alt="${esc(p.destination || 'Trip')}" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80&auto=format&fit=crop'" />
      </div>
      ${galleryHtml}

      <h2 class="pdm-title">${esc(p.title || 'Trip')}</h2>
      <div class="pdm-subline">
        📍 <b>${esc(p.destination || '')}</b> · ⏱ <b>${esc(p.duration_days || '?')} days${p.nights != null ? ` / ${esc(p.nights)} nights` : ''}</b> · <span class="pdm-price-tag">₹${priceStr}</span> <span class="muted small">/ person</span>
      </div>

      <div class="pdm-badges-row">
        ${statusBadge}
        ${operatorBadge}
        ${demoBadge}
        ${p.match_score ? `<span class="badge">★ ${esc(p.match_score)}% Match</span>` : ''}
      </div>

      ${p.short_desc ? `<p style="font-size:15px; line-height:1.5; margin-bottom:16px;">${esc(p.short_desc)}</p>` : ''}

      <div class="pdm-meta-grid">
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Operator</span>
          <span class="pdm-meta-val">${esc(operatorName)}</span>
        </div>
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Travel Dates</span>
          <span class="pdm-meta-val">${esc(tripDatesText)}</span>
        </div>
        ${bookingDeadlineFmt ? `
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Booking Deadline</span>
          <span class="pdm-meta-val">${esc(bookingDeadlineFmt)}</span>
        </div>` : ''}
        ${validUntilFmt ? `
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Listing Validity</span>
          <span class="pdm-meta-val">${esc(validUntilFmt)}</span>
        </div>` : ''}
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Group Size & Capacity</span>
          <span class="pdm-meta-val">${esc(p.group_size || 'Flexible')} ${p.capacity != null ? `(Capacity: ${esc(p.capacity)})` : ''}</span>
        </div>
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Stay / Accommodation</span>
          <span class="pdm-meta-val">${esc(p.accommodation || 'Not specified')}</span>
        </div>
        <div class="pdm-meta-item">
          <span class="pdm-meta-label">Transport</span>
          <span class="pdm-meta-val">${esc(p.transportation || 'Not specified')}</span>
        </div>
      </div>

      ${p.itinerary ? `
      <div class="pdm-section">
        <div class="pdm-section-title">Complete Itinerary</div>
        <p style="white-space:pre-line; line-height:1.6; margin:0;">${esc(p.itinerary)}</p>
      </div>` : ''}

      <div class="cols" style="margin-bottom:14px;">
        <div class="pdm-section" style="margin:0;">
          <div class="pdm-section-title" style="color:var(--color-success);">✓ Included Services</div>
          ${incList.length ? `<ul class="pdm-pill-list">${incList.map(item => `<li class="pdm-pill-item inc">✓ ${esc(item)}</li>`).join('')}</ul>` : '<p class="muted small" style="margin:0;">Not specified</p>'}
        </div>
        <div class="pdm-section" style="margin:0;">
          <div class="pdm-section-title" style="color:var(--color-danger);">✕ Excluded Services</div>
          ${excList.length ? `<ul class="pdm-pill-list">${excList.map(item => `<li class="pdm-pill-item exc">✕ ${esc(item)}</li>`).join('')}</ul>` : '<p class="muted small" style="margin:0;">None listed</p>'}
        </div>
      </div>

      ${breakdownHtml}

      ${p.cancellation_terms ? `
      <div class="pdm-section">
        <div class="pdm-section-title">Cancellation Policy</div>
        <p class="muted small" style="margin:0; line-height:1.5;">${esc(p.cancellation_terms)}</p>
      </div>` : ''}

      <p id="pdm-status-msg" class="muted small" style="text-align:center; min-height:18px; margin:10px 0 0;" role="status"></p>
    `;

    if (renderOpts.preserveScroll) {
      body.scrollTop = scrollPos;
    }

    // Configure Sticky Actions
    syncModalActionButtons(p, isBookable, isExpired);
  }

  function syncModalActionButtons(p, isBookable, isExpired) {
    const btnInterested = document.getElementById('pdm-btn-interested');
    const btnLike = document.getElementById('pdm-btn-like');
    const btnSave = document.getElementById('pdm-btn-save');
    const btnChat = document.getElementById('pdm-btn-chat');
    const statusMsg = document.getElementById('pdm-status-msg');

    // 1. Interested / Send Enquiry
    if (btnInterested) {
      if (isExpired) {
        btnInterested.disabled = true;
        btnInterested.textContent = 'Listing Expired';
        btnInterested.classList.remove('primary');
        btnInterested.classList.add('ghost');
      } else if (!isBookable) {
        btnInterested.disabled = true;
        btnInterested.textContent = 'Sold Out';
        btnInterested.classList.remove('primary');
        btnInterested.classList.add('ghost');
      } else {
        btnInterested.disabled = false;
        btnInterested.textContent = '♥ Send Enquiry / Interested';
        btnInterested.classList.add('primary');
        btnInterested.classList.remove('ghost');
        btnInterested.onclick = async (e) => {
          e.preventDefault();
          e.stopPropagation();
          btnInterested.disabled = true;
          btnInterested.textContent = 'Sending enquiry…';
          try {
            const res = await vybeFetch('/api/enquiries', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ package_id: p.id, num_travellers: 2 })
            });
            btnInterested.textContent = '✓ Enquiry Sent';
            if (statusMsg) {
              statusMsg.textContent = `Enquiry recorded (#${res.enquiry?.id || ''}) — no upfront payment required. Track in My trips!`;
            }
            if (typeof activeModalOpts.onInterested === 'function') {
              activeModalOpts.onInterested(p);
            }
          } catch (err) {
            btnInterested.disabled = false;
            btnInterested.textContent = '♥ Send Enquiry / Interested';
            if (statusMsg) statusMsg.textContent = `Could not send enquiry: ${err.message}`;
          }
        };
      }
    }

    // 2. Favourites (Like)
    if (btnLike) {
      const isLiked = window.likedSet && window.likedSet.has(p.id);
      btnLike.textContent = isLiked ? '♥ Liked' : '♡ Favourite';
      btnLike.classList.toggle('active', !!isLiked);
      btnLike.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          const currentlyLiked = btnLike.classList.contains('active') || btnLike.textContent.includes('Liked');
          const method = currentlyLiked ? 'DELETE' : 'POST';
          await fetch(`/api/packages/${p.id}/like`, { method });
          const newLiked = !currentlyLiked;
          btnLike.textContent = newLiked ? '♥ Liked' : '♡ Favourite';
          btnLike.classList.toggle('active', newLiked);
          if (window.likedSet) {
            if (newLiked) window.likedSet.add(p.id); else window.likedSet.delete(p.id);
          }
          if (window.refreshNavCounts) window.refreshNavCounts();
          if (typeof activeModalOpts.onLike === 'function') activeModalOpts.onLike(p, newLiked);
        } catch (_) {}
      };
    }

    // 3. Save (Bookmark)
    if (btnSave) {
      const isSaved = window.savedSet && window.savedSet.has(p.id);
      btnSave.textContent = isSaved ? '★ Saved' : '☆ Save';
      btnSave.classList.toggle('active', !!isSaved);
      btnSave.onclick = async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          const currentlySaved = btnSave.classList.contains('active') || btnSave.textContent.includes('Saved');
          const method = currentlySaved ? 'DELETE' : 'POST';
          await fetch(`/api/packages/${p.id}/save`, { method });
          const newSaved = !currentlySaved;
          btnSave.textContent = newSaved ? '★ Saved' : '☆ Save';
          btnSave.classList.toggle('active', newSaved);
          if (window.savedSet) {
            if (newSaved) window.savedSet.add(p.id); else window.savedSet.delete(p.id);
          }
          if (window.refreshNavCounts) window.refreshNavCounts();
          if (typeof activeModalOpts.onSave === 'function') activeModalOpts.onSave(p, newSaved);
        } catch (_) {}
      };
    }

    // 4. Operator Chat
    if (btnChat) {
      if (p.operator && p.operator.id) {
        btnChat.classList.remove('hidden');
        btnChat.onclick = async (e) => {
          e.preventDefault();
          try {
            const res = await vybeFetch('/api/conversations', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ company_id: p.operator.id, package_id: p.id })
            });
            if (res.conversation && res.conversation.id) {
              window.location.href = `/chats/${res.conversation.id}`;
            }
          } catch (_) {
            window.location.href = `/chats`;
          }
        };
      } else {
        btnChat.classList.add('hidden');
      }
    }
  }

  // Bind close buttons and keyboard Esc
  document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('pkg-detail-modal');
    if (!modal) return;

    document.getElementById('pdm-close-btn')?.addEventListener('click', (e) => {
      e.preventDefault();
      window.closePackageModal();
    });

    document.getElementById('pdm-back-btn')?.addEventListener('click', (e) => {
      e.preventDefault();
      window.closePackageModal();
    });

    // Close when tapping modal backdrop outside card
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        window.closePackageModal();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
        window.closePackageModal();
      }
    });

    // Browser back button support
    window.addEventListener('popstate', () => {
      if (!modal.classList.contains('hidden')) {
        window.closePackageModal({ revertUrl: false });
      }
    });

    // Delegated click handling for all package cards and links across Explore, Saved, Dashboard, etc.
    document.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      const link = e.target.closest('a[href^="/packages/"]');
      if (!link) return;
      // Do not intercept if inside the modal itself or if it's an operator edit/delete action
      if (link.closest('#pdm-body') || link.closest('.pkg-modal-header') || link.closest('.pkg-modal-actions')) return;
      if (link.getAttribute('target') === '_blank') return;
      const m = link.getAttribute('href').match(/\/packages\/(\d+)(?:[?#]|$)/);
      if (m && m[1]) {
        // If already on this exact package standalone page, allow default navigation
        if (window.location.pathname === `/packages/${m[1]}`) return;
        e.preventDefault();
        window.openPackageModal(parseInt(m[1], 10));
      }
    });
  });
})();
