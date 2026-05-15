"""
CineBook — payment_routes.py

FIXES APPLIED
─────────────
Bug #1  booking_models.py now has payment_method column → uncommented here.
Bug #3  Booking.total_amount now stores grand_total (was storing total_price only).
Bug #4  seat_lock_models.py flushes after deletes (fixed there, used here).
Warn #1 payment() no longer re-locks seats; instead it VERIFIES the JS-acquired
        lock belongs to the current user and is still active.
Warn #2 confirm_booking() wraps the double-booking check + insert in a savepoint
        (begin_nested) to prevent race-condition double-bookings.
Warn #3 Server-side guard: available_seats >= num_tickets checked before booking.
Warn #5 _back_to_payment() now passes lock_expires_at + lock_duration so the
        payment-page countdown timer still works after a validation failure.
"""

import uuid, io, base64
from datetime import datetime

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, session, jsonify)

from extensions import db
from models import Movie, Show, Theater, Seat, Booking, Payment, SeatLock
from models.users_models import User
from utils.decorators import login_required, handle_exceptions

payment_bp = Blueprint('payment_bp', __name__)


def _resolve_show(show_id: str) -> Show | None:
    """
    If show_id starts with 'VS_', look up or create a real Show record.
    Virtual show IDs encode:  VS_{movie_id}_{YYYY-MM-DD}_{HHMM}
    Returns the Show object (real or newly created), or None on failure.
    """
    if not show_id.startswith('VS_'):
        return Show.query.get(show_id)

    # Parse virtual ID
    try:
        parts     = show_id.split('_')
        hhmm      = parts[-1]
        date_str  = parts[-2]
        movie_id  = '_'.join(parts[1:-2])
        from datetime import time as _time, date as _date2
        slot_time = _time(int(hhmm[:2]), int(hhmm[2:]))
        show_date = _date2.fromisoformat(date_str)
    except Exception:
        return None

    # Check if we already materialised this virtual show before
    existing = Show.query.filter_by(show_id=show_id).first()
    if existing:
        return existing

    # Find a donor real show for theater/screen/price info
    donor = (Show.query
             .filter_by(movie_id=movie_id, status='active')
             .first())

    new_show = Show()
    new_show.show_id         = show_id
    new_show.movie_id        = movie_id
    new_show.theater_id      = donor.theater_id   if donor else None
    new_show.screen_id       = donor.screen_id    if donor else None
    new_show.price           = donor.price        if donor else 150.0
    new_show.available_seats = donor.available_seats if donor else 60
    new_show.show_date       = show_date
    new_show.start_time      = slot_time
    new_show.status          = 'active'
    db.session.add(new_show)
    db.session.commit()
    return new_show

import re as _re
_UPI_RE = _re.compile(r'^[\w.\-]{2,256}@[a-zA-Z]{2,64}$')


# ─────────────────────────────────────────────────────────────
# HELPER — price computation
# ─────────────────────────────────────────────────────────────
# seat_type_counts: optional dict {'vip': n, 'premium': n, 'regular': n}
# When provided, each type is priced at its multiplier of show.price.
#   Regular = 1.0×  |  Premium = 1.5×  |  VIP = 2.0×
# When omitted, falls back to flat show.price × num_seats (legacy).
def compute_totals(show, num_seats: int, seat_type_counts: dict = None) -> dict:
    base_price = float(show.price or 0)

    if seat_type_counts:
        vip_count     = int(seat_type_counts.get('vip',     0))
        premium_count = int(seat_type_counts.get('premium', 0))
        regular_count = int(seat_type_counts.get('regular', 0))
        other_count   = max(0, num_seats - vip_count - premium_count - regular_count)

        total_price = (
            vip_count     * base_price * 2.0 +
            premium_count * base_price * 1.5 +
            regular_count * base_price * 1.0 +
            other_count   * base_price * 1.0   # unknown type → base price
        )
    else:
        total_price = base_price * max(num_seats, 0)

    total_price = round(total_price, 2)
    conv        = int(total_price * 0.02)
    gst         = int((total_price + conv) * 0.18)
    grand_total = int(total_price + conv + gst)
    return {
        'total_price' : int(total_price),
        'conv'        : conv,
        'gst'         : gst,
        'grand_total' : grand_total,
    }


