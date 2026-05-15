/* ============================================================
   CineBook — main.js
   ============================================================ */
"use strict";

/* ── Toast ──────────────────────────────────────────────── */
function showToast(msg, type = 'success') {
  const icons = { success:'fa-check-circle', danger:'fa-times-circle',
                  warning:'fa-exclamation-triangle', info:'fa-info-circle' };
  const t = document.createElement('div');
  t.className = `alert alert-${type} toast-custom d-flex align-items-center gap-2`;
  t.innerHTML = `<i class="fas ${icons[type]||icons.info}"></i><span>${msg}</span>`;
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.animation = 'slideUp 0.3s ease reverse';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

/* ── DB Locations (state → cities from /api/locations) ── */
let DB_LOCATIONS = {};

async function loadLocationsFromDB() {
  try {
    const res = await fetch('/api/locations');
    if (res.ok) {
      DB_LOCATIONS = await res.json();
      return;
    }
  } catch (e) { /* fall through to fallback */ }

  // Static fallback so page still works if API is down
  DB_LOCATIONS = {
    "Andhra Pradesh":["Visakhapatnam","Vijayawada","Guntur","Tirupati","Kurnool","Nellore"],
    "Telangana":["Hyderabad","Warangal","Nizamabad","Karimnagar"],
    "Maharashtra":["Mumbai","Pune","Nagpur","Nashik","Aurangabad"],
    "Karnataka":["Bengaluru","Mysuru","Hubli","Mangaluru"],
    "Tamil Nadu":["Chennai","Coimbatore","Madurai","Tiruchirappalli","Salem"],
    "Delhi":["New Delhi","North Delhi","South Delhi","East Delhi","West Delhi"],
    "Gujarat":["Ahmedabad","Surat","Vadodara","Rajkot"],
    "Rajasthan":["Jaipur","Jodhpur","Udaipur","Ajmer","Kota"],
    "Uttar Pradesh":["Lucknow","Kanpur","Agra","Noida","Varanasi"],
    "West Bengal":["Kolkata","Siliguri","Durgapur","Asansol"],
    "Punjab":["Ludhiana","Amritsar","Jalandhar","Bathinda"],
    "Bihar":["Patna","Gaya","Muzaffarpur","Bhagalpur"],
    "Madhya Pradesh":["Bhopal","Indore","Gwalior","Jabalpur","Ujjain"],
    "Kerala":["Thiruvananthapuram","Kochi","Kozhikode","Thrissur"]
  };
}

/* ── Populate a state <select> from DB_LOCATIONS ───────── */
function populateStateSelect(el, selectedState='', placeholder='-- Select State --') {
  if (!el) return;
  el.innerHTML = `<option value="">${placeholder}</option>`;
  Object.keys(DB_LOCATIONS).sort().forEach(state => {
    const opt = new Option(state, state);
    if (state === selectedState) opt.selected = true;
    el.appendChild(opt);
  });
}

/* ── Populate a city <select> for a given state ─────────── */
function populateCitySelect(cityEl, state, selectedCity='', placeholder='-- Select City --') {
  if (!cityEl) return;
  cityEl.innerHTML = `<option value="">${placeholder}</option>`;
  const cities = DB_LOCATIONS[state] || [];
  if (!cities.length) { cityEl.disabled = true; return; }
  cities.sort().forEach(city => {
    const opt = new Option(city, city);
    if (city === selectedCity) opt.selected = true;
    cityEl.appendChild(opt);
  });
  cityEl.disabled = false;
}

/* ── DB Areas (state+city → areas from /api/areas) ── */
let DB_AREAS = {};

async function loadAreasFromDB() {
  try {
    const res = await fetch('/api/areas');
    if (res.ok) { DB_AREAS = await res.json(); }
  } catch (e) { /* silent fail */ }
}

function populateAreaSelect(areaEl, state, city, selectedArea='') {
  if (!areaEl) return;
  areaEl.innerHTML = '<option value="">-- Select Area --</option>';
  const key = `${state}|${city}`;
  const areas = DB_AREAS[key] || [];
  if (!areas.length) { areaEl.disabled = true; return; }
  areas.sort().forEach(area => {
    const opt = new Option(area, area);
    if (area === selectedArea) opt.selected = true;
    areaEl.appendChild(opt);
  });
  areaEl.disabled = false;
}

/* ── City picker (navbar modal) ─────────────────────────── */
function initCityPicker() {
  const btn     = document.getElementById('cityPickerBtn');
  const modalEl = document.getElementById('cityModal');
  if (!btn || !modalEl) return;

  const modal   = new bootstrap.Modal(modalEl);
  btn.addEventListener('click', () => modal.show());

  const $state  = document.getElementById('modal_state');
  const $city   = document.getElementById('modal_city');

  // Populate states NOW (DB_LOCATIONS is already loaded when this runs)
  populateStateSelect($state);

  $state?.addEventListener('change', function() {
    populateCitySelect($city, this.value);
  });

  document.getElementById('saveCityBtn')?.addEventListener('click', function() {
    const city = $city?.value;
    if (!city) { showToast('Please select a city', 'warning'); return; }

    fetch('/set-city', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ city })
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const badge = document.getElementById('currentCity');
        if (badge) badge.textContent = city;
        modal.hide();
        location.reload();
      } else {
        showToast('Could not save city', 'danger');
      }
    })
    .catch(() => showToast('Network error', 'danger'));
  });
}

