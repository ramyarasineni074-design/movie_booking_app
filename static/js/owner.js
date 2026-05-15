/* ============================================================
   CineBook — owner.js
   Owner-role specific JavaScript
   ============================================================ */
"use strict";

/* ── Theater screen fields builder (Add Theater modal) ───── */
function buildOwnerScreenFields() {
  const numEl = document.getElementById('ownerNumScreens');
  const container = document.getElementById('ownerScreenFields');
  if (!numEl || !container) return;

  const n = parseInt(numEl.value) || 1;
  let html = '<div class="row g-2">';
  for (let i = 1; i <= n; i++) {
    html += `<div class="col-12"><div class="row g-2 align-items-center mb-1">
      <div class="col-1 text-center" style="color:var(--text-muted);font-size:0.8rem">${i}</div>
      <div class="col-6"><input type="text" name="screen_name_${i}" class="form-control" value="Screen ${i}"></div>
      <div class="col-5"><input type="number" name="capacity_${i}" class="form-control" placeholder="Capacity" value="150"></div>
    </div></div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

/* ── Open edit theater modal ─────────────────────────────── */
function openEditTheater(id, data) {
  const form = document.getElementById('editTheaterForm');
  if (form) form.action = `/owner/theaters/edit/${id}`;
  const nameEl  = document.getElementById('oet_name');
  const addrEl  = document.getElementById('oet_address');
  const stateEl = document.getElementById('oet_state');
  const cityEl  = document.getElementById('oet_city');
  const areaEl  = document.getElementById('oet_area');
  if (nameEl) nameEl.value = data.name || '';
  if (addrEl) addrEl.value = data.address || '';
  if (stateEl) {
    populateStateSelect(stateEl, data.state || '');
    if (data.state && cityEl) {
      populateCitySelect(cityEl, data.state, data.city || '');
      cityEl.disabled = false;
      if (data.city && areaEl) {
        populateAreaSelect(areaEl, data.state, data.city, data.location || '');
        areaEl.disabled = false;
      }
    }
    stateEl.addEventListener('change', function () {
      if (cityEl) { populateCitySelect(cityEl, this.value); cityEl.disabled = !this.value; }
      if (areaEl) { areaEl.innerHTML = '<option value="">Select Area</option>'; areaEl.disabled = true; }
    });
    if (cityEl) {
      cityEl.addEventListener('change', function () {
        if (areaEl) { populateAreaSelect(areaEl, stateEl.value, this.value); areaEl.disabled = !this.value; }
      });
    }
  }
  new bootstrap.Modal(document.getElementById('editTheaterModal')).show();
}

/* ── Set theater for Add Show modal ──────────────────────── */
function setShowTheater(theaterId, theaterName) {
  const idEl   = document.getElementById('showTheaterId');
  const nameEl = document.getElementById('showTheaterName');
  const screenSel = document.getElementById('showScreenSelect');
  if (idEl)   idEl.value = theaterId;
  if (nameEl) nameEl.textContent = theaterName;

  // Populate screens for this theater
  if (screenSel && window.THEATER_SCREENS) {
    const screens = window.THEATER_SCREENS[theaterId] || [];
    screenSel.innerHTML = '<option value="">-- Select Screen --</option>';
    screens.forEach(s => {
      const opt = new Option(s.name, s.id);
      screenSel.appendChild(opt);
    });
  }
}

/* ── Set theater for Add Movie modal ─────────────────────── */
function setMovieTheater(theaterId, theaterName) {
  const idEl   = document.getElementById('movieTheaterId');
  const nameEl = document.getElementById('movieTheaterName');
  const screenSel = document.getElementById('movieScreenSelect');
  if (idEl)   idEl.value = theaterId;
  if (nameEl) nameEl.textContent = theaterName;

  // Populate screens for this theater
  if (screenSel && window.THEATER_SCREENS) {
    const screens = window.THEATER_SCREENS[theaterId] || [];
    screenSel.innerHTML = '<option value="">-- Select Screen --</option>';
    screens.forEach(s => {
      const opt = new Option(s.name, s.id);
      screenSel.appendChild(opt);
    });
  }
}

/* ── Owner Theaters page filter ──────────────────────────── */
function applyTheaterFilters() {
  const state = document.querySelector('#filter_state')?.value || '';
  const city  = document.querySelector('#filter_city')?.value  || '';
  const area  = document.querySelector('#filter_area')?.value  || '';
  document.querySelectorAll('#theaterGrid [data-theater]').forEach(card => {
    const matches = (!state || card.dataset.state === state) &&
                    (!city  || card.dataset.city  === city)  &&
                    (!area  || (card.dataset.area || '').toLowerCase().includes(area.toLowerCase()));
    card.style.display = matches ? '' : 'none';
  });
}

/* ── Owner Shows page search ─────────────────────────────── */
function initOwnerShowsSearch() {
  const inp = document.getElementById('showSearch');
  if (!inp) return;
  inp.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('#showsTable tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ── Owner Bookings page search ──────────────────────────── */
function initOwnerBookingsSearch() {
  const inp = document.getElementById('bookingSearch');
  if (!inp) return;
  inp.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('#bookingsTable tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ── DOMContentLoaded ────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async function () {
  // Wait for locations to load first
  await loadLocationsFromDB();

  // Theaters page
  if (document.getElementById('theaterGrid')) {
    // NOTE: #filter_state / #filter_city are server-rendered with correct options
    // and pre-selected values — do NOT call initLocationSelector on them or it
    // will overwrite options from DB_LOCATIONS and break the server-side filter.
    // Modal add/edit selects still need initLocationSelector:
    initLocationSelector({ stateSelect: '#ot_state',  citySelect: '#ot_city',  areaSelect: '#ot_area'  });
    initLocationSelector({ stateSelect: '#oet_state', citySelect: '#oet_city', areaSelect: '#oet_area' });
    buildOwnerScreenFields();
  }

  // Shows page
  if (document.getElementById('showsTable')) {
    initLocationSelector({ stateSelect: '#filter_state', citySelect: '#filter_city', areaSelect: null });
  }

  // Shows search
  initOwnerShowsSearch();

  // Bookings search
  initOwnerBookingsSearch();
});