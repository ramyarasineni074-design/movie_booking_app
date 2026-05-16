"""
Admin Analytics Routes
Separate file for dashboard analytics (charts & graphs).
Mounted under admin_bp via app.py registration.
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import func, extract, case
from extensions import db
from models import (AppUser, User, Movie, Theater, Show,
                    Booking, Payment, Review, TheaterBrand, Screen, Seat)
from utils.decorators import admin_required

admin_analytics_bp = Blueprint(
    'admin_analytics_bp', __name__, url_prefix='/admin/analytics'
)

PAID = ['completed']


# PAGE
@admin_analytics_bp.route('/')
@admin_required
def analytics():
    return render_template('admin/analytics.html', active_page='analytics')


# KPI Summary
@admin_analytics_bp.route('/api/revenue-summary')
@admin_required
def api_revenue_summary():
    total_rev = db.session.query(func.sum(Booking.total_amount))\
        .filter(Booking.payment_status.in_(PAID)).scalar() or 0
    total_bookings = db.session.query(func.count(Booking.booking_id))\
        .filter(Booking.payment_status.in_(PAID)).scalar() or 0
    cancelled_rev = db.session.query(func.sum(Booking.total_amount))\
        .filter(Booking.payment_status == 'cancelled').scalar() or 0
    failed_rev = db.session.query(func.sum(Booking.total_amount))\
        .filter(Booking.payment_status == 'failed').scalar() or 0
    avg_booking_val = round(float(total_rev) / max(total_bookings, 1), 2)
    return jsonify({
        'total_revenue': round(float(total_rev), 2),
        'total_bookings': int(total_bookings),
        'cancelled_revenue': round(float(cancelled_rev), 2),
        'failed_revenue': round(float(failed_rev), 2),
        'avg_booking_value': avg_booking_val
    })


# Q1 – Daily bookings trend
# FIX: removed hard 60-day cap; now returns last 90 days of actual data,
# falling back to the most-recent 90 days in the dataset so seeded
# historical bookings always appear.
@admin_analytics_bp.route('/api/daily-bookings-trend')
@admin_required
def api_daily_bookings_trend():
    # Find the latest booking date in the DB (works for both live and seeded data)
    latest = db.session.query(func.max(Booking.booking_date))\
        .filter(Booking.payment_status.in_(PAID)).scalar()

    if latest is None:
        return jsonify([])

    # Show 90 days ending at the latest booking date
    if isinstance(latest, datetime):
        end_date = latest
    else:
        end_date = datetime.combine(latest, datetime.max.time())

    start_date = end_date - timedelta(days=90)

    rows = (
        db.session.query(
            func.date(Booking.booking_date).label('day'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .filter(Booking.payment_status.in_(PAID))
        .filter(Booking.booking_date >= start_date)
        .filter(Booking.booking_date <= end_date)
        .group_by(func.date(Booking.booking_date))
        .order_by(func.date(Booking.booking_date))
        .all()
    )
    return jsonify([
        {'day': str(r.day), 'count': int(r.count or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q2 – Total bookings by city
@admin_analytics_bp.route('/api/bookings-by-city')
@admin_required
def api_bookings_by_city():
    rows = (
        db.session.query(
            Theater.city,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.theater_id  == Theater.theater_id)
        .join(Booking, Booking.show_id  == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.city)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(15)
        .all()
    )
    return jsonify([
        {'city': r.city or 'Unknown', 'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q3a – Peak booking periods by month
@admin_analytics_bp.route('/api/peak-by-month')
@admin_required
def api_peak_by_month():
    rows = (
        db.session.query(
            extract('month', Booking.booking_date).label('mo'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .filter(Booking.payment_status.in_(PAID))
        .group_by('mo')
        .order_by('mo')
        .all()
    )
    months = ['Jan','Feb','Mar','Apr','May','Jun',
              'Jul','Aug','Sep','Oct','Nov','Dec']
    return jsonify([
        {'month': months[int(r.mo)-1], 'count': int(r.count or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q3b – Bookings by weekday (for heatmap)
@admin_analytics_bp.route('/api/bookings-by-weekday')
@admin_required
def api_bookings_by_weekday():
    dow = func.extract('dow', Booking.booking_date)
    rows = (
        db.session.query(
            dow.label('dow'),
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .filter(Booking.payment_status.in_(PAID))
        .group_by('dow')
        .order_by('dow')
        .all()
    )
    day_names = {0: 'Sun', 1: 'Mon', 2: 'Tue',
                 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}
    return jsonify([
        {'day': day_names.get(int(r.dow), str(r.dow)),
         'count': int(r.count or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q4 – Booking volume by time slot
@admin_analytics_bp.route('/api/bookings-by-timeslot')
@admin_required
def api_bookings_by_timeslot():
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
        .join(Show, Booking.show_id == Show.show_id)
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


# Q5 – Top 10 movies by total bookings
@admin_analytics_bp.route('/api/top-movies-bookings')
@admin_required
def api_top_movies_bookings():
    rows = (
        db.session.query(
            Movie.title,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
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


# Q6 – Revenue by genre
@admin_analytics_bp.route('/api/revenue-by-genre')
@admin_required
def api_revenue_by_genre():
    rows = (
        db.session.query(
            Movie.genre,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.movie_id    == Movie.movie_id)
        .join(Booking, Booking.show_id  == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.genre)
        .order_by(func.sum(Booking.total_amount).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'genre': r.genre or 'Unknown',
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q8 – Rating vs booking count scatter
@admin_analytics_bp.route('/api/rating-vs-bookings')
@admin_required
def api_rating_vs_bookings():
    rows = (
        db.session.query(
            Movie.title,
            Movie.rating,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Movie.rating.isnot(None))
        .group_by(Movie.title, Movie.rating)
        .having(func.count(Booking.booking_id) > 0)
        .all()
    )
    return jsonify([
        {'title': r.title, 'rating': round(float(r.rating or 0), 1),
         'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q9 – Top theatres by number of bookings
@admin_analytics_bp.route('/api/top-theaters-bookings')
@admin_required
def api_top_theaters_bookings():
    rows = (
        db.session.query(
            Theater.name,
            Theater.city,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.theater_id == Theater.theater_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.name, Theater.city)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'theater': f"{r.name} ({r.city})",
         'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q10 – Theatre performance by city grouped bar
@admin_analytics_bp.route('/api/theater-by-city')
@admin_required
def api_theater_by_city():
    rows = (
        db.session.query(
            Theater.city,
            func.count(Theater.theater_id.distinct()).label('theater_count'),
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.theater_id == Theater.theater_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.city)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(12)
        .all()
    )
    return jsonify([
        {'city': r.city or 'Unknown',
         'theater_count': int(r.theater_count or 0),
         'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Q13 – Total revenue by movie
@admin_analytics_bp.route('/api/top-movies-revenue')
@admin_required
def api_top_movies_revenue():
    rows = (
        db.session.query(
            Movie.title,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.title)
        .order_by(func.sum(Booking.total_amount).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'title': r.title,
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q14 – Avg ticket price by city
@admin_analytics_bp.route('/api/avg-price-by-city')
@admin_required
def api_avg_price_by_city():
    rows = (
        db.session.query(
            Theater.city,
            func.avg(Show.price).label('avg_price'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.theater_id == Theater.theater_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Show.price.isnot(None))
        .group_by(Theater.city)
        .order_by(func.avg(Show.price).desc())
        .limit(15)
        .all()
    )
    return jsonify([
        {'city': r.city or 'Unknown',
         'avg_price': round(float(r.avg_price or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q15 – Ticket price distribution (histogram)
@admin_analytics_bp.route('/api/price-distribution')
@admin_required
def api_price_distribution():
    rows = (
        db.session.query(Show.price)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Show.price.isnot(None))
        .all()
    )
    prices = [float(r.price) for r in rows if r.price]
    if not prices:
        return jsonify([])
    mn, mx = min(prices), max(prices)
    bucket_size = max(50, (mx - mn) / 10)
    buckets = {}
    for p in prices:
        b = int((p - mn) // bucket_size) * bucket_size + mn
        label = f"Rs.{int(b)}-{int(b+bucket_size)}"
        buckets[label] = buckets.get(label, 0) + 1
    result = [{'range': k, 'count': v} for k, v in sorted(buckets.items())]
    return jsonify(result)


# Q16 – Avg price vs booking volume scatter
@admin_analytics_bp.route('/api/price-vs-bookings')
@admin_required
def api_price_vs_bookings():
    rows = (
        db.session.query(
            Movie.title,
            func.avg(Show.price).label('avg_price'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .filter(Show.price.isnot(None))
        .group_by(Movie.title)
        .having(func.count(Booking.booking_id) > 0)
        .all()
    )
    return jsonify([
        {'title': r.title,
         'avg_price': round(float(r.avg_price or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Q18 – Payment method distribution
@admin_analytics_bp.route('/api/payment-methods')
@admin_required
def api_payment_methods():
    rows = (
        db.session.query(
            Payment.payment_method,
            func.count(Payment.payment_id).label('count'),
            func.sum(Payment.amount).label('total')
        )
        .group_by(Payment.payment_method)
        .order_by(func.count(Payment.payment_id).desc())
        .all()
    )
    return jsonify([
        {'method': r.payment_method or 'Unknown',
         'count': int(r.count or 0),
         'total': round(float(r.total or 0), 2)}
        for r in rows
    ])


# Q20 – Avg booking value per customer distribution
@admin_analytics_bp.route('/api/avg-booking-value-dist')
@admin_required
def api_avg_booking_value_dist():
    rows = (
        db.session.query(
            func.avg(Booking.total_amount).label('avg_val')
        )
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Booking.user_id)
        .all()
    )
    values = [float(r.avg_val) for r in rows if r.avg_val]
    if not values:
        return jsonify([])
    mn, mx = min(values), max(values)
    bucket_size = max(100, (mx - mn) / 10)
    buckets = {}
    for v in values:
        b = int((v - mn) // bucket_size) * bucket_size + mn
        label = f"Rs.{int(b)}-{int(b+bucket_size)}"
        buckets[label] = buckets.get(label, 0) + 1
    result = [{'range': k, 'count': v} for k, v in sorted(buckets.items())]
    return jsonify(result)


# Kept – payment status breakdown
@admin_analytics_bp.route('/api/payment-status')
@admin_required
def api_payment_status():
    rows = (
        db.session.query(
            Booking.payment_status,
            func.count(Booking.booking_id).label('count'),
            func.sum(Booking.total_amount).label('amount')
        )
        .group_by(Booking.payment_status)
        .all()
    )
    return jsonify([
        {'status': r.payment_status or 'Unknown',
         'count': int(r.count or 0),
         'amount': round(float(r.amount or 0), 2)}
        for r in rows
    ])


# Kept – top cities revenue
@admin_analytics_bp.route('/api/top-cities')
@admin_required
def api_top_cities():
    rows = (
        db.session.query(
            Theater.city,
            Theater.state,
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .join(Show,    Show.theater_id == Theater.theater_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Theater.city, Theater.state)
        .order_by(func.sum(Booking.total_amount).desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'city': f"{r.city}, {r.state}",
         'revenue': round(float(r.revenue or 0), 2),
         'bookings': int(r.bookings or 0)}
        for r in rows
    ])


# Kept – language popularity
@admin_analytics_bp.route('/api/language-popularity')
@admin_required
def api_language_popularity():
    rows = (
        db.session.query(
            Movie.language,
            func.count(Booking.booking_id).label('bookings'),
            func.sum(Booking.total_amount).label('revenue')
        )
        .join(Show,    Show.movie_id   == Movie.movie_id)
        .join(Booking, Booking.show_id == Show.show_id)
        .filter(Booking.payment_status.in_(PAID))
        .group_by(Movie.language)
        .order_by(func.count(Booking.booking_id).desc())
        .limit(8)
        .all()
    )
    return jsonify([
        {'language': r.language or 'Unknown',
         'bookings': int(r.bookings or 0),
         'revenue': round(float(r.revenue or 0), 2)}
        for r in rows
    ])


# Kept – revenue trend
# FIX: same as daily trend — use latest booking date in DB, not today's date.
# This makes seeded historical data visible instead of an empty chart.
@admin_analytics_bp.route('/api/revenue-trend')
@admin_required
def api_revenue_trend():
    latest = db.session.query(func.max(Booking.booking_date))\
        .filter(Booking.payment_status.in_(PAID)).scalar()

    if latest is None:
        return jsonify([])

    if isinstance(latest, datetime):
        end_date = latest
    else:
        end_date = datetime.combine(latest, datetime.max.time())

    start_date = end_date - timedelta(days=365)

    rows = (
        db.session.query(
            extract('year',  Booking.booking_date).label('yr'),
            extract('month', Booking.booking_date).label('mo'),
            func.sum(Booking.total_amount).label('revenue'),
            func.count(Booking.booking_id).label('bookings')
        )
        .filter(Booking.payment_status.in_(PAID))
        .filter(Booking.booking_date >= start_date)
        .filter(Booking.booking_date <= end_date)
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