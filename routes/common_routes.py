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


@common_bp.route('/test-mail')
def test_mail():
    from utils.email_utils import _send
    ok = _send(
        to_email='ramyarasineni074@gmail.com',
        subject='CineBook — SendGrid Test',
        plain='SendGrid is working correctly on CineBook!'
    )
    return ('SendGrid mail sent successfully ✅' if ok
            else 'SendGrid mail FAILED ❌ — check SENDGRID_API_KEY env var and Render logs')