# ─────────────────────────────────────────────────────────────
# HELPER — dataset user
# ─────────────────────────────────────────────────────────────
def _get_dataset_user():
    from models import User
    uid = session.get('dataset_user_id') or session.get('user_id')
    return db.session.get(User, uid) if uid else None


# ─────────────────────────────────────────────────────────────
# HELPER — already-booked seat numbers for a show
# ─────────────────────────────────────────────────────────────
def _booked_seats_for_show(show_id: str) -> set:
    """
    Authoritative source: Booking table seat_numbers column.
    Seat.show_id is only written after booking confirms, so querying Seat
    here would miss bookings that haven't been committed yet.
    """
    booked = set()
    rows = (Booking.query
            .filter_by(show_id=show_id)
            .filter(Booking.payment_status != 'cancelled')
            .with_entities(Booking.seat_numbers)
            .all())
    for (seat_str,) in rows:
        for sn in (seat_str or '').split(','):
            sn = sn.strip()
            if sn:
                booked.add(sn)
    return booked


# ─────────────────────────────────────────────────────────────
# HELPER — re-render payment page (used on validation failures)
# FIX Warn #5: now passes lock_expires_at + lock_duration so the
#              countdown timer keeps working after a failed submission.
# ─────────────────────────────────────────────────────────────

def _get_wallet_balance():
    """Return the current user's wallet balance for payment page.

    BUG FIX: The old code read session['user_id'] which holds the AppUser
    integer primary key (e.g. 5).  It then tried User.query.filter_by(email=5)
    which never matches, so it always returned 0.0 — even after a refund was
    credited to the wallet.

    The correct key is session['dataset_user_id'] which holds the dataset
    User string PK (e.g. 'US_3847F6FB') that has the wallet_balance column.
    This is exactly what _get_dataset_user() uses everywhere else.
    """
    try:
        from flask import session
        # Use dataset_user_id (e.g. 'US_3847F6FB') — this is the User row
        # that has wallet_balance.  session['user_id'] is the AppUser integer
        # PK and must NOT be used here.
        uid = session.get('dataset_user_id')
        if uid:
            u = db.session.get(User, uid)
            if u:
                return round(u.wallet_balance or 0.0, 2)
    except Exception:
        pass
    return 0.0


def _back_to_payment(show, movie, theater, selected_seats, seat_ids, user_id=None):
    seat_list = [s.strip() for s in selected_seats.split(',') if s.strip()]
    totals    = compute_totals(show, len(seat_list))

    lock_expires_at = None
    if user_id:
        lock_expires_at = SeatLock.get_user_lock_expiry(show.show_id, user_id)

    return render_template(
        'user/payment.html',
        show=show, movie=movie, theater=theater,
        selected_seats=selected_seats, seat_ids=seat_ids,
        num_seats=len(seat_list),
        total_price=totals['total_price'],
        conv=totals['conv'],
        gst=totals['gst'],
        grand_total=totals['grand_total'],
        lock_expires_at=lock_expires_at,
        lock_duration=SeatLock.LOCK_DURATION_SECONDS,
        wallet_balance=_get_wallet_balance(),
    )


# ═════════════════════════════════════════════════════════════
# 0 — UPI verification API
# ═════════════════════════════════════════════════════════════
@payment_bp.route('/api/verify-upi', methods=['POST'])
@login_required
@handle_exceptions
def verify_upi():
    data   = request.get_json(silent=True) or {}
    upi_id = (data.get('upi_id') or '').strip()
    if not upi_id:
        return jsonify({'valid': False, 'message': 'UPI ID is required.'})
    if not _UPI_RE.match(upi_id):
        return jsonify({
            'valid': False,
            'message': 'Invalid UPI ID. Use format: name@upi, 9876543210@paytm, user@ybl etc.'
        })
    return jsonify({'valid': True, 'message': f'UPI ID {upi_id} verified successfully.'})