/* ── Theater filter (movie detail page) ─────────────────── */
function initTheaterFilter() {
  const $state = document.getElementById('filter_state');
  const $city  = document.getElementById('filter_city');
  if (!$state) return;

  populateStateSelect($state);

  $state.addEventListener('change', function() {
    populateCitySelect($city, this.value);
    applyTheaterFilters();
  });
  $city?.addEventListener('change', applyTheaterFilters);
}

function applyTheaterFilters() {
  const state = document.getElementById('filter_state')?.value || '';
  const city  = document.getElementById('filter_city')?.value  || '';

  let visible = 0;
  document.querySelectorAll('[data-theater]').forEach(card => {
    const tState = card.dataset.state || '';
    const tCity  = card.dataset.city  || '';
    const match  = (!state || tState === state) && (!city || tCity === city);
    card.style.display = match ? '' : 'none';
    if (match) visible++;
  });

  const emptyEl = document.getElementById('noTheaterMsg');
  if (emptyEl) emptyEl.style.display = visible === 0 ? '' : 'none';
}

/* ── Password toggle ────────────────────────────────────── */
function togglePassword(inputId, iconId) {
  const inp = document.getElementById(inputId);
  const ico = document.getElementById(iconId);
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
  if (ico) ico.className = inp.type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
}

/* ── Forgot password ────────────────────────────────────── */
function submitForgotPassword() {
  const email  = document.getElementById('forgotEmail')?.value?.trim();
  const msgDiv = document.getElementById('forgotMsg');
  if (!email) {
    if (msgDiv) msgDiv.innerHTML = '<div class="alert alert-danger py-2">Email is required</div>';
    return;
  }
  const fd = new FormData(); fd.append('email', email);
  fetch('/forgot-password', { method:'POST', body:fd })
    .then(r => r.json())
    .then(d => {
      if (msgDiv) msgDiv.innerHTML =
        `<div class="alert alert-${d.success?'success':'danger'} py-2">${d.message}</div>`;
    })
    .catch(() => {
      if (msgDiv) msgDiv.innerHTML = '<div class="alert alert-danger py-2">Something went wrong</div>';
    });
}

/* ── Admin table search ──────────────────────────────────── */
function initTableSearch(inputId, tableId) {
  const input = document.getElementById(inputId);
  const table = document.getElementById(tableId);
  if (!input || !table) return;
  input.addEventListener('input', function() {
    const q = this.value.toLowerCase();
    table.querySelectorAll('tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
}

/* ── Image preview ───────────────────────────────────────── */
function previewImage(inputEl, previewId) {
  const file = inputEl.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const preview = document.getElementById(previewId);
    if (preview) { preview.src = e.target.result; preview.style.display = 'block'; }
  };
  reader.readAsDataURL(file);
}

/* ── Admin helpers ───────────────────────────────────────── */
function confirmDelete(url, csrfToken, cb) {
  if (!confirm('Are you sure? This cannot be undone.')) return;
  fetch(url, { method:'DELETE', headers:{'X-CSRFToken': csrfToken||''} })
    .then(r => r.json())
    .then(d => { showToast(d.message||'Deleted', 'success'); if(cb) cb(); })
    .catch(() => showToast('Delete failed', 'danger'));
}

function postAction(url, body, cb) {
  fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) })
    .then(r => r.json())
    .then(d => { showToast(d.message||'Done', 'success'); if(cb) cb(d); })
    .catch(() => showToast('Request failed', 'danger'));
}

/* ── Sidebar toggle (admin / owner) ─────────────────────── */
function initSidebar() {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.querySelector('.admin-sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('show');
      if (overlay) overlay.classList.toggle('d-none');
    });
  }
  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar?.classList.remove('show');
      overlay.classList.add('d-none');
    });
  }
}

