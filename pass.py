from app import create_app   # or your app import
from models import AppUser
from extensions import db
from werkzeug.security import generate_password_hash

app = create_app()  # or use your existing app instance

with app.app_context():
    users = AppUser.query.all()

    for user in users:
        if not user.password.startswith("pbkdf2:"):
            user.password = generate_password_hash(user.password)

    db.session.commit()

    print("✅ All passwords converted to hashed successfully!")