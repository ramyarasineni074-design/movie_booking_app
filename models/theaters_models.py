from extensions import db

class Theater(db.Model):
    __tablename__ = 'theaters'

    theater_id = db.Column(db.String(300), primary_key=True)

    brand_id = db.Column(
        db.String(300),
        db.ForeignKey('theater_brands.brand_id'),
        nullable=True,
        index=True
    )

    name = db.Column(db.String(250), nullable=False, index=True)
    location = db.Column(db.String(200), index=True)
    city = db.Column(db.String(250), index=True)
    state = db.Column(db.String(200), index=True)

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    screens = db.relationship('Screen', backref='theater', lazy=True)
    shows = db.relationship('Show', backref='theater', lazy=True)

    __table_args__ = (
        db.Index('idx_state_city', 'state', 'city'),
        db.Index('idx_brand_city', 'brand_id', 'city'),
    )


    def to_dict(self):
        return {
            "theater_id": self.theater_id,
            "brand_id": self.brand_id,
            "name": self.name,
            "location": self.location,
            "city": self.city,
            "state": self.state
        }

    def __repr__(self):
        return f"<Theater {self.name}>"