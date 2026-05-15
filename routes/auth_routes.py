import secrets
import string

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import AppUser, User, Role
from utils.decorators import login_required, handle_exceptions
from utils.email_utils import send_forgot_password_email

auth_bp = Blueprint('auth_bp', __name__)


def generate_random_password(length=10):
    return ''.join(secrets.choice(string.digits) for _ in range(length))


# --------------------------------------------------
# LOGIN
# --------------------------------------------------
@auth_bp.route('/login', methods=['GET', 'POST'])
@handle_exceptions
def login():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_bp.dashboard'))
        elif role == 'owner':
            return redirect(url_for('owner_bp.dashboard'))
        else:
            return redirect(url_for('user_bp.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('auth_bp.login'))

        # Admin login
        if (email == current_app.config['ADMIN_EMAIL'] and
                password == current_app.config['ADMIN_PASSWORD']):
            session.clear()
            session['user_id'] = 'admin'
            session['user_name'] = 'Admin'
            session['role'] = 'admin'
            flash('Welcome Admin!', 'success')

            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin_bp.dashboard'))

        # DB login
        app_user = AppUser.query.filter_by(email=email).first()

        if not app_user or not check_password_hash(app_user.password, password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth_bp.login'))

        if not app_user.is_active:
            flash('Your account has been deactivated. Contact admin.', 'danger')
            return redirect(url_for('auth_bp.login'))

        role = app_user.role.role_name if app_user.role else 'user'

        session.clear()
        session['user_id'] = app_user.id
        session['user_name'] = app_user.name
        session['role'] = role
        session['app_user_id'] = app_user.id

        if app_user.user_id:
            session['dataset_user_id'] = app_user.user_id

        if app_user.is_first_login:
            flash('Please change your password on first login.', 'warning')
            return redirect(url_for('auth_bp.change_password'))

        # ✅ Handle next HERE
        next_page = request.args.get('next')

        if role == 'owner':
            return redirect(next_page or url_for('owner_bp.dashboard'))

        return redirect(next_page or url_for('user_bp.home'))

    # ✅ GET request → show login page
    return render_template('auth/login.html')


# --------------------------------------------------
# REGISTER (public users only)
# --------------------------------------------------
@auth_bp.route('/register', methods=['GET', 'POST'])
@handle_exceptions
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if not all([name, email, phone, password, confirm]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth_bp.register'))

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth_bp.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth_bp.register'))

        if AppUser.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth_bp.register'))

        # Get or create user role
        user_role = Role.query.filter_by(role_name='user').first()
        if not user_role:
            user_role = Role(role_name='user')
            db.session.add(user_role)
            db.session.flush()

        # Create dataset User entry
        import uuid
        new_user_id = 'US_' + str(uuid.uuid4())[:8].upper()
        dataset_user = User(
            user_id=new_user_id,
            name=name,
            email=email,
            phone_number=phone
        )
        db.session.add(dataset_user)
        db.session.flush()

        # Create AppUser
        new_app_user = AppUser(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role_id=user_role.role_id,
            user_id=new_user_id,
            is_first_login=False,
            is_active=True
        )
        db.session.add(new_app_user)
        db.session.commit()

        # Auto-login the new user
        session.clear()
        session['user_id'] = new_app_user.id
        session['user_name'] = new_app_user.name
        session['role'] = 'user'
        session['app_user_id'] = new_app_user.id
        session['dataset_user_id'] = new_user_id
        flash(f'Welcome to CineBook, {name}! 🎬 Start exploring movies.', 'success')
        return redirect(url_for('user_bp.home'))

    return render_template('auth/register.html')


# --------------------------------------------------
# CHANGE PASSWORD
# --------------------------------------------------
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@handle_exceptions
def change_password():
    user_id = session.get('user_id')

    if user_id == 'admin':
        flash('Admin password cannot be changed here.', 'danger')
        return redirect(url_for('admin_bp.dashboard'))

    app_user = db.session.get(AppUser, user_id)
    if not app_user:
        session.clear()
        flash('User not found.', 'danger')
        return redirect(url_for('auth_bp.login'))

    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth_bp.change_password'))

        if not check_password_hash(app_user.password, current_password):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('auth_bp.change_password'))

        if len(new_password) < 6:
            flash('New password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth_bp.change_password'))

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth_bp.change_password'))

        if check_password_hash(app_user.password, new_password):
            flash('New password must be different from current password.', 'danger')
            return redirect(url_for('auth_bp.change_password'))

        app_user.password = generate_password_hash(new_password)
        app_user.is_first_login = False
        db.session.commit()

        flash('Password changed successfully!', 'success')

        role = session.get('role')
        if role == 'owner':
            return redirect(url_for('owner_bp.dashboard'))
        return redirect(url_for('user_bp.home'))

    return render_template('auth/change_password.html')


# --------------------------------------------------
# FORGOT PASSWORD (AJAX)
# --------------------------------------------------
@auth_bp.route('/forgot-password', methods=['POST'])
@handle_exceptions
def forgot_password():
    email = request.form.get('email', '').strip()

    if not email:
        return jsonify({'success': False, 'message': 'Email is required'}), 400

    app_user = AppUser.query.filter_by(email=email).first()

    if not app_user:
        return jsonify({'success': False, 'message': 'Email not found'}), 404

    new_password = generate_random_password()
    app_user.password = generate_password_hash(new_password)
    app_user.is_first_login = True

    try:
        db.session.commit()
        send_forgot_password_email(
            to_email=app_user.email,
            user_name=app_user.name,
            new_password=new_password
        )
        return jsonify({'success': True, 'message': 'New password sent to your email'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to send email. Try again later.'}), 500


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------
@auth_bp.route('/logout')
@handle_exceptions
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth_bp.login'))