/* ============================================================
   CineBook — admin.js
   Admin-role specific JavaScript
   ============================================================ */
"use strict";

/* ── Admin Movies Page ───────────────────────────────────── */
function initAdminMoviesPage() {
  const searchInput = document.getElementById('movieSearch');
  if (!searchInput) return;

  // Genre / language filter dropdowns (client-side live filter within page)
  const genreFilter = document.getElementById('genreFilter');
  const langFilter  = document.getElementById('langFilter');

  function applyAdminMovieFilter() {
    const q = (searchInput.value || '').toLowerCase().trim();
    const g = (genreFilter?.value || '').toLowerCase().trim();
    const l = (langFilter?.value  || '').toLowerCase().trim();
    document.querySelectorAll('#moviesTable tbody tr').forEach(row => {
      const text = row.textContent.toLowerCase();
      const match = (!q || text.includes(q))
                 && (!g || text.includes(g))
                 && (!l || text.includes(l));
      row.style.display = match ? '' : 'none';
    });
  }

  searchInput.addEventListener('input', applyAdminMovieFilter);
  genreFilter?.addEventListener('change', applyAdminMovieFilter);
  langFilter?.addEventListener('change',  applyAdminMovieFilter);
}

/* ── Admin Theaters Page ─────────────────────────────────── */
function initAdminTheatersPage() {
  const filterState = document.getElementById('filterState');
  const filterCity  = document.getElementById('filterCity');
  const addState    = document.getElementById('add_state');
  const addCity     = document.getElementById('add_city');
  const etState     = document.getElementById('et_state');
  const etCity      = document.getElementById('et_city');

  // Only run on the theaters page
  if (!filterState && !addState) return;

  const urlParams = new URLSearchParams(window.location.search);
  const curState  = urlParams.get('state') || '';
  const curCity   = urlParams.get('city')  || '';

  // ── Filter bar dropdowns ──
  if (filterState) {
    populateStateSelect(filterState, curState, 'All States');
    if (curState && filterCity) {
      populateCitySelect(filterCity, curState, curCity, 'All Cities');
      filterCity.disabled = false;
    }
    filterState.addEventListener('change', function () {
      const s = this.value;
      if (s) {
        if (filterCity) { populateCitySelect(filterCity, s, '', 'All Cities'); filterCity.disabled = false; }
      } else {
        if (filterCity) { filterCity.innerHTML = '<option value="">All Cities</option>'; filterCity.disabled = true; }
      }
      this.closest('form').submit();
    });
    filterCity?.addEventListener('change', function () { this.closest('form').submit(); });
  }

  // Owner/Brand dropdowns auto-submit the filter form
  document.querySelector('select[name="owner_id"]')?.addEventListener('change', function() { this.closest('form').submit(); });
  document.querySelector('select[name="brand_id"]')?.addEventListener('change', function() { this.closest('form').submit(); });

  // ── Add Theater modal dropdowns ──
  if (addState) {
    populateStateSelect(addState);
    addState.addEventListener('change', function () {
      if (this.value) {
        if (addCity) { populateCitySelect(addCity, this.value); addCity.disabled = false; }
      } else {
        if (addCity) { addCity.innerHTML = '<option value="">-- Select City --</option>'; addCity.disabled = true; }
      }
    });
  }

  // ── Edit Theater modal dropdowns ──
  if (etState) {
    populateStateSelect(etState);
    etState.addEventListener('change', function () {
      if (this.value) {
        if (etCity) { populateCitySelect(etCity, this.value); etCity.disabled = false; }
      } else {
        if (etCity) { etCity.innerHTML = '<option value="">Select City</option>'; etCity.disabled = true; }
      }
    });
  }
}

/* ── Override editTheater to also populate city dropdown ── */
function _adminEditTheaterSetup(id, data) {
  const form = document.getElementById('editTheaterForm');
  if (!form) return;
  form.action = '/admin/theaters/edit/' + id;

  const nameEl  = document.getElementById('et_name');
  const brandEl = document.getElementById('et_brand');
  const ownerEl = document.getElementById('et_owner');
  const locEl   = document.getElementById('et_location');
  const stateEl = document.getElementById('et_state');
  const cityEl  = document.getElementById('et_city');

  if (nameEl)  nameEl.value  = data.name     || '';
  if (brandEl) brandEl.value = data.brand_id || '';
  if (ownerEl) ownerEl.value = data.owner_id || '';
  if (locEl)   locEl.value   = data.location || '';

  // Re-populate state select fresh with correct selected value
  if (stateEl) {
    populateStateSelect(stateEl, data.state || '');
  }

  // Re-populate city select for theater's current state
  if (cityEl) {
    if (data.state) {
      populateCitySelect(cityEl, data.state, data.city || '');
      cityEl.disabled = false;
    } else {
      cityEl.innerHTML = '<option value="">Select City</option>';
      cityEl.disabled = true;
    }
  }

  bootstrap.Modal.getOrCreateInstance(document.getElementById('editTheaterModal')).show();
}

/* ── Admin Bookings Page ─────────────────────────────────── */
function initAdminBookingsPage() {
  const statusFilter = document.getElementById('statusFilter');
  const dateFilter   = document.getElementById('dateFilter');
  if (!statusFilter && !dateFilter) return;

  function filterBookingTable() {
    const status = statusFilter?.value || '';
    document.querySelectorAll('#bookingsTable tbody tr').forEach(row => {
      const badge = row.querySelector('.badge-pill');
      const rowStatus = badge ? badge.textContent.trim() : '';
      const matchStatus = !status || rowStatus === status;
      row.style.display = matchStatus ? '' : 'none';
    });
  }

  statusFilter?.addEventListener('change', filterBookingTable);
  dateFilter?.addEventListener('change', filterBookingTable);

  // Init location selector for state/city filter
  initLocationSelector({ stateSelect: '#filter_state', citySelect: '#filter_city', areaSelect: null });
}

