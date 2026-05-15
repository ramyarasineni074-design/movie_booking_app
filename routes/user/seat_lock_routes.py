"""
seat_lock_routes.py
~~~~~~~~~~~~~~~~~~~
REST API endpoints for the seat-locking feature.

Flow:
  1. User selects seats → clicks "Proceed to Payment"
     POST /api/seats/lock  →  locks seats for 2 min, returns expiry time
  2. User is on payment page for > 2 min without completing:
     Locks expire automatically; other users can book those seats.
  3. User completes payment:
     POST /confirm-booking  →  locks are deleted (seats permanently booked).
  4. User abandons / backs off:
     POST /api/seats/unlock  →  releases their own locks immediately.
  5. Any user landing on seat-selection page:
     GET  /api/seats/locked/<show_id>  →  list of currently locked seat numbers.

FIXES vs original
─────────────────
FIX 1  get_locked_seats: the API response now always includes `is_mine` so the
       JS can distinguish "my lock" (selected orange) vs "other's lock" (amber).
       The original code already built is_mine correctly but the JS was ignoring
       it because of a separate variable-name bug — both sides are now aligned.

FIX 4  lock_seats: when the same user tries to lock a seat they already hold,
       we return the existing lock's expiry WITHOUT resetting the timer.
       Previously every call to /api/seats/lock refreshed all the user's locks,
       letting them extend the hold indefinitely by repeatedly clicking Proceed.
"""

from datetime import datetime
from flask import Blueprint, jsonify, request, session

from extensions import db
from models import SeatLock, Show, Movie
from utils.decorators import login_required, handle_exceptions
from routes.user.seat_ws_events import broadcast_seat_update

seat_lock_bp = Blueprint('seat_lock_bp', __name__, url_prefix='/api/seats')


def _current_user_id():
    return session.get('dataset_user_id') or session.get('user_id')


def _resolve_virtual_show(show_id: str) -> bool:
    """
    If show_id is a virtual show ID (starts with 'VS_'), ensure a real row
    exists in the `shows` table BEFORE any seat_locks INSERT is attempted.

    The `seat_locks` table has a FK  seat_locks.show_id → shows.show_id.
    Virtual show IDs are generated on the movie-detail page for the 4 fixed
    time-slots and are only materialised into `shows` inside payment_routes
    _resolve_show().  When the seat-lock API is called BEFORE the payment
    form is submitted (i.e. when the user clicks "Proceed to Payment" on the
    seat-selection page), the virtual show row does not exist yet, which
    causes the FK violation:
        psycopg2.errors.ForeignKeyViolation: Key (show_id)=(...) is not
        present in table "shows".

    This function materialises the virtual show row the same way
    payment_routes._resolve_show() does, so the FK is satisfied.

    Returns True if the show_id is valid (real or successfully created),
    False if it could not be created (bad VS_ format).
    """
    if not show_id.startswith('VS_'):
        return True   # real show_id — FK already satisfied

    # Check if already materialised
    if Show.query.filter_by(show_id=show_id).first():
        return True

    # Parse:  VS_{movie_id}_{YYYY-MM-DD}_{HHMM}
    try:
        parts     = show_id.split('_')
        hhmm      = parts[-1]          # last segment:  HHMM
        date_str  = parts[-2]          # second-last:   YYYY-MM-DD
        movie_id  = '_'.join(parts[1:-2])  # everything between VS_ and date
        from datetime import time as _time, date as _date2
        slot_time = _time(int(hhmm[:2]), int(hhmm[2:]))
        show_date = _date2.fromisoformat(date_str)
    except Exception:
        return False   # malformed VS_ id

    # Find a donor real show to borrow theater/screen/price from
    donor = Show.query.filter_by(movie_id=movie_id, status='active').first()

    new_show                 = Show()
    new_show.show_id         = show_id
    new_show.movie_id        = movie_id
    new_show.theater_id      = donor.theater_id      if donor else None
    new_show.screen_id       = donor.screen_id       if donor else None
    new_show.price           = donor.price           if donor else 150.0
    new_show.available_seats = donor.available_seats if donor else 60
    new_show.show_date       = show_date
    new_show.start_time      = slot_time
    new_show.status          = 'active'
    db.session.add(new_show)
    db.session.commit()   # must commit BEFORE the seat_locks INSERT
    return True


# ─────────────────────────────────────────────────────────────
# GET /api/seats/locked/<show_id>
# Returns all currently-locked seat numbers for a show.
#
# FIX 1 — Response always includes is_mine so the JS can apply
#          the correct visual (selected vs amber held).
# ─────────────────────────────────────────────────────────────
@seat_lock_bp.route('/locked/<show_id>', methods=['GET'])
@login_required
@handle_exceptions
def get_locked_seats(show_id):
    user_id = _current_user_id()
    locked  = SeatLock.get_locked_seats(show_id)
    db.session.commit()   # flush the expired-row deletes

    result = {}
    for seat_num, info in locked.items():
        result[seat_num] = {
            # FIX 1: always send is_mine so JS can distinguish own vs others
            'is_mine':    info['user_id'] == user_id,
            'expires_at': info['expires_at'],
        }
    return jsonify({'success': True, 'locked': result})