/* ── Partner form state/city selects ────────────────────── */
function initPartnerForm() {
  const stateEl = document.getElementById('partnerState');
  const cityEl  = document.getElementById('partnerCity');
  if (!stateEl) return;
  populateStateSelect(stateEl);
  stateEl.addEventListener('change', function() {
    populateCitySelect(cityEl, this.value);
  });
}

/* ── DOMContentLoaded — boot everything ─────────────────── */
document.addEventListener('DOMContentLoaded', async function() {
  // 1. Load locations first (await so dropdowns can fill immediately)
  await loadLocationsFromDB();
  await loadAreasFromDB();

  // 2. Sidebar (admin/owner)
  initSidebar();

  // 3. City picker modal
  initCityPicker();

  // 4. Theater filter (movie detail page)
  if (document.getElementById('filter_state')) {
    initTheaterFilter();
  }

  // 5. Partner form
  initPartnerForm();

  // 6. Admin table searches
  initTableSearch('movieSearch',   'moviesTable');
  initTableSearch('theaterSearch', 'theatersTable');
  initTableSearch('bookingSearch', 'bookingsTable');
  initTableSearch('userSearch',    'usersTable');

  // 8. Language/genre round-robin rotation on movie cards
  initCardLabelRotation();

  // 7. Auto-dismiss flash alerts after 4 s
  setTimeout(() => {
    document.querySelectorAll('.alert-dismissible').forEach(el => {
      bootstrap.Alert.getOrCreateInstance(el)?.close();
    });
  }, 4000);
});



/* ── Location Selector (owner pages) ── */
function initLocationSelector({ stateSelect, citySelect, areaSelect }) {
  const stateEl = document.querySelector(stateSelect);
  const cityEl  = document.querySelector(citySelect);
  const areaEl  = areaSelect ? document.querySelector(areaSelect) : null;
  if (!stateEl) return;

  populateStateSelect(stateEl);

  stateEl.addEventListener('change', function() {
    if (cityEl) {
      populateCitySelect(cityEl, this.value);
      cityEl.disabled = !this.value;
    }
    if (areaEl) {
      areaEl.innerHTML = '<option value="">-- Select Area --</option>';
      areaEl.disabled = true;
    }
  });

  if (cityEl) {
    cityEl.addEventListener('change', function() {
      if (areaEl) {
        populateAreaSelect(areaEl, stateEl.value, this.value);
        areaEl.disabled = !this.value;
      }
    });
  }
}
/* ── Language / Genre round-robin rotation on movie cards ── */
/*
 * Each .movie-card that has data-languages and/or data-genres attributes
 * will cycle through all languages and genres in order — never repeating
 * until the full list is exhausted — so the audience sees variety across
 * the card grid rather than every card saying "Action · Bengali".
 *
 * Usage in template:
 *   data-languages="Hindi,Telugu,Tamil"
 *   data-genres="Action,Drama,Thriller"
 */
function initCardLabelRotation() {
  // Collect all unique languages and genres from every card on the page
  const allLangs  = [];
  const allGenres = [];
  const seenLang  = new Set();
  const seenGenre = new Set();

  document.querySelectorAll('.movie-card[data-languages]').forEach(card => {
    card.dataset.languages.split(',').forEach(l => {
      const t = l.trim();
      if (t && !seenLang.has(t)) { seenLang.add(t); allLangs.push(t); }
    });
  });
  document.querySelectorAll('.movie-card[data-genres]').forEach(card => {
    card.dataset.genres.split(',').forEach(g => {
      const t = g.trim();
      if (t && !seenGenre.has(t)) { seenGenre.add(t); allGenres.push(t); }
    });
  });

  // Nothing to rotate if no data attributes present
  if (!allLangs.length && !allGenres.length) return;

  let langIdx  = 0;
  let genreIdx = 0;

  document.querySelectorAll('.movie-card').forEach(card => {
    const langEl  = card.querySelector('.lang-inline');
    const genreEl = card.querySelector('.genre-tag');

    // Per-card languages — pick the next language from the card's own list
    // using a global pointer so adjacent cards show different languages
    if (langEl) {
      const cardLangs = (card.dataset.languages || '')
        .split(',').map(l => l.trim()).filter(Boolean);
      const pool = cardLangs.length ? cardLangs : allLangs;
      if (pool.length) {
        langEl.textContent = pool[langIdx % pool.length];
        langIdx++;
      }
    }

    if (genreEl) {
      const cardGenres = (card.dataset.genres || '')
        .split(',').map(g => g.trim()).filter(Boolean);
      const pool = cardGenres.length ? cardGenres : allGenres;
      if (pool.length) {
        genreEl.textContent = pool[genreIdx % pool.length];
        genreIdx++;
      }
    }
  });
}