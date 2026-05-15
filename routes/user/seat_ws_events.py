"""
seat_ws_events.py
~~~~~~~~~~~~~~~~~
Flask-SocketIO event handlers for real-time seat-lock updates.

How it works
────────────
• Every seat-selection page joins a SocketIO *room* named "show_<show_id>".
  All browsers watching the same show share that room automatically.

• Whenever a seat is locked or unlocked via the REST API
  (seat_lock_routes.py), a helper `broadcast_seat_update()` is called.
  It emits a `seat_update` event to every client in that room so they
  see the change instantly — no polling needed on the client side.

• The client still calls the REST endpoints for actual lock / unlock
  operations.  SocketIO is purely a *push* channel for state changes.

• The existing polling loop in seat_selection.html is DISABLED when the
  WebSocket connection is established (the JS checks `window.__wsActive`).
  It falls back to polling automatically if the connection drops.

Broadcast payload sent to room "show_<show_id>"
────────────────────────────────────────────────
{
  "locked": {
    "A1": { "is_mine": false, "expires_at": "2025-01-01T12:34:56" },
    "B3": { "is_mine": true,  "expires_at": "2025-01-01T12:34:56" }
  }
}

`is_mine` is ALWAYS false in broadcasts (server cannot know the receiver),
so the client compares seat user_id to its own session user_id stored in
`window.__userId`.
"""

from flask import request
from flask_socketio import join_room, leave_room

from extensions import db, socketio
from models import SeatLock


# ─────────────────────────────────────────────────────────────────
# Helper – called from seat_lock_routes after every lock/unlock/commit
# ─────────────────────────────────────────────────────────────────
def broadcast_seat_update(show_id: str):
    """
    Push the current lock state for *show_id* to every browser in that room.
    Safe to call from any request context (uses socketio.emit with namespace).
    """
    locked = SeatLock.get_locked_seats(show_id)  # { seat_num: {user_id, expires_at} }
    db.session.commit()                           # commit the expired-row cleanup

    payload = {
        seat: {
            'is_mine':    False,          # clients determine their own ownership
            'user_id':    info['user_id'],
            'expires_at': info['expires_at'],
        }
        for seat, info in locked.items()
    }

    socketio.emit(
        'seat_update',
        {'locked': payload},
        room=f'show_{show_id}',
    )


# ─────────────────────────────────────────────────────────────────
# Client connects to the namespace (auto event)
# ─────────────────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    pass   # nothing to do; rooms are joined via 'join_show'


# ─────────────────────────────────────────────────────────────────
# Client sends: { show_id: "SH_..." }
# We put this socket into the matching room.
# ─────────────────────────────────────────────────────────────────
@socketio.on('join_show')
def on_join_show(data):
    show_id = (data or {}).get('show_id', '').strip()
    if not show_id:
        return

    room = f'show_{show_id}'
    join_room(room)

    # Immediately push the current lock state so the client is in sync
    try:
        locked = SeatLock.get_locked_seats(show_id)
        db.session.commit()
    except Exception:
        locked = {}

    payload = {
        seat: {
            'is_mine':    False,
            'user_id':    info['user_id'],
            'expires_at': info['expires_at'],
        }
        for seat, info in locked.items()
    }

    # emit only to the caller's socket (room=request.sid)
    socketio.emit('seat_update', {'locked': payload}, room=request.sid)


# ─────────────────────────────────────────────────────────────────
# Client sends: { show_id: "SH_..." }  when leaving the page
# ─────────────────────────────────────────────────────────────────
@socketio.on('leave_show')
def on_leave_show(data):
    show_id = (data or {}).get('show_id', '').strip()
    if show_id:
        leave_room(f'show_{show_id}')


# ─────────────────────────────────────────────────────────────────
# Socket disconnect (auto event)
# ─────────────────────────────────────────────────────────────────
@socketio.on('disconnect')
def on_disconnect():
    pass   # Flask-SocketIO removes the sid from all rooms automatically
