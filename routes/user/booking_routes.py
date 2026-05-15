from flask import Blueprint, redirect, url_for, flash
from utils.decorators import login_required, handle_exceptions

booking_bp = Blueprint('booking_bp', __name__)

@booking_bp.route('/select-seats/<show_id>')
@login_required
@handle_exceptions
def select_seats(show_id):
    return redirect(url_for('user_bp.select_seats', show_id=show_id))

@booking_bp.route('/create-booking', methods=['POST'])
@login_required
@handle_exceptions
def create_booking():
    return redirect(url_for('user_bp.movies'))

