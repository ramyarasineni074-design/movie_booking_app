/**
 * form_validations.js
 * Comprehensive client-side validations for CineBook Admin/Owner/User forms.
 * Include this file in base.html files so it loads on every page.
 */

/* ─────────────────────────────────────────────────────────────
   UTILITY HELPERS
───────────────────────────────────────────────────────────── */

function showError(input, message) {
  clearError(input);
  input.classList.add('is-invalid');
  const div = document.createElement('div');
  div.className = 'invalid-feedback cv-error';
  div.style.cssText = 'display:block;font-size:0.78rem;color:#e50914;margin-top:3px';
  div.innerHTML = '<i class="fas fa-exclamation-circle me-1"></i>' + message;
  // Insert after the input's parent if it's inside an input-group, else after input
  const parent = input.closest('.input-group') || input;
  parent.insertAdjacentElement('afterend', div);
}

function clearError(input) {
  input.classList.remove('is-invalid');
  input.classList.remove('is-valid');
  const parent = input.closest('.input-group') || input;
  const existing = parent.nextElementSibling;
  if (existing && existing.classList.contains('cv-error')) existing.remove();
}

function markValid(input) {
  clearError(input);
  input.classList.add('is-valid');
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

function isValidPhone(phone) {
  return /^[6-9]\d{9}$/.test(phone.trim());
}

function isValidUrl(url) {
  try { new URL(url); return true; } catch { return false; }
}

/* ─────────────────────────────────────────────────────────────
   GENERIC FORM BLOCKER
   Prevents submit until all required fields pass.
───────────────────────────────────────────────────────────── */
function attachRequiredGuard(form) {
  form.addEventListener('submit', function (e) {
    let valid = true;
    form.querySelectorAll('[required]').forEach(function (el) {
      if (el.type === 'checkbox') {
        if (!el.checked) { showError(el, 'This checkbox is required.'); valid = false; }
        else markValid(el);
      } else {
        const val = el.value.trim();
        if (!val) { showError(el, 'This field is required.'); valid = false; }
        else markValid(el);
      }
    });
    if (!valid) { e.preventDefault(); e.stopPropagation(); scrollToFirstError(form); }
  });
}

function scrollToFirstError(form) {
  const first = form.querySelector('.is-invalid');
  if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ─────────────────────────────────────────────────────────────
   ① LOGIN FORM  (#loginForm or action ends with /login)
───────────────────────────────────────────────────────────── */
function initLoginValidation() {
  const form = document.querySelector('form[action*="/login"]');
  if (!form) return;
  form.addEventListener('submit', function (e) {
    let ok = true;
    const email = form.querySelector('[name="email"]');
    const pwd   = form.querySelector('[name="password"]');

    if (!email || !email.value.trim()) {
      showError(email, 'Email address is required.'); ok = false;
    } else if (!isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    } else markValid(email);

    if (!pwd || !pwd.value.trim()) {
      showError(pwd, 'Password is required.'); ok = false;
    } else if (pwd.value.length < 4) {
      showError(pwd, 'Password must be at least 4 characters.'); ok = false;
    } else markValid(pwd);

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ② REGISTER FORM
───────────────────────────────────────────────────────────── */
function initRegisterValidation() {
  const form = document.querySelector('form[action*="/register"]');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const name    = form.querySelector('[name="name"]');
    const email   = form.querySelector('[name="email"]');
    const phone   = form.querySelector('[name="phone"]');
    const dob     = form.querySelector('[name="dob"]');
    const pwd     = form.querySelector('[name="password"], #regPwd');
    const confirm = form.querySelector('[name="confirm_password"], #regConfirm');
    const terms   = form.querySelector('#agreeTerms');

    if (!name || !name.value.trim()) {
      showError(name, 'Full name is required.'); ok = false;
    } else if (name.value.trim().length < 2) {
      showError(name, 'Name must be at least 2 characters.'); ok = false;
    } else markValid(name);

    if (!email || !email.value.trim()) {
      showError(email, 'Email address is required.'); ok = false;
    } else if (!isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    } else markValid(email);

    if (phone && phone.value.trim()) {
      if (!isValidPhone(phone.value)) {
        showError(phone, 'Enter a valid 10-digit Indian mobile number.'); ok = false;
      } else markValid(phone);
    }

    if (dob && dob.value) {
      const age = (new Date() - new Date(dob.value)) / (1000 * 60 * 60 * 24 * 365.25);
      if (age < 5) { showError(dob, 'Please enter a valid date of birth.'); ok = false; }
      else markValid(dob);
    }

    if (!pwd || !pwd.value.trim()) {
      showError(pwd, 'Password is required.'); ok = false;
    } else if (pwd.value.length < 6) {
      showError(pwd, 'Password must be at least 6 characters.'); ok = false;
    } else markValid(pwd);

    if (confirm) {
      if (!confirm.value.trim()) {
        showError(confirm, 'Please confirm your password.'); ok = false;
      } else if (pwd && confirm.value !== pwd.value) {
        showError(confirm, 'Passwords do not match.'); ok = false;
      } else markValid(confirm);
    }

    if (terms && !terms.checked) {
      showError(terms, 'You must agree to the Terms of Service.'); ok = false;
    }

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ③ ADD OWNER MODAL  (#addOwnerModal)
───────────────────────────────────────────────────────────── */
function initAddOwnerValidation() {
  const modal = document.getElementById('addOwnerModal');
  if (!modal) return;
  const form = modal.querySelector('form');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const name      = form.querySelector('[name="name"]');
    const email     = form.querySelector('[name="email"]');
    const brandName = form.querySelector('[name="brand_name"]');
    const brandId   = form.querySelector('[name="brand_id"]');

    if (!name || !name.value.trim()) {
      showError(name, "Owner's full name is required."); ok = false;
    } else if (name.value.trim().length < 2) {
      showError(name, 'Name must be at least 2 characters.'); ok = false;
    } else markValid(name);

    if (!email || !email.value.trim()) {
      showError(email, 'Email address is required.'); ok = false;
    } else if (!isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    } else markValid(email);

    // Brand: either new name or existing selection is fine; neither is also fine (optional)
    if (brandName && brandId) {
      const hasNew = brandName.value.trim().length > 0;
      const hasExisting = brandId.value.trim().length > 0;
      if (hasNew && hasExisting) {
        showError(brandName, 'Please provide either a new brand name OR select an existing brand, not both.');
        ok = false;
      } else {
        if (brandName) clearError(brandName);
      }
    }

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });

  // Live clear on input
  ['name','email','brand_name'].forEach(function(n) {
    const el = form.querySelector('[name="' + n + '"]');
    if (el) el.addEventListener('input', function() { clearError(this); });
  });
}

/* ─────────────────────────────────────────────────────────────
   ④ EDIT OWNER MODAL
───────────────────────────────────────────────────────────── */
function initEditOwnerValidation() {
  const form = document.getElementById('editOwnerForm');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const name  = form.querySelector('[name="name"]');
    const email = form.querySelector('[name="email"]');

    if (!name || !name.value.trim()) {
      showError(name, 'Name is required.'); ok = false;
    } else markValid(name);

    if (!email || !email.value.trim()) {
      showError(email, 'Email is required.'); ok = false;
    } else if (!isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    } else markValid(email);

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑤ ADD THEATER MODAL  (#addTheaterModal)
───────────────────────────────────────────────────────────── */
function initAddTheaterValidation() {
  const modal = document.getElementById('addTheaterModal');
  if (!modal) return;
  const form = modal.querySelector('form');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const name    = form.querySelector('[name="name"]');
    const state   = form.querySelector('[name="state"], #add_state');
    const city    = form.querySelector('[name="city"], #add_city');
    const screens = form.querySelector('[name="num_screens"]');

    if (!name || !name.value.trim()) {
      showError(name, 'Theater name is required.'); ok = false;
    } else markValid(name);

    if (state && !state.value) {
      showError(state, 'Please select a state.'); ok = false;
    } else if (state) markValid(state);

    if (city && !city.value) {
      showError(city, 'Please select a city.'); ok = false;
    } else if (city) markValid(city);

    if (screens && (isNaN(parseInt(screens.value)) || parseInt(screens.value) < 1)) {
      showError(screens, 'Number of screens must be at least 1.'); ok = false;
    } else if (screens) markValid(screens);

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑥ ADD MOVIE MODAL  (#addMovieModal)
───────────────────────────────────────────────────────────── */
function initAddMovieValidation() {
  const modal = document.getElementById('addMovieModal');
  if (!modal) return;
  const form = modal.querySelector('form');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const title    = form.querySelector('[name="title"]');
    const duration = form.querySelector('[name="duration"]');
    const rating   = form.querySelector('[name="rating"]');
    const posterUrl= form.querySelector('[name="poster_url"]');

    if (!title || !title.value.trim()) {
      showError(title, 'Movie title is required.'); ok = false;
    } else markValid(title);

    if (duration && duration.value) {
      if (parseInt(duration.value) < 1 || parseInt(duration.value) > 600) {
        showError(duration, 'Duration must be between 1 and 600 minutes.'); ok = false;
      } else markValid(duration);
    }

    if (rating && rating.value) {
      const r = parseFloat(rating.value);
      if (isNaN(r) || r < 0 || r > 10) {
        showError(rating, 'Rating must be between 0 and 10.'); ok = false;
      } else markValid(rating);
    }

    if (posterUrl && posterUrl.value.trim() && !isValidUrl(posterUrl.value.trim())) {
      showError(posterUrl, 'Please enter a valid URL (starting with https://).'); ok = false;
    }

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑦ ADD SHOW FORM (owner shows page)
───────────────────────────────────────────────────────────── */
function initAddShowValidation() {
  // Could be in a modal or inline — handle both
  const forms = document.querySelectorAll('form[action*="/shows/add"], form[action*="/add_show"]');
  forms.forEach(function(form) {
    form.addEventListener('submit', function (e) {
      let ok = true;

      const movieId    = form.querySelector('[name="movie_id"]');
      const theaterId  = form.querySelector('[name="theater_id"]');
      const screenId   = form.querySelector('[name="screen_id"]');
      const showDate   = form.querySelector('[name="show_date"]');
      const startTime  = form.querySelector('[name="start_time"]');
      const price      = form.querySelector('[name="price"]');

      if (movieId && !movieId.value.trim()) {
        showError(movieId, 'Please select a movie.'); ok = false;
      } else if (movieId) markValid(movieId);

      if (theaterId && !theaterId.value.trim()) {
        showError(theaterId, 'Please select a theater.'); ok = false;
      } else if (theaterId) markValid(theaterId);

      if (screenId && (!screenId.value || screenId.disabled)) {
        showError(screenId, 'Please select a screen (choose theater first).'); ok = false;
      } else if (screenId && screenId.value) markValid(screenId);

      if (!showDate || !showDate.value) {
        showError(showDate, 'Show date is required.'); ok = false;
      } else {
        const today = new Date(); today.setHours(0,0,0,0);
        if (new Date(showDate.value) < today) {
          showError(showDate, 'Show date cannot be in the past.'); ok = false;
        } else markValid(showDate);
      }

      if (!startTime || !startTime.value) {
        showError(startTime, 'Start time is required.'); ok = false;
      } else markValid(startTime);

      if (!price || !price.value || parseFloat(price.value) < 1) {
        showError(price, 'Ticket price must be at least ₹1.'); ok = false;
      } else markValid(price);

      if (!ok) { e.preventDefault(); scrollToFirstError(form); }
    });
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑧ CONTACT FORM
───────────────────────────────────────────────────────────── */
function initContactValidation() {
  const form = document.querySelector('form[action*="/contact"]');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const name    = form.querySelector('[name="name"]');
    const email   = form.querySelector('[name="email"]');
    const subject = form.querySelector('[name="subject"]');
    const message = form.querySelector('[name="message"]');

    if (!name || !name.value.trim()) {
      showError(name, 'Your name is required.'); ok = false;
    } else markValid(name);

    if (!email || !email.value.trim()) {
      showError(email, 'Email address is required.'); ok = false;
    } else if (!isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    } else markValid(email);

    if (!subject || !subject.value.trim()) {
      showError(subject, 'Subject is required.'); ok = false;
    } else markValid(subject);

    if (!message || !message.value.trim()) {
      showError(message, 'Message cannot be empty.'); ok = false;
    } else if (message.value.trim().length < 10) {
      showError(message, 'Message must be at least 10 characters.'); ok = false;
    } else markValid(message);

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑨ CHANGE PASSWORD FORM
───────────────────────────────────────────────────────────── */
function initChangePasswordValidation() {
  const form = document.querySelector('form[action*="/change-password"], form[action*="/change_password"]');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const oldPwd  = form.querySelector('[name="old_password"], [name="current_password"]');
    const newPwd  = form.querySelector('[name="new_password"]');
    const confirm = form.querySelector('[name="confirm_password"], [name="confirm_new_password"]');

    if (oldPwd && !oldPwd.value.trim()) {
      showError(oldPwd, 'Current password is required.'); ok = false;
    } else if (oldPwd) markValid(oldPwd);

    if (!newPwd || !newPwd.value.trim()) {
      showError(newPwd, 'New password is required.'); ok = false;
    } else if (newPwd.value.length < 6) {
      showError(newPwd, 'New password must be at least 6 characters.'); ok = false;
    } else markValid(newPwd);

    if (!confirm || !confirm.value.trim()) {
      showError(confirm, 'Please confirm your new password.'); ok = false;
    } else if (newPwd && confirm.value !== newPwd.value) {
      showError(confirm, 'Passwords do not match.'); ok = false;
    } else if (confirm) markValid(confirm);

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑩ PARTNER APPLICATION FORM
───────────────────────────────────────────────────────────── */
function initPartnerValidation() {
  const form = document.querySelector('form[action*="/partner"], form[action*="/partnership"]');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    let ok = true;
    const required = form.querySelectorAll('[required]');
    required.forEach(function(el) {
      if (!el.value.trim()) {
        showError(el, 'This field is required.'); ok = false;
      } else markValid(el);
    });

    const email = form.querySelector('[name="email"], [type="email"]');
    if (email && email.value.trim() && !isValidEmail(email.value)) {
      showError(email, 'Please enter a valid email address.'); ok = false;
    }

    const phone = form.querySelector('[name="phone"]');
    if (phone && phone.value.trim() && !isValidPhone(phone.value)) {
      showError(phone, 'Enter a valid 10-digit Indian mobile number.'); ok = false;
    }

    if (!ok) { e.preventDefault(); scrollToFirstError(form); }
  });
}

/* ─────────────────────────────────────────────────────────────
   ⑪ FORGOT PASSWORD MODAL (inline JS button submit)
   Patch the existing submitForgotPassword() if present.
───────────────────────────────────────────────────────────── */
function initForgotPasswordValidation() {
  // Override the submitForgotPassword that exists in login.html
  window._cvForgotPatched = true;
  const origFn = window.submitForgotPassword;
  window.submitForgotPassword = function () {
    const emailEl = document.getElementById('forgotEmail');
    if (!emailEl) return origFn && origFn();
    const msgEl   = document.getElementById('forgotMsg');
    if (!emailEl.value.trim()) {
      if (msgEl) msgEl.innerHTML = '<div class="alert alert-danger py-2 mb-2"><i class="fas fa-exclamation-circle me-1"></i>Please enter your email address.</div>';
      emailEl.focus();
      return;
    }
    if (!isValidEmail(emailEl.value)) {
      if (msgEl) msgEl.innerHTML = '<div class="alert alert-danger py-2 mb-2"><i class="fas fa-exclamation-circle me-1"></i>Please enter a valid email address.</div>';
      emailEl.focus();
      return;
    }
    if (msgEl) msgEl.innerHTML = '';
    origFn && origFn();
  };
}

/* ─────────────────────────────────────────────────────────────
   ⑫ LIVE INPUT CLEARING (removes red as user types)
───────────────────────────────────────────────────────────── */
function initLiveClear() {
  document.addEventListener('input', function (e) {
    const el = e.target;
    if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
      if (el.classList.contains('is-invalid')) clearError(el);
    }
  }, true);
  document.addEventListener('change', function (e) {
    const el = e.target;
    if (el.tagName === 'SELECT' && el.classList.contains('is-invalid')) clearError(el);
  }, true);
}

/* ─────────────────────────────────────────────────────────────
   ⑬ GENERIC FALLBACK: attach guard to any remaining forms
   with required fields that weren't covered above.
───────────────────────────────────────────────────────────── */
function initGenericForms() {
  document.querySelectorAll('form').forEach(function(form) {
    // Skip filter/search forms (GET forms) and forms without required fields
    if (form.method && form.method.toLowerCase() === 'get') return;
    if (!form.querySelector('[required]')) return;
    // Skip forms that have already had specific validators attached
    if (form.dataset.cvInit) return;
    form.dataset.cvInit = '1';
    attachRequiredGuard(form);
  });
}

/* ─────────────────────────────────────────────────────────────
   BOOTSTRAP: run all inits on DOMContentLoaded
───────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  initLiveClear();
  initLoginValidation();
  initRegisterValidation();
  initAddOwnerValidation();
  initEditOwnerValidation();
  initAddTheaterValidation();
  initAddMovieValidation();
  initAddShowValidation();
  initContactValidation();
  initChangePasswordValidation();
  initPartnerValidation();
  initForgotPasswordValidation();
  // Run last so it only catches leftover forms
  initGenericForms();
});

/* ─────────────────────────────────────────────────────────────
   RE-INIT hook: call window.cvReinit() after dynamically
   injecting new modals or forms into the DOM.
───────────────────────────────────────────────────────────── */
window.cvReinit = function () {
  initAddShowValidation();
  initGenericForms();
};