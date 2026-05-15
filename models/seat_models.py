from extensions import db

class Seat(db.Model):
    __tablename__ = 'seats'

    seat_id = db.Column(db.String(300), primary_key=True)

    screen_id = db.Column(
        db.String(300),
        db.ForeignKey('screens.screen_id'),
        index=True
    )

    seat_number = db.Column(db.String(200), index=True)
    seat_type = db.Column(db.String(200), index=True)

    charger = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(200), default='available', index=True)

    show_id = db.Column(
        db.String(300),
        db.ForeignKey('shows.show_id'),
        nullable=True,
        index=True
    )

    booking_id = db.Column(
        db.String(300),
        db.ForeignKey('bookings.booking_id'),
        nullable=True,
        index=True
    )

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    __table_args__ = (
        db.Index('idx_screen_show', 'screen_id', 'show_id'),
        db.Index('idx_booking_seat', 'booking_id', 'seat_number'),
        db.UniqueConstraint('screen_id', 'seat_number', name='uq_screen_seat'),
    )
    

    def to_dict(self):
        return {
            "seat_id": self.seat_id,
            "screen_id": self.screen_id,
            "seat_number": self.seat_number,
            "seat_type": self.seat_type,
            "charger": self.charger,
            "status": self.status,
            "show_id": self.show_id,
            "booking_id": self.booking_id
        }

    def __repr__(self):
        return f"<Seat {self.seat_number}>"