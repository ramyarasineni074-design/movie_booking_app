from extensions import db

class Show(db.Model):
    __tablename__ = 'shows'

    show_id = db.Column(db.String(300), primary_key=True)

    movie_id = db.Column(db.String(300), db.ForeignKey('movies.movie_id'), index=True)
    theater_id = db.Column(db.String(300), db.ForeignKey('theaters.theater_id'), index=True)
    screen_id = db.Column(db.String(300), db.ForeignKey('screens.screen_id'), index=True)

    show_date = db.Column(db.Date, index=True)
    start_time = db.Column(db.Time, index=True)

    price = db.Column(db.Float)
    available_seats = db.Column(db.Integer)

    status = db.Column(db.String(50), default='active', index=True)

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    bookings = db.relationship('Booking', backref='show', lazy=True)

    __table_args__ = (
        db.Index('idx_movie_date', 'movie_id', 'show_date'),
        db.Index('idx_theater_date', 'theater_id', 'show_date'),
        db.Index('idx_movie_status', 'movie_id', 'status'),
        db.Index('idx_theater_status', 'theater_id', 'status'),
    )

    def to_dict(self):
        return {
            "show_id": self.show_id,
            "movie_id": self.movie_id,
            "theater_id": self.theater_id,
            "screen_id": self.screen_id,
            "show_date": self.show_date.isoformat() if self.show_date else None,
            "start_time": str(self.start_time) if self.start_time else None,
            "price": self.price,
            "available_seats": self.available_seats,
            "status": self.status
        }

    def __repr__(self):
        return f"<Show {self.show_id}>"