/* ── Admin Users Page ────────────────────────────────────── */
function initAdminUsersPage() {
  const inp = document.getElementById('userSearch');
  const tbl = document.getElementById('usersTable');
  if (!inp || !tbl) return;
  inp.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    tbl.querySelectorAll('tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ── Confirm delete helper for admin pages ───────────────── */
function adminConfirmDelete(url, csrfToken, reloadOnSuccess) {
  if (!confirm('Are you sure? This cannot be undone.')) return;
  fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': csrfToken || '' } })
    .then(r => r.json())
    .then(d => {
      showToast(d.message || 'Deleted', 'success');
      if (reloadOnSuccess) setTimeout(() => location.reload(), 800);
    })
    .catch(() => showToast('Delete failed', 'danger'));
}



/* ── Boot admin page-specific inits on DOMContentLoaded ─── */
document.addEventListener('DOMContentLoaded', async function () {
  // Wait for DB_LOCATIONS to be populated by main.js
  await loadLocationsFromDB();
  
  initAdminMoviesPage();
  initAdminTheatersPage();
  initAdminBookingsPage();
  initAdminUsersPage();
});


async function admOnBrandChange() {
  const brandId = document.getElementById('adm_assign_brand').value;
  const stateEl = document.getElementById('adm_assign_state');
  const container = document.getElementById('admAssignList');

  // clear UI
  container.innerHTML = `<div class="text-center text-muted py-4">
    Select State to load theaters
  </div>`;

  if (!brandId) {
    stateEl.innerHTML = '<option value="">Select State</option>';
    stateEl.disabled = true;
    return;
  }

  const res = await fetch(`/admin/api/brand-states?brand_id=${brandId}`);
  const states = await res.json();

  stateEl.innerHTML = '<option value="">Select State</option>';
  states.forEach(s => {
    stateEl.innerHTML += `<option value="${s}">${s}</option>`;
  });

  stateEl.disabled = false;
}


async function admOnStateChange() {
  const brandId = document.getElementById('adm_assign_brand').value;
  const state = document.getElementById('adm_assign_state').value;
  const cityEl = document.getElementById('adm_assign_city');
  const container = document.getElementById('admAssignList');

  if (!state) {
    cityEl.innerHTML = '<option value="">Select City</option>';
    cityEl.disabled = true;

    container.innerHTML = `<div class="text-center text-muted py-4">
      Select State to load cities
    </div>`;
    return;
  }

  // ✅ CALL CORRECT API (cities, NOT theaters)
  const res = await fetch(`/admin/api/brand-cities?brand_id=${brandId}&state=${state}`);
  const cities = await res.json();

  cityEl.innerHTML = '<option value="">Select City</option>';

  if (!cities.length) {
    cityEl.disabled = true;
    container.innerHTML = `<div class="text-center text-muted py-4">
      No cities found
    </div>`;
    return;
  }

  cities.forEach(c => {
    cityEl.innerHTML += `<option value="${c}">${c}</option>`;
  });

  cityEl.disabled = false;

  // Clear theaters until city is selected
  container.innerHTML = `<div class="text-center text-muted py-4">
    Select City to load theaters
  </div>`;
}



// Track selected theater IDs across city/state changes


async function admOnCityChange() {
  const brandId = document.getElementById('adm_assign_brand').value;
  const state   = document.getElementById('adm_assign_state').value;
  const city    = document.getElementById('adm_assign_city').value;

  const res = await fetch(`/admin/api/brand-theaters?brand_id=${brandId}&state=${state}&city=${city}`);
  const theaters = await res.json();

  const container = document.getElementById('admAssignList');
  container.innerHTML = '';

  if (!theaters.length) {
    container.innerHTML = `<div class="text-center text-muted py-4">No theaters found in this city</div>`;
    return;
  }

  theaters.forEach(t => {
    const checked = ADM_SELECTED_IDS.has(String(t.theater_id));
    container.innerHTML += `
      <div class="col-md-6 col-lg-4 adm-assign-item">
        <label class="d-block p-3 adm-theater-card"
          style="border:1px solid ${checked ? '#e50914' : 'transparent'};
                 background:${checked ? 'rgba(229,9,20,0.06)' : ''};
                 border-radius:10px;cursor:pointer;transition:all 0.15s">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <div style="color:#fff;font-weight:600">${t.name}</div>
              <div style="font-size:0.75rem;color:#aaa">${t.brand}</div>
              <div style="font-size:0.75rem;color:#aaa">${t.city}, ${t.state}</div>
            </div>
            <input type="checkbox"
              class="adm-theater-cb"
              name="theater_ids"
              value="${t.theater_id}"
              ${checked ? 'checked' : ''}>
          </div>
          <div style="font-size:0.75rem;color:#888;margin-top:5px">
            ${t.screens} screen(s)
          </div>
        </label>
      </div>
    `;
  });

  admUpdateCount();
}

// Update ADM_SELECTED_IDS on every checkbox change
document.addEventListener('change', e => {
  if (!e.target.classList.contains('adm-theater-cb')) return;
  const id = String(e.target.value);
  if (e.target.checked) {
    ADM_SELECTED_IDS.add(id);
  } else {
    ADM_SELECTED_IDS.delete(id);
  }
  admHighlight(e.target);
  admUpdateCount();
});