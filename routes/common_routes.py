from flask import Blueprint, redirect, url_for, session

common_bp = Blueprint('common_bp', __name__)


@common_bp.route('/')
def home():
    role = session.get('role')

    if role == 'admin':
        return redirect(url_for('admin_bp.dashboard'))
    elif role == 'owner':
        return redirect(url_for('owner_bp.dashboard'))
    elif role == 'user':
        return redirect(url_for('user_bp.home'))

    # ✅ Guest users go to home page
    return redirect(url_for('user_bp.home'))


from flask_mail import Message
from extensions import mail

@common_bp.route('/test-mail')
def test_mail():

    try:

        msg = Message(
            subject="Test Mail",
            recipients=["your_email@gmail.com"],
            body="Mail working successfully"
        )

        mail.send(msg)

        return "Mail sent successfully"

    except Exception as e:
        return str(e)