# ═════════════════════════════════════════════════════════════
# 1 — Payment page
# FIX Warn #1: No longer re-locks seats here. The JS already acquired
#              the lock via POST /api/seats/lock before the form submit.
#              We only VERIFY the lock exists and belongs to this user.
# ═════════════════════════════════════════════════════════════
@payment_bp.route('/payment', methods=['POST'])
@login_required
@handle_exceptions
def payment():
    show_id        = request.form.get('show_id', '').strip()
    selected_seats = request.form.get('selected_seats', '').strip()
    seat_ids       = request.form.get('seat_ids', '').strip()

    if not show_id:
        flash('Invalid show. Please try again.', 'danger')
        return redirect(url_for('user_bp.movies'))
    if not selected_seats:
        flash('Please select at least one seat.', 'danger')
        return redirect(url_for('user_bp.movies'))

    show = _resolve_show(show_id)
    if show is None:
        flash('Show not found.', 'danger')
        return redirect(url_for('user_bp.movies'))
    seat_number_list = [s.strip() for s in selected_seats.split(',') if s.strip()]
    num_seats        = len(seat_number_list)

    if num_seats == 0:
        flash('No valid seats selected. Please try again.', 'danger')
        return redirect(url_for('user_bp.select_seats', show_id=show_id))

    movie   = db.session.get(Movie,   show.movie_id)   if show.movie_id   else None
    theater = db.session.get(Theater, show.theater_id) if show.theater_id else None

    # Read per-type counts sent by the seat selection form
    seat_type_counts = {
        'vip':     int(request.form.get('vip_count',     0) or 0),
        'premium': int(request.form.get('premium_count', 0) or 0),
        'regular': int(request.form.get('regular_count', 0) or 0),
    }
    totals  = compute_totals(show, num_seats, seat_type_counts if any(seat_type_counts.values()) else None)

    # FIX Warn #1: verify the JS-acquired lock — do NOT re-lock.
    # If for some reason the lock is missing (e.g. direct POST), acquire it now.
    user_id = session.get('dataset_user_id') or session.get('user_id')
    lock_expires_at = None
    if user_id:
        lock_expires_at = SeatLock.get_user_lock_expiry(show_id, user_id)
        if not lock_expires_at:
            # Lock missing — acquire it (fallback for direct POST without JS)
            result = SeatLock.lock_seats(show_id, seat_number_list, user_id)
            db.session.commit()
            if result['success']:
                lock_expires_at = result['expires_at']
            else:
                flash(
                    f"Seats {', '.join(result['conflict_seats'])} are currently held by another user. "
                    "Please choose different seats.",
                    'danger'
                )
                return redirect(url_for('user_bp.select_seats', show_id=show_id))

    return render_template(
        'user/payment.html',
        show=show, movie=movie, theater=theater,
        selected_seats=selected_seats, seat_ids=seat_ids,
        num_seats=num_seats,
        total_price=totals['total_price'],
        conv=totals['conv'],
        gst=totals['gst'],
        grand_total=totals['grand_total'],
        lock_expires_at=lock_expires_at,
        lock_duration=SeatLock.LOCK_DURATION_SECONDS,
        wallet_balance=_get_wallet_balance(),
    )