# ─────────────────────────────────────────────────────────────
# POST /api/seats/lock
# Body: { show_id, seat_numbers: ["A1","A2",...] }
#
# FIX 4 — Do NOT reset the expiry timer for seats the current user
#          already holds.  Return the existing expiry instead.
#          This prevents the user from extending their hold
#          by navigating back and clicking Proceed again.
# ─────────────────────────────────────────────────────────────
@seat_lock_bp.route('/lock', methods=['POST'])
@login_required
@handle_exceptions
def lock_seats():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data         = request.get_json(silent=True) or {}
    show_id      = (data.get('show_id') or '').strip()
    seat_numbers = data.get('seat_numbers') or []

    if not show_id:
        return jsonify({'success': False, 'message': 'show_id is required'}), 400
    if not seat_numbers or not isinstance(seat_numbers, list):
        return jsonify({'success': False, 'message': 'seat_numbers must be a non-empty list'}), 400

    seat_numbers = [str(s).strip() for s in seat_numbers if str(s).strip()]

    # ── FIX: Materialise virtual show into `shows` table BEFORE any
    #         seat_locks INSERT — seat_locks.show_id has a FK to shows.show_id.
    #         Virtual show IDs (VS_...) are only created in payment_routes, so
    #         when the seat-lock API is hit first (on "Proceed to Payment"),
    #         the row doesn't exist yet and the INSERT fails with:
    #           ForeignKeyViolation: Key (show_id)=(...) not present in "shows"
    if not _resolve_virtual_show(show_id):
        return jsonify({'success': False, 'message': 'Invalid show ID.'}), 400

    # ── FIX 4: Check which seats this user already holds ────
    # We call get_locked_seats first to see the current state.
    # Seats the current user already holds are skipped — we do NOT
    # re-lock them (that would refresh the timer).
    # Only seats not yet locked by anyone are passed to lock_seats().
    already_locked = SeatLock.get_locked_seats(show_id)

    seats_i_own       = []  # seats I already hold a valid lock on
    seats_to_lock     = []  # seats not locked by anyone yet
    conflict_seats    = []  # seats locked by someone else

    for sn in seat_numbers:
        if sn in already_locked:
            info = already_locked[sn]
            if info['user_id'] == user_id:
                # I already own this lock — keep it, don't refresh
                seats_i_own.append(sn)
            else:
                # Someone else holds it
                conflict_seats.append(sn)
        else:
            seats_to_lock.append(sn)

    # If any seat is held by someone else, abort the whole request
    if conflict_seats:
        db.session.commit()
        return jsonify({
            'success':        False,
            'conflict_seats': conflict_seats,
            'message': (
                f"Seats {', '.join(conflict_seats)} are currently being booked "
                f"by another user. Please choose different seats."
            ),
        }), 409

    # Lock only the seats not yet held by anyone
    new_lock_ids   = []
    new_expires_at = None

    if seats_to_lock:
        result = SeatLock.lock_seats(show_id, seats_to_lock, user_id)
        db.session.commit()

        if not result['success']:
            # A race condition — someone grabbed a seat between our check and lock
            return jsonify({
                'success':        False,
                'conflict_seats': result['conflict_seats'],
                'message': (
                    f"Seats {', '.join(result['conflict_seats'])} are currently being booked "
                    f"by another user. Please choose different seats."
                ),
            }), 409

        new_lock_ids   = result['lock_ids']
        new_expires_at = result['expires_at']

    else:
        db.session.commit()

    # Determine the expiry to return to the client.
    # If we only re-confirmed existing locks, return the oldest expiry
    # (the one that will expire soonest) so the client timer is accurate.
    if seats_i_own and not new_expires_at:
        # All requested seats were already locked by this user.
        # Find the earliest expiry among them.
        earliest = None
        for sn in seats_i_own:
            exp_str = already_locked[sn]['expires_at']
            try:
                exp_dt = datetime.fromisoformat(exp_str)
            except Exception:
                continue
            if earliest is None or exp_dt < earliest:
                earliest = exp_dt
        new_expires_at = earliest.isoformat() if earliest else None

    response = jsonify({
        'success':    True,
        'expires_at': new_expires_at,
        'lock_ids':   new_lock_ids,
        'duration':   SeatLock.LOCK_DURATION_SECONDS,
    })

    # Broadcast real-time update to all browsers watching this show
    broadcast_seat_update(show_id)

    return response


# ─────────────────────────────────────────────────────────────
# POST /api/seats/unlock
# Body: { show_id, seat_numbers: [...] }   (seat_numbers optional → release all)
# Releases locks held by the current user.
# ─────────────────────────────────────────────────────────────
@seat_lock_bp.route('/unlock', methods=['POST'])
@login_required
@handle_exceptions
def unlock_seats():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data         = request.get_json(silent=True) or {}
    show_id      = (data.get('show_id') or '').strip()
    seat_numbers = data.get('seat_numbers')   # None → release all for this show

    if not show_id:
        return jsonify({'success': False, 'message': 'show_id is required'}), 400

    SeatLock.release_locks(show_id, user_id, seat_numbers)
    db.session.commit()

    # Broadcast real-time update to all browsers watching this show
    broadcast_seat_update(show_id)

    return jsonify({'success': True})