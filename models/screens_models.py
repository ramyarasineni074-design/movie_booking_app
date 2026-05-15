from extensions import db

class Screen(db.Model):
    __tablename__ = 'screens'

    screen_id = db.Column(db.String(300), primary_key=True)

    theater_id = db.Column(
        db.String(300),
        db.ForeignKey('theaters.theater_id'),
        index=True
    )

    screen_number = db.Column(db.Integer, index=True)
    total_seats = db.Column(db.Integer)

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    seats = db.relationship('Seat', backref='screen', lazy=True)
    shows = db.relationship('Show', backref='screen', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('theater_id', 'screen_number', name='uq_theater_screen'),
        db.Index('idx_theater_screen', 'theater_id', 'screen_number'),
    )

    @property
    def name(self):
        return f"Screen {self.screen_number}"

    @property
    def capacity(self):
        return self.total_seats
    
    

    def to_dict(self):
        return {
            "screen_id": self.screen_id,
            "theater_id": self.theater_id,
            "screen_number": self.screen_number,
            "total_seats": self.total_seats,
            "name": self.name,
            "capacity": self.capacity
        }

    def __repr__(self):
        return f"<Screen {self.screen_number}>"