from extensions import db

class AppUser(db.Model):
    __tablename__ = "app_users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False, index=True)

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    password = db.Column(db.String(200), nullable=False)

    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.role_id"),
        index=True
    )

    user_id = db.Column(
        db.String(300),
        db.ForeignKey("c_user.user_id"),
        nullable=True,
        index=True
    )

    is_first_login = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True, index=True)

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    brands = db.relationship('TheaterBrand', backref='owner', lazy=True)

    __table_args__ = (
        db.Index('idx_role_active', 'role_id', 'is_active'),
        db.UniqueConstraint('user_id', name='uq_appuser_user'),
    )



    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role_id": self.role_id,
            "user_id": self.user_id,
            "is_first_login": self.is_first_login,
            "is_active": self.is_active
        }

    def __repr__(self):
        return f"<AppUser {self.email}>"