from extensions import db

class Review(db.Model):
    __tablename__ = 'reviews'

    review_id = db.Column(db.String(300), primary_key=True)

    user_id = db.Column(
        db.String(300),
        db.ForeignKey('c_user.user_id'),
        index=True
    )

    movie_id = db.Column(
        db.String(300),
        db.ForeignKey('movies.movie_id'),
        index=True
    )

    rating = db.Column(db.Float, index=True)
    comment = db.Column(db.Text)

    review_date = db.Column(
        db.DateTime,
        default=db.func.now(),
        index=True
    )

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    __table_args__ = (
        db.Index('idx_movie_review_date', 'movie_id', 'review_date'),
        # db.UniqueConstraint('user_id', 'movie_id', name='uq_user_movie_review'),
    )

    def to_dict(self):
        return {
            "review_id": self.review_id,
            "user_id": self.user_id,
            "movie_id": self.movie_id,
            "rating": self.rating,
            "comment": self.comment,
            "review_date": self.review_date.isoformat() if self.review_date else None
        }

    def __repr__(self):
        return f"<Review {self.review_id}>"