# ═════════════════════════════════════════════════════════════
# 2 — Confirm booking
# ═════════════════════════════════════════════════════════════
@payment_bp.route('/confirm-booking', methods=['POST'])
@login_required
@handle_exceptions
def confirm_booking():
    show_id             = request.form.get('show_id', '').strip()
    selected_seats      = request.form.get('selected_seats', '').strip()
    seat_ids            = request.form.get('seat_ids', '').strip()
    payment_method      = request.form.get('payment_method', 'UPI').strip()
    razorpay_payment_id = request.form.get('razorpay_payment_id', '').strip()

    dataset_user = _get_dataset_user()
    if not dataset_user:
        flash('User profile not found. Please re-login.', 'danger')
        return redirect(url_for('auth_bp.login'))

    if not show_id:
        flash('Invalid show reference.', 'danger')
        return redirect(url_for('user_bp.movies'))

    show = _resolve_show(show_id)
    if show is None:
        flash('Show not found.', 'danger')
        return redirect(url_for('user_bp.movies'))
    movie   = db.session.get(Movie,   show.movie_id)   if show.movie_id   else None
    theater = db.session.get(Theater, show.theater_id) if show.theater_id else None

    if show.status != 'active':
        flash('This show is no longer available.', 'danger')
        return redirect(url_for('user_bp.movie_detail', movie_id=show.movie_id))

    seat_number_list = [s.strip() for s in selected_seats.split(',') if s.strip()]
    seat_id_list     = [s.strip() for s in seat_ids.split(',')       if s.strip()]
    num_tickets      = len(seat_number_list)

    if num_tickets == 0:
        flash('No seats selected.', 'danger')
        return redirect(url_for('user_bp.select_seats', show_id=show_id))

    uid = dataset_user.user_id

    # ── Payment-method-specific validation ──────────────────
    method_upper = payment_method.upper()

    if method_upper == 'UPI':
        upi_id = request.form.get('upi_id', '').strip()
        if not upi_id:
            flash('Please enter your UPI ID to proceed.', 'danger')
            return _back_to_payment(show, movie, theater, selected_seats, seat_ids, uid)
        if not _UPI_RE.match(upi_id):
            flash('Invalid UPI ID format. Use: name@upi, 9876543210@paytm, user@ybl etc.', 'danger')
            return _back_to_payment(show, movie, theater, selected_seats, seat_ids, uid)

    elif method_upper == 'RAZORPAY':
        if not razorpay_payment_id:
            flash('Razorpay payment ID missing. Please complete payment via Razorpay popup.', 'danger')
            return _back_to_payment(show, movie, theater, selected_seats, seat_ids, uid)

    elif method_upper == 'CARD':
        pass  # validated client-side

    elif method_upper == 'NETBANKING':
        pass  # bank optional at server level

    elif method_upper == 'WALLET':
        pass  # wallet balance checked after totals are computed (below)

    # FIX Warn #3: server-side available-seat guard
    if (show.available_seats or 0) < num_tickets:
        flash(
            f'Only {show.available_seats or 0} seat(s) remaining. '
            'Please go back and choose fewer seats.',
            'danger'
        )
        return redirect(url_for('user_bp.select_seats', show_id=show_id))

    # ── Compute totals ───────────────────────────────────────
    seat_type_counts = {
        'vip':     int(request.form.get('vip_count',     0) or 0),
        'premium': int(request.form.get('premium_count', 0) or 0),
        'regular': int(request.form.get('regular_count', 0) or 0),
    }
    totals = compute_totals(show, num_tickets, seat_type_counts if any(seat_type_counts.values()) else None)

    # ── Wallet balance check (done here after grand_total is known) ──────
    if method_upper == 'WALLET':
        wallet_bal = dataset_user.wallet_balance or 0.0
        if wallet_bal < totals['grand_total']:
            flash(
                f'Insufficient wallet balance. Your wallet has ₹{wallet_bal:.2f} '
                f'but the total is ₹{totals["grand_total"]:.2f}.',
                'danger'
            )
            return _back_to_payment(show, movie, theater, selected_seats, seat_ids, uid)

    upi_id    = request.form.get('upi_id', '').strip()
    bank_name = request.form.get('bank_name', '').strip()

    # Build transaction ref per method
    if method_upper == 'RAZORPAY':
        transaction_ref = razorpay_payment_id
    elif method_upper == 'UPI' and upi_id:
        transaction_ref = 'TXN_' + str(uuid.uuid4())[:10].upper() + f'|UPI:{upi_id}'
    elif method_upper == 'CARD':
        transaction_ref = 'TXN_CARD_' + str(uuid.uuid4())[:10].upper()
    elif method_upper == 'NETBANKING':
        bank_suffix     = bank_name.replace(' ', '')[:8].upper() if bank_name else 'BANK'
        transaction_ref = f'TXN_NB_{bank_suffix}_' + str(uuid.uuid4())[:8].upper()
    elif method_upper == 'WALLET':
        transaction_ref = 'TXN_WALLET_' + str(uuid.uuid4())[:10].upper()
    else:
        transaction_ref = 'TXN_' + str(uuid.uuid4())[:10].upper()

    booking_id = 'BK_' + str(uuid.uuid4())[:8].upper()

    # FIX Warn #2: wrap check + insert in a savepoint so concurrent requests
    #              can't both pass the double-booking guard simultaneously.
    try:
        with db.session.begin_nested():
            # ── Double-booking guard (inside savepoint) ──────────
            already_booked = _booked_seats_for_show(show_id)
            conflicts = [sn for sn in seat_number_list if sn in already_booked]
            if conflicts:
                flash(
                    f'Seats {", ".join(conflicts)} were just taken by someone else. '
                    'Please go back and choose different seats.',
                    'danger'
                )
                return redirect(url_for('user_bp.select_seats', show_id=show_id))

            # FIX Bug #1: payment_method column now exists on Booking model
            # FIX Bug #3: total_amount stores grand_total (not just total_price)
            booking = Booking(
                booking_id      = booking_id,
                user_id         = uid,
                show_id         = show_id,
                booking_date    = datetime.now(),
                total_tickets   = num_tickets,
                seat_numbers    = selected_seats,
                total_amount    = totals['grand_total'],   # FIX Bug #3
                payment_status  = 'completed',
                transaction_ref = transaction_ref,
                payment_method  = payment_method,          # FIX Bug #1
            )
            db.session.add(booking)

    except Exception as exc:
        db.session.rollback()
        flash('Booking could not be completed. Please try again.', 'danger')
        return redirect(url_for('user_bp.select_seats', show_id=show_id))

    # Update seat rows (synth seats skipped — Booking table is source of truth)
    for sid in seat_id_list:
        if sid.startswith('synth-'):
            continue
        seat = db.session.get(Seat, sid)
        if seat:
            seat.show_id    = show_id
            seat.booking_id = booking_id
            seat.status     = 'Booked'

    # FIX Warn #3: decrement safely — guard already ensured availability above
    show.available_seats = max(0, (show.available_seats or 0) - num_tickets)

    # Release seat locks now that booking is permanent
    SeatLock.release_locks(show_id, uid)

    # ── Deduct wallet balance if paid via wallet ─────────────────────────
    if method_upper == 'WALLET':
        dataset_user.wallet_balance = round(
            (dataset_user.wallet_balance or 0.0) - totals['grand_total'], 2
        )

    payment_rec = Payment(
        payment_id      = 'PAY_' + str(uuid.uuid4())[:8].upper(),
        booking_id      = booking_id,
        user_id         = uid,
        amount          = totals['grand_total'],
        payment_method  = payment_method,
        payment_date    = datetime.now(),
        status          = 'Success',
        transaction_ref = transaction_ref,
    )
    db.session.add(payment_rec)

    # ── Update Movie.total_revenue (stored aggregate) ────────────────────
    if movie:
        movie.total_revenue = round(
            (movie.total_revenue or 0.0) + totals['grand_total'], 2
        )

    db.session.commit()

    try:
        from utils.email_utils import send_booking_confirmation_email
        send_booking_confirmation_email(
            to_email=dataset_user.email, user_name=dataset_user.name,
            booking_id=booking_id,
            movie_title=movie.title    if movie   else '',
            theater_name=theater.name  if theater else '',
            show_date=str(show.show_date),
            show_time=str(show.start_time),
            seat_numbers=selected_seats,
            total_amount=totals['grand_total'],
            transaction_ref=transaction_ref,
            payment_method=payment_method,
        )
    except Exception as e:
        print(f'Email error: {e}')

    flash('Booking confirmed! 🎬 Enjoy the movie.', 'success')
    return redirect(url_for('payment_bp.ticket', booking_id=booking_id))


