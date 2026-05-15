from extensions import db

class User(db.Model):
    __tablename__ = 'c_user'

    user_id = db.Column(db.String(300), primary_key=True)

    name = db.Column(db.String(250), index=True)
    email = db.Column(db.String(300), unique=True, index=True)
    phone_number = db.Column(db.String(20), index=True)
    dob = db.Column(db.Date)

    # 🔥 NEW
    is_active = db.Column(db.Boolean, default=True, index=True)

    # Wallet balance — credited on refund, debited on wallet payment
    wallet_balance = db.Column(db.Float, default=0.0, nullable=False, server_default='0')

    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    bookings = db.relationship('Booking', backref='user', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)

    __table_args__ = (
        db.Index('idx_user_search', 'name', 'email'),
    )

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "phone_number": self.phone_number,
            "dob": self.dob.isoformat() if self.dob else None,
            "wallet_balance": round(self.wallet_balance or 0.0, 2),
        }

    def __repr__(self):
        return f"<User {self.email}>"