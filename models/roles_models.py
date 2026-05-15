from extensions import db

class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True)

    role_name = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
        index=True
    )

    # 🔥 NEW
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    users = db.relationship("AppUser", backref="role", lazy=True)



    def to_dict(self):
        return {
            "role_id": self.role_id,
            "role_name": self.role_name
        }

    def __repr__(self):
        return f"<Role {self.role_name}>"