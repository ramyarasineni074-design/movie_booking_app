from functools import wraps
from flask import session, redirect, url_for, flash, jsonify, request, render_template
from extensions import db


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "danger")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for('auth_bp.login'))
        if session.get("role") != "admin":
            flash("Access denied. Admin only.", "danger")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return wrapper


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth_bp.login'))
        if session.get('role') != 'owner':
            flash('Access denied.', 'danger')
            return redirect(url_for('auth_bp.login'))
        # Force password change on first login
        from models import AppUser
        user = db.session.get(AppUser, session['user_id'])
        if user and user.is_first_login:
            flash('Please change your temporary password before continuing.', 'warning')
            return redirect(url_for('auth_bp.change_password'))
        return f(*args, **kwargs)
    return decorated

def user_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "danger")
            return redirect(url_for('auth_bp.login'))
        if session.get("role") != "user":
            flash("Access denied.", "danger")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return wrapper


def handle_exceptions(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"ERROR in {f.__name__}: {str(e)}")

            # If AJAX / JSON request → return JSON error
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": "Something went wrong"}), 500

            # Otherwise show error page
            return render_template("common/error.html", error=str(e)), 500
    return wrapper