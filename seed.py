from app import create_app
from extensions import db
from models import Role, AppUser, ContactMessage, PartnershipRequest
from werkzeug.security import generate_password_hash
from config import Config

app = create_app()

with app.app_context():

    print("Seeding roles...")

    roles = ["admin", "owner", "user"]

    for role_name in roles:
        if not Role.query.filter_by(role_name=role_name).first():
            db.session.add(Role(role_name=role_name))

    db.session.commit()

    print("Seeding admin user...")

    admin_role = Role.query.filter_by(role_name="admin").first()

    if not AppUser.query.filter_by(email=Config.ADMIN_EMAIL).first():
        admin = AppUser(
            name=Config.ADMIN_NAME,
            email=Config.ADMIN_EMAIL,
            password=generate_password_hash(Config.ADMIN_PASSWORD),
            role_id=admin_role.role_id,
            is_first_login=False,
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()

    print("✅ Roles + Admin inserted")