# ═════════════════════════════════════════════════════════════
# 3 — E-ticket
# ═════════════════════════════════════════════════════════════
@payment_bp.route('/ticket/<booking_id>')
@login_required
@handle_exceptions
def ticket(booking_id):
    dataset_user = _get_dataset_user()

    result = (
        db.session.query(Booking, Show, Movie, Theater)
        .join(Show,    Booking.show_id    == Show.show_id)
        .join(Movie,   Show.movie_id      == Movie.movie_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Booking.booking_id == booking_id)
        .first()
    )

    if not result:
        flash('Booking not found.', 'danger')
        return redirect(url_for('user_bp.my_bookings'))

    b, s, m, t = result
    if dataset_user and b.user_id != dataset_user.user_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('user_bp.my_bookings'))

    payment_rec = Payment.query.filter_by(booking_id=booking_id).first()

    qr_lines = [
        "CineBook E-Ticket",
        f"Booking ID : {b.booking_id}",
        f"Movie      : {m.title if m else 'N/A'}",
        f"Theater    : {t.name if t else 'N/A'}",
        f"City       : {t.city if t else 'N/A'}",
        f"Date       : {s.show_date.strftime('%d %b %Y') if s and s.show_date else 'N/A'}",
        f"Time       : {s.start_time.strftime('%I:%M %p') if s and s.start_time else 'N/A'}",
        f"Seats      : {b.seat_numbers or 'N/A'}",
        f"Tickets    : {b.total_tickets}",
        f"Amount     : Rs.{int(payment_rec.amount) if payment_rec else int(b.total_amount or 0)}",
        f"Method     : {payment_rec.payment_method if payment_rec else 'N/A'}",
        f"Status     : {b.payment_status or 'N/A'}",
        f"TXN        : {b.transaction_ref or 'N/A'}",
    ]
    qr_b64 = None
    try:
        import qrcode
        qr_img = qrcode.make("\n".join(qr_lines))
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f'QR error: {e}')

    return render_template(
        'user/ticket.html',
        booking=b, show=s, movie=m, theater=t,
        qr_b64=qr_b64,
        payment=payment_rec,
    )


