from flask import Flask
from werkzeug.security import generate_password_hash
from flask_migrate import Migrate

from config import Config
from extensions import db, mail, socketio

# Import models (IMPORTANT for migrations)

from models import *

# Import blueprints

from routes.common_routes import common_bp
from routes.auth_routes import auth_bp
from routes.admin.admin_routes import admin_bp
from routes.admin.admin_analytics import admin_analytics_bp
from routes.owner.owner_routes import owner_bp
from routes.owner.owner_analytics import owner_analytics_bp
from routes.user.user_routes import user_bp
from routes.user.booking_routes import booking_bp
from routes.user.contact_routes import contact_bp
from routes.user.payment_routes import payment_bp
from routes.user.seat_lock_routes import seat_lock_bp
from routes.user import seat_ws_events  # registers SocketIO event handlers  # noqa: F401

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    #  Init extensions
    db.init_app(app)
    mail.init_app(app)
    socketio.init_app(app, cors_allowed_origins='*', async_mode='eventlet')

    #  INIT MIGRATE (VERY IMPORTANT)
    migrate = Migrate(app, db)

        # Auto-run migrations on startup
    with app.app_context():

        from flask_migrate import upgrade
        upgrade()

        import seed

        from script.scripts import seed_csv_data
        seed_csv_data()



    # 🔹 Register blueprints
    app.register_blueprint(common_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_analytics_bp)
    app.register_blueprint(owner_bp)
    app.register_blueprint(owner_analytics_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(contact_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(seat_lock_bp)

    # 🔹 Seed data (roles + admin)
   
    return app




#  REQUIRED for Flask CLI

app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=False)