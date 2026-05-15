# DATABASE CONFIG

# -----------------------

import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:Ramya@localhost:5432/movie_booking_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY')

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Admin Credentials
    ADMIN_NAME = 'Admin'
    ADMIN_EMAIL = 'admin@gmail.com'
    ADMIN_PASSWORD = 'admin123'

    # Email (Gmail SMTP - same as school project)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'ramyarasineni074@gmail.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = 'ramyarasineni074@gmail.com'

    # Pagination
    PAGE_SIZE = 12


    RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID')  # same as above
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')   # your secret key