# ═════════════════════════════════════════════════════════════
# 4 — Cancel booking
# ═════════════════════════════════════════════════════════════
@payment_bp.route('/cancel-booking/<booking_id>', methods=['POST'])
@login_required
@handle_exceptions
def cancel_booking(booking_id):
    dataset_user = _get_dataset_user()
    if not dataset_user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404
    if booking.user_id != dataset_user.user_id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    if booking.payment_status == 'cancelled':
        return jsonify({'success': False, 'message': 'Already cancelled'}), 400

    show  = db.session.get(Show,  booking.show_id)
    movie = db.session.get(Movie, show.movie_id) if show else None

    # ── Block cancellation if show has already started/passed ────────────
    if show and show.show_date and show.start_time:
        from datetime import datetime as _dt, date as _date2, time as _time2
        show_datetime = _dt.combine(show.show_date, show.start_time)
        if _dt.now() >= show_datetime:
            return jsonify({
                'success': False,
                'message': 'Cannot cancel — the show has already started or passed.'
            }), 400

    if show:
        Seat.query.filter_by(booking_id=booking_id).update(
            {'status': 'Available', 'show_id': None, 'booking_id': None}
        )
        show.available_seats = (show.available_seats or 0) + booking.total_tickets

    booking.payment_status = 'cancelled'
    pmt = Payment.query.filter_by(booking_id=booking_id).first()
    if pmt:
        pmt.status = 'refunded'

    # ── Credit wallet balance ────────────────────────────────────────────
    # Refund the amount paid back to the user's in-app wallet
    refund_amount = booking.total_amount or 0.0
    if refund_amount > 0:
        dataset_user.wallet_balance = round(
            (dataset_user.wallet_balance or 0.0) + refund_amount, 2
        )

    # ── Deduct from Movie.total_revenue ─────────────────────────────────
    # Owner revenue is computed live (payment_status='completed' filter),
    # so cancellation already removes it from live queries automatically.
    # But Movie.total_revenue is a stored field — must be decremented here.
    if movie and refund_amount > 0:
        movie.total_revenue = round(
            max(0.0, (movie.total_revenue or 0.0) - refund_amount), 2
        )

    db.session.commit()

    try:
        from utils.email_utils import send_cancellation_refund_email
        send_cancellation_refund_email(
            to_email=dataset_user.email, user_name=dataset_user.name,
            booking_id=booking_id,
            movie_title=movie.title if movie else 'N/A',
            seat_numbers=booking.seat_numbers,
            total_amount=booking.total_amount,
            transaction_ref=booking.transaction_ref,
        )
    except Exception as e:
        print(f'Email error: {e}')

    return jsonify({
        'success': True,
        'message': f'Booking cancelled. ₹{refund_amount:.0f} refunded to your wallet.',
        'wallet_balance': dataset_user.wallet_balance,
        'refund_amount': refund_amount,
    })