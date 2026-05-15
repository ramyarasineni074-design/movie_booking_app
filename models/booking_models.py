from extensions import db

class Booking(db.Model):
    __tablename__ = 'bookings'

    booking_id = db.Column(db.String(300), primary_key=True)
    user_id = db.Column(db.String(300), db.ForeignKey('c_user.user_id'), index=True)
    show_id = db.Column(db.String(300), db.ForeignKey('shows.show_id'), index=True)

    booking_date = db.Column(db.DateTime, index=True)
    total_tickets = db.Column(db.Integer)
    seat_numbers = db.Column(db.String(500))
    total_amount = db.Column(db.Float)
    payment_status = db.Column(db.String(200), index=True)
    transaction_ref = db.Column(db.String(200), index=True)

    # FIX Bug #1: added payment_method column so confirm_booking() can store it
    payment_method = db.Column(db.String(50), nullable=True)

    payments = db.relationship('Payment', backref='booking', lazy=True)

    __table_args__ = (
        db.Index('idx_user_booking_date', 'user_id', 'booking_date'),
        db.Index('idx_show_booking_date', 'show_id', 'booking_date'),
        db.Index('idx_status_booking_date', 'payment_status', 'booking_date'),
    )

    def to_dict(self):
        return {
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "show_id": self.show_id,
            "booking_date": self.booking_date.isoformat() if self.booking_date else None,
            "total_tickets": self.total_tickets,
            "seat_numbers": self.seat_numbers,
            "total_amount": self.total_amount,
            "payment_status": self.payment_status,
            "transaction_ref": self.transaction_ref,
            "payment_method": self.payment_method,
        }

    def __repr__(self):
        return f"<Booking {self.booking_id}>"