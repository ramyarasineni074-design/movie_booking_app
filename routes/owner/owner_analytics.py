"""
Owner Analytics Routes
Separate file for owner dashboard analytics (charts & graphs).
All queries are scoped to the logged-in owner's brand.
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, session
from sqlalchemy import func, extract, case
from extensions import db
from models import TheaterBrand, Theater, Show, Booking, Movie, Screen, Seat, Review, Payment
from utils.decorators import owner_required

owner_analytics_bp = Blueprint(
    'owner_analytics_bp', __name__, url_prefix='/owner/analytics'
)

PAID = ['completed']


def _get_brand():
    owner_id = session.get('user_id')
    return TheaterBrand.query.filter_by(owner_id=owner_id).first()


# PAGE
@owner_analytics_bp.route('/')
@owner_required
def analytics():
    brand = _get_brand()
    if not brand:
        from flask import render_template as rt
        return rt('owner/no_brand.html')
    return render_template('owner/analytics.html',
                           brand=brand, active_page='analytics')


# KPI Summary
@owner_analytics_bp.route('/api/summary')
@owner_required
def api_summary():
    brand = _get_brand()
    if not brand:
        return jsonify({})
    base = (
        db.session.query(func.sum(Booking.total_amount),
                         func.count(Booking.booking_id))
        .join(Show,    Booking.show_id   == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
    )
    paid_rev, paid_cnt = base.filter(Booking.payment_status.in_(PAID)).first() or (0, 0)
    cancelled_rev, _ = base.filter(Booking.payment_status == 'cancelled').first() or (0, 0)
    failed_rev, _ = base.filter(Booking.payment_status == 'failed').first() or (0, 0)
    avg_val = round(float(paid_rev or 0) / max(int(paid_cnt or 0), 1), 2)
    return jsonify({
        'total_revenue': round(float(paid_rev or 0), 2),
        'total_bookings': int(paid_cnt or 0),
        'cancelled_revenue': round(float(cancelled_rev or 0), 2),
        'failed_revenue': round(float(failed_rev or 0), 2),
        'avg_booking_value': avg_val
    })


# Kept – Revenue trend
@owner_analytics_bp.route('/api/revenue-trend')
@owner_required
def api_revenue_trend():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            extract('year',  Booking.booking_date).label('yr'),
            extract('month', Booking.booking_date).label('mo'),
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Booking.show_id    == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Booking.booking_date >= datetime.now() - timedelta(days=365))
        .group_by('yr', 'mo')
        .order_by('yr', 'mo')
        .all()
    )
    months = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']
    return jsonify([
        {'label': f"{months[int(r.mo)-1]} {int(r.yr)}",
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q1 (owner) – Daily bookings trend for brand (last 60 days)
@owner_analytics_bp.route('/api/daily-bookings-trend')
@owner_required
def api_daily_bookings_trend():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            func.date(Booking.booking_date).label('day'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Booking.show_id   == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Booking.booking_date >= datetime.now() - timedelta(days=60))
        .group_by(func.date(Booking.booking_date))
        .order_by(func.date(Booking.booking_date))
        .all()
    )
    return jsonify([
        {'day': str(r.day), 'count': int(r.count or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Kept – Top movies by revenue
@owner_analytics_bp.route('/api/top-movies')
@owner_required
def api_top_movies():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Movie.title,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.movie_id     == Movie.movie_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.title)
        .order_by(func.sum(Booking.total_amount).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'title': r.title, 'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q5 (owner) – Top 10 movies by bookings count
@owner_analytics_bp.route('/api/top-movies-bookings')
@owner_required
def api_top_movies_bookings():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Movie.title,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.movie_id     == Movie.movie_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.title)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'title': r.title, 'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q7 – Booking trends for top 5 movies over time (multi-line)
@owner_analytics_bp.route('/api/movie-trends-over-time')
@owner_required
def api_movie_trends_over_time():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    # Get top 5 movies by bookings in this brand
    top_movies = (
        db.session.query(Movie.movie_id, Movie.title)
        .join(Show,    Show.movie_id     == Movie.movie_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.movie_id, Movie.title)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(5)
        .all()
    )
    result = []
    months_list = ['Jan','Feb','Mar','Apr','May','Jun',
                   'Jul','Aug','Sep','Oct','Nov','Dec']
    for mv in top_movies:
        rows = (
            db.session.query(
                extract('year',  Booking.booking_date).label('yr'),
                extract('month', Booking.booking_date).label('mo'),
                func.count(Booking.booking_id).label('count')
            )
            .join(Show,    Booking.show_id   == Show.show_id)
            .join(Theater, Show.theater_id   == Theater.theater_id)
            .filter(Theater.brand_id == brand.brand_id)
            .filter(Show.movie_id == mv.movie_id)
            .filter(Booking.payment_status.in_(PAID))
            .filter(Booking.booking_date >= datetime.now() - timedelta(days=365))
            .group_by('yr', 'mo')
            .order_by('yr', 'mo')
            .all()
        )
        result.append({
            'title': mv.title,
            'data': [
                {'label': f"{months_list[int(r.mo)-1]} {int(r.yr)}",
                 'count': int(r.count or 0)}
                for r in rows
            ]
        })
    return jsonify(result)


# Q9 (owner) – Top theatres by bookings within brand
@owner_analytics_bp.route('/api/top-theaters-bookings')
@owner_required
def api_top_theaters_bookings():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Theater.name,
            Theater.city,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.name, Theater.city)
        .order_by(func.count(Booking.booking_id).desc())
        .all()
    )
    return jsonify([
        {'theater': r.name, 'city': r.city,
         'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q11 – Screen occupancy / seat utilization
@owner_analytics_bp.route('/api/screen-occupancy')
@owner_required
def api_screen_occupancy():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Screen.screen_number,
            Theater.name.label('theater_name'),
            Screen.total_seats,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_tickets).label('tickets_sold')
        )
        .join(Theater, Screen.theater_id == Theater.theater_id)
        .join(Show,    Show.screen_id    == Screen.screen_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Screen.screen_id, Screen.screen_number, Theater.name, Screen.total_seats)
        .order_by(func.sum(Booking.total_tickets).desc())
        .all()
    )
    return jsonify([
        {
            'screen': f"{r.theater_name} - Screen {r.screen_number}",
            'total_seats': int(r.total_seats or 0),
            'tickets_sold': int(r.tickets_sold or 0),
            'bookings': int(r.bookings or 0),
            'occupancy_pct': round(
                float(r.tickets_sold or 0) / max(int(r.total_seats or 1), 1) * 100, 1
            )
        }
        for r in rows
    ])


# Q12 – Seat type (economy/premium etc.) booking comparison
@owner_analytics_bp.route('/api/seat-type-breakdown')
@owner_required
def api_seat_type_breakdown():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Seat.seat_type,
            func.count(Seat.seat_id).label('seats_booked'),
            func.count(Booking.booking_id.distinct()).label('bookings')
        )
        .join(Screen,  Seat.screen_id   == Screen.screen_id)
        .join(Theater, Screen.theater_id == Theater.theater_id)
        .join(Booking, Seat.booking_id  == Booking.booking_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Seat.seat_type.isnot(None))
        .group_by(Seat.seat_type)
        .order_by(func.count(Seat.seat_id).desc())
        .all()
    )
    return jsonify([
        {'seat_type': r.seat_type or 'Unknown',
         'seats_booked': int(r.seats_booked or 0),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q14 (owner) – Avg ticket price by theater
@owner_analytics_bp.route('/api/avg-price-by-theater')
@owner_required
def api_avg_price_by_theater():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Theater.name,
            Theater.city,
            func.avg(Show.price).label('avg_price'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Show.price.isnot(None))
        .group_by(Theater.name, Theater.city)
        .order_by(func.avg(Show.price).desc())
        .all()
    )
    return jsonify([
        {'theater': r.name, 'city': r.city,
         'avg_price': round(float(r.avg_price or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q4 (owner) – Booking volume by time slot
@owner_analytics_bp.route('/api/bookings-by-timeslot')
@owner_required
def api_bookings_by_timeslot():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    hour = func.extract('hour', Show.start_time)
    slot = case(
        (hour < 12, 'Morning'),
        (hour < 17, 'Afternoon'),
        (hour < 21, 'Evening'),
        else_='Night'
    )
    rows = (
        db.session.query(
            slot.label('slot'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Booking.show_id   == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by('slot')
        .all()
    )
    order = {'Morning': 0, 'Afternoon': 1, 'Evening': 2, 'Night': 3}
    data = sorted(
        [{'slot': r.slot, 'count': int(r.count or 0),
          'revenue': round(float(r.revenue or 0), 2)} for r in rows],
        key=lambda x: order.get(x['slot'], 9)
    )
    return jsonify(data)


# Kept – Revenue per theater
@owner_analytics_bp.route('/api/theater-revenue')
@owner_required
def api_theater_revenue():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Theater.name,
            Theater.city,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.name, Theater.city)
        .order_by(func.sum(Booking.total_amount).desc())
        .all()
    )
    return jsonify([
        {'theater': r.name, 'city': r.city,
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Kept – Genre breakdown
@owner_analytics_bp.route('/api/genre-breakdown')
@owner_required
def api_genre_breakdown():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Movie.genre,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.movie_id     == Movie.movie_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .join(Booking, Booking.show_id   == Show.show_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.genre)
        .order_by(func.sum(Booking.total_amount).desc())
        .all()
    )
    return jsonify([
        {'genre': r.genre or 'Unknown',
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Kept – Bookings by weekday
@owner_analytics_bp.route('/api/bookings-by-weekday')
@owner_required
def api_bookings_by_weekday():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    dow = func.extract('dow', Booking.booking_date)
    rows = (
        db.session.query(
            dow.label('dow'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Booking.show_id   == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by('dow')
        .order_by('dow')
        .all()
    )
    day_names = {1: 'Sun', 2: 'Mon', 3: 'Tue', 4: 'Wed',
                 5: 'Thu', 6: 'Fri', 7: 'Sat'}
    return jsonify([
        {'day': day_names.get(int(r.dow), str(r.dow)),
         'count': int(r.count or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Kept – Payment status
@owner_analytics_bp.route('/api/payment-status')
@owner_required
def api_payment_status():
    brand = _get_brand()
    if not brand:
        return jsonify([])
    rows = (
        db.session.query(
            Booking.payment_status,
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('amount')
        )
        .join(Show,    Booking.show_id   == Show.show_id)
        .join(Theater, Show.theater_id   == Theater.theater_id)
        .filter(Theater.brand_id == brand.brand_id)
        .group_by(Booking.payment_status)
        .all()
    )
    return jsonify([
        {'status': r.payment_status or 'Unknown',
         'count': int(r.count or 0),
         'amount': round(float(r.amount or 0), 2)}
        for r in rows
    ])