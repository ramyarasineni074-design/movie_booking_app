/* ============================================================
   CineBook — user.js
   User-role specific JavaScript
   ============================================================ */
"use strict";

/* ── User Movies Page — live client-side filter ──────────── */
function initUserMoviesPage() {
  const searchInput = document.getElementById('searchInput');
  const genreSelect = document.getElementById('genreSelect');
  const langSelect  = document.getElementById('langSelect');
  const liveCount   = document.getElementById('liveCount');
  const shownCount  = document.getElementById('shownCount');

  if (!searchInput && !genreSelect) return;

  function applyLiveFilter() {
    const q = (searchInput?.value  || '').toLowerCase().trim();
    const g = (genreSelect?.value  || '').toLowerCase().trim();
    const l = (langSelect?.value   || '').toLowerCase().trim();
    let shown = 0;
    document.querySelectorAll('.movie-item').forEach(card => {
      const ok = (!q || card.dataset.title.includes(q))
              && (!g || card.dataset.genre.includes(g))
              && (!l || card.dataset.language.includes(l));
      card.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    if (liveCount)  liveCount.textContent  = shown;
    if (shownCount) shownCount.textContent = shown;
  }

  searchInput?.addEventListener('input',  applyLiveFilter);
  genreSelect?.addEventListener('change', applyLiveFilter);
  langSelect?.addEventListener('change',  applyLiveFilter);

  // Run once on load to apply any pre-filled filters
  applyLiveFilter();
}

/* ── Seat Selection Page ─────────────────────────────────── */
function initSeatSelection() {
  // Disabled — seat_selection.html handles everything
  return;
}

/* ── My Bookings search ──────────────────────────────────── */
function initMyBookingsSearch() {
  const inp = document.getElementById('bookingSearchUser');
  if (!inp) return;
  inp.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.booking-card').forEach(card => {
      card.style.display = card.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ── DOMContentLoaded ────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  initUserMoviesPage();
  initSeatSelection();
  initMyBookingsSearch();
  // NOTE: selectMethod() is defined and initialised in payment.html's
  // own <script> block. Do NOT call it here — this file runs on every
  // user page and 'el' would be undefined, crashing the JS engine.
});