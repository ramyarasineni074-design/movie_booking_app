from extensions import db

class Payment(db.Model):
    __tablename__ = 'payments'

    payment_id = db.Column(db.String(300), primary_key=True)
    booking_id = db.Column(db.String(300), db.ForeignKey('bookings.booking_id'), index=True)
    user_id = db.Column(db.String(300), db.ForeignKey('c_user.user_id'), index=True)

    amount = db.Column(db.Float)
    payment_method = db.Column(db.String(200), index=True)
    payment_date = db.Column(db.DateTime, index=True)
    status = db.Column(db.String(200), index=True)
    transaction_ref = db.Column(db.String(200), index=True)

    __table_args__ = (
        db.Index('idx_user_payment_date', 'user_id', 'payment_date'),
        db.Index('idx_status_payment_date', 'status', 'payment_date'),
    )
    

    def to_dict(self):
        return {
            "payment_id": self.payment_id,
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "payment_method": self.payment_method,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "status": self.status,
            "transaction_ref": self.transaction_ref
        }

    def __repr__(self):
        return f"<Payment {self.payment_id}>"