from extensions import db

class TheaterBrand(db.Model):
    __tablename__ = 'theater_brands'

    brand_id = db.Column(db.String(300), primary_key=True)

    brand_name = db.Column(db.String(250), nullable=False, unique=True, index=True)

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("app_users.id"),
        nullable=True,
        index=True
    )

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    theaters = db.relationship('Theater', backref='brand', lazy=True)

    __table_args__ = (
        db.Index('idx_owner_brand', 'owner_id', 'brand_name'),
    )


    
    def to_dict(self):
        return {
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
            "owner_id": self.owner_id
        }

    def __repr__(self):
        return f"<TheaterBrand {self.brand_name}>"