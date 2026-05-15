from extensions import db

class Movie(db.Model):
    __tablename__ = 'movies'

    movie_id = db.Column(db.String(300), primary_key=True)

    title = db.Column(db.String(250), nullable=False, index=True)
    genre = db.Column(db.String(200), index=True)
    language = db.Column(db.String(250), index=True)
    duration = db.Column(db.Integer)
    rating = db.Column(db.Float, index=True)
    release_date = db.Column(db.Date, index=True)
    description = db.Column(db.Text)
    poster_url = db.Column(db.String(500))
    status = db.Column(db.String(50), default='active', index=True)

    # 🔥 NEW COLUMNS
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    is_featured = db.Column(db.Boolean, default=False, index=True)

    total_bookings = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Float, default=0)

    shows = db.relationship('Show', backref='movie', lazy=True)
    reviews = db.relationship('Review', backref='movie', lazy=True)

    __table_args__ = (
        db.Index('idx_movie_search', 'title', 'genre', 'language'),
    )


    
    def to_dict(self):
        return {
            "movie_id": self.movie_id,
            "title": self.title,
            "genre": self.genre,
            "language": self.language,
            "duration": self.duration,
            "rating": self.rating,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "description": self.description,
            "poster_url": self.poster_url,
            "status": self.status
        }

    def __repr__(self):
        return f"<Movie {self.title}>"