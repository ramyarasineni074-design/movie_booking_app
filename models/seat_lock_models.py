from extensions import db
from datetime import datetime, timedelta


class SeatLock(db.Model):
    """
    Temporary seat lock table.
    When a user clicks "Proceed to Payment", the selected seats are locked
    for LOCK_DURATION_SECONDS seconds.
    - If payment is completed → seats are permanently booked (lock row deleted).
    - If user backs off or times out → lock expires and seats become available again.
    - Only one lock can exist per (show_id, seat_number) at a time.
    """
    __tablename__ = 'seat_locks'

    LOCK_DURATION_SECONDS = 300  # 5 minutes

    lock_id     = db.Column(db.String(300), primary_key=True)
    show_id     = db.Column(db.String(300), db.ForeignKey('shows.show_id'), nullable=False, index=True)
    seat_number = db.Column(db.String(200), nullable=False, index=True)
    user_id     = db.Column(db.String(300), nullable=False, index=True)
    locked_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at  = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('show_id', 'seat_number', name='uq_show_seat_lock'),
        db.Index('idx_lock_expiry', 'expires_at'),
    )

    @classmethod
    def lock_seats(cls, show_id: str, seat_numbers: list, user_id: str) -> dict:
        """
        Attempt to lock a list of seat_numbers for a show.
        Returns {'success': True, 'lock_ids': [...]} on success,
        or {'success': False, 'conflict_seats': [...]} if any seat is already locked by another user.
        """
        import uuid
        now    = datetime.utcnow()
        expiry = now + timedelta(seconds=cls.LOCK_DURATION_SECONDS)

        # FIX Bug #4: flush after delete so expired rows are gone before the
        # conflict check runs within the same transaction.
        cls.query.filter(cls.expires_at < now).delete(synchronize_session=False)
        db.session.flush()

        # Check existing active locks on these seats (by OTHER users)
        conflicts = (
            cls.query
            .filter(
                cls.show_id == show_id,
                cls.seat_number.in_(seat_numbers),
                cls.user_id != user_id,
                cls.expires_at >= now,
            )
            .with_entities(cls.seat_number)
            .all()
        )
        if conflicts:
            return {'success': False, 'conflict_seats': [r.seat_number for r in conflicts]}

        # Remove any existing locks by THIS user on these seats (re-lock)
        cls.query.filter(
            cls.show_id == show_id,
            cls.seat_number.in_(seat_numbers),
            cls.user_id == user_id,
        ).delete(synchronize_session=False)
        db.session.flush()

        lock_ids = []
        for sn in seat_numbers:
            lid = 'LK_' + str(uuid.uuid4())[:10].upper()
            db.session.add(cls(
                lock_id=lid,
                show_id=show_id,
                seat_number=sn,
                user_id=user_id,
                locked_at=now,
                expires_at=expiry,
            ))
            lock_ids.append(lid)

        return {'success': True, 'lock_ids': lock_ids, 'expires_at': expiry.strftime('%Y-%m-%d %H:%M:%S')}

    @classmethod
    def release_locks(cls, show_id: str, user_id: str, seat_numbers: list = None):
        """Release locks held by this user for this show (optionally specific seats)."""
        q = cls.query.filter(cls.show_id == show_id, cls.user_id == user_id)
        if seat_numbers:
            q = q.filter(cls.seat_number.in_(seat_numbers))
        q.delete(synchronize_session=False)

    @classmethod
    def get_locked_seats(cls, show_id: str) -> dict:
        """
        Return a dict: { seat_number: {user_id, expires_at} }
        for all currently active locks on this show.
        FIX Bug #4: flush after delete so the cleanup is visible immediately.
        """
        now = datetime.utcnow()
        cls.query.filter(cls.expires_at < now).delete(synchronize_session=False)
        db.session.flush()
        rows = cls.query.filter(cls.show_id == show_id, cls.expires_at >= now).all()
        return {
            r.seat_number: {
                'user_id':    r.user_id,
                'expires_at': r.expires_at.isoformat(),
            }
            for r in rows
        }

    @classmethod
    def get_user_lock_expiry(cls, show_id: str, user_id: str):
        """
        Return the earliest expiry ISO string for this user's locks on this show,
        or None if they have no active lock.  Used by _back_to_payment() to pass
        the countdown time when re-rendering the payment page after a validation error.
        """
        now = datetime.utcnow()
        row = (
            cls.query
            .filter(
                cls.show_id    == show_id,
                cls.user_id    == user_id,
                cls.expires_at >= now,
            )
            .order_by(cls.expires_at.asc())
            .first()
        )
        return row.expires_at.isoformat() if row else None

    def to_dict(self):
        return {
            'lock_id':     self.lock_id,
            'show_id':     self.show_id,
            'seat_number': self.seat_number,
            'user_id':     self.user_id,
            'locked_at':   self.locked_at.isoformat() if self.locked_at else None,
            'expires_at':  self.expires_at.isoformat() if self.expires_at else None,
        }

    def __repr__(self):
        return f'<SeatLock {self.seat_number} show={self.show_id}>'