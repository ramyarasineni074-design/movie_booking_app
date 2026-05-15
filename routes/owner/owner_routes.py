import json
import uuid
from datetime import datetime, date, time

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify, current_app, abort)
from sqlalchemy import func

from extensions import db
from models import AppUser, TheaterBrand, Theater, Show, Booking, Movie, Screen, Seat
from utils.decorators import owner_required, handle_exceptions

owner_bp = Blueprint('owner_bp', __name__, url_prefix='/owner')

PER_PAGE = 20


def paginate(query, page, per_page=PER_PAGE):
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return items, total, total_pages


# --------------------------------------------------
# HELPER: get owner's brand
# --------------------------------------------------
def get_owner_brand():
    owner_id = session.get('user_id')
    brand = TheaterBrand.query.filter_by(owner_id=owner_id).first()
    return brand


# --------------------------------------------------
# HELPER: build theater_screens_json for templates
# --------------------------------------------------
def build_theater_screens_json(brand_id):
    """Returns JSON string: { theater_id: [screen.to_dict(), ...] }"""
    theaters = Theater.query.filter_by(brand_id=brand_id)\
        .filter(~Theater.theater_id.like('LOC_%')).all()
    result = {}
    for t in theaters:
        result[t.theater_id] = [s.to_dict() for s in t.screens]
    return json.dumps(result)


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------
@owner_bp.route('/dashboard')
@owner_required
@handle_exceptions
def dashboard():
    brand = get_owner_brand()

    if not brand:
        return render_template('owner/no_brand.html')

    total_theaters = Theater.query.filter_by(brand_id=brand.brand_id)\
        .filter(~Theater.theater_id.like('LOC_%')).count()

    total_shows = db.session.query(func.count(Show.show_id))\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id).scalar() or 0

    total_bookings = db.session.query(func.count(Booking.booking_id))\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id).scalar() or 0

    total_revenue = db.session.query(func.sum(Booking.total_amount))\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id)\
        .filter(Booking.payment_status.in_(['completed'])).scalar() or 0


    top_movies = db.session.query(
        Movie.title,
        func.count(Booking.booking_id).label('bookings')
    ).join(Show, Show.movie_id == Movie.movie_id)\
     .join(Theater, Theater.theater_id == Show.theater_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Theater.brand_id == brand.brand_id)\
     .filter(Booking.payment_status == 'completed')\
     .group_by(Movie.title)\
     .order_by(func.count(Booking.booking_id).desc())\
     .limit(5).all()

    recent_bookings = db.session.query(Booking, Show, Movie)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Movie, Show.movie_id == Movie.movie_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id)\
        .order_by(Booking.booking_date.desc()).limit(5).all()

    theaters = Theater.query.filter_by(brand_id=brand.brand_id)\
        .filter(~Theater.theater_id.like('LOC_%'))\
        .order_by(Theater.name).limit(5).all()

    return render_template(
        'owner/dashboard.html',
        brand=brand,
        active_page='dashboard', 
        total_theaters=total_theaters,
        total_shows=total_shows,
        total_bookings=total_bookings,
        total_revenue=total_revenue,
        top_movies=top_movies,
        recent_bookings=recent_bookings,
        theaters=theaters
    )


# --------------------------------------------------
# THEATERS LIST + FILTER
# --------------------------------------------------
@owner_bp.route('/theaters')
@owner_required
@handle_exceptions
def theaters():
    brand = get_owner_brand()
    if not brand:
        return render_template('owner/no_brand.html')

    # Exclude location-anchor sentinel rows (theater_id starts with 'LOC_')
    query = Theater.query.filter_by(brand_id=brand.brand_id)\
        .filter(~Theater.theater_id.like('LOC_%'))

    state    = request.args.get('state', '').strip()
    city     = request.args.get('city', '').strip()
    location = request.args.get('location', '').strip()

    if state:    query = query.filter(Theater.state == state)
    if city:     query = query.filter(Theater.city == city)
    if location: query = query.filter(Theater.location.ilike(f'%{location}%'))

    PER_PAGE = 6
    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Theater.name).paginate(page=page, per_page=PER_PAGE, error_out=False)
    theaters_list = pagination.items

    all_brand_theaters = Theater.query.filter_by(brand_id=brand.brand_id)\
        .filter(~Theater.theater_id.like('LOC_%')).all()
    states = sorted({t.state for t in all_brand_theaters if t.state})
    if state:
        cities = sorted({t.city for t in all_brand_theaters if t.city and t.city != '(placeholder)' and t.state == state})
    else:
        cities = sorted({t.city for t in all_brand_theaters if t.city and t.city != '(placeholder)'})

    movies = Movie.query.order_by(Movie.title).all()
    theater_screens_json = build_theater_screens_json(brand.brand_id)

    return render_template(
        'owner/theaters.html',
        brand=brand,
        theaters=theaters_list,
        active_page='theaters',
        states=states,
        cities=cities,
        filter_state=state,
        filter_city=city,
        filter_location=location,
        movies=movies,
        theater_screens_json=theater_screens_json,
        owner_has_add_theater=True,
        page=page,
        total_pages=pagination.pages,
        total=pagination.total
    )


# --------------------------------------------------
# ADD THEATER
# --------------------------------------------------
@owner_bp.route('/theaters/add', methods=['POST'])
@owner_required
@handle_exceptions
def add_theater():
    brand = get_owner_brand()
    if not brand:
        flash('No brand assigned to your account. Contact admin.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    name        = request.form.get('name', '').strip()
    state       = request.form.get('state', '').strip()
    city        = request.form.get('city', '').strip()
    location    = request.form.get('location', '').strip()
    address     = request.form.get('address', '').strip()
    num_screens = int(request.form.get('num_screens', 1))

    if not name or not state or not city:
        flash('Theater name, state and city are required.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    theater_id = 'TH_' + str(uuid.uuid4())[:8].upper()
    theater = Theater(
        theater_id=theater_id,
        brand_id=brand.brand_id,
        name=name,
        state=state,
        city=city,
        location=location or address
    )
    db.session.add(theater)
    db.session.flush()

    for i in range(1, num_screens + 1):
        screen_name = request.form.get(f'screen_name_{i}', f'Screen {i}').strip()
        capacity    = request.form.get(f'capacity_{i}', 150)
        try:
            capacity = int(capacity)
        except (ValueError, TypeError):
            capacity = 150

        # Parse screen number from name like "Screen 3"
        parts = screen_name.split()
        screen_num = int(parts[-1]) if parts and parts[-1].isdigit() else i

        screen = Screen(
            screen_id='SC_' + str(uuid.uuid4())[:8].upper(),
            theater_id=theater_id,
            screen_number=screen_num,
            total_seats=capacity
        )
        db.session.add(screen)

    db.session.commit()
    flash(f'Theater "{name}" added with {num_screens} screen(s).', 'success')
    return redirect(url_for('owner_bp.theaters'))


# --------------------------------------------------
# THEATER DETAIL (shows + booking counts)
# --------------------------------------------------
@owner_bp.route('/theater/<theater_id>')
@owner_required
@handle_exceptions
def theater_detail(theater_id):
    brand = get_owner_brand()
    theater = db.session.get(Theater, theater_id)
    if not theater:
        abort(404)

    if theater.brand_id != brand.brand_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    shows = db.session.query(
        Show,
        Movie.title.label('movie_title'),
        func.count(Booking.booking_id).label('booked_count')
    ).join(Movie, Movie.movie_id == Show.movie_id)\
     .outerjoin(Booking, Booking.show_id == Show.show_id)\
     .filter(Show.theater_id == theater_id)\
     .group_by(Show.show_id, Movie.title)\
     .order_by(Show.show_date.desc(), Show.start_time.desc())\
     .all()

    screens    = Screen.query.filter_by(theater_id=theater_id).all()
    all_movies = Movie.query.order_by(Movie.title).all()

    theater_bookings = db.session.query(Booking)\
        .join(Show, Booking.show_id == Show.show_id)\
        .filter(Show.theater_id == theater_id).all()

    theater_revenue = sum(
        (b.total_amount or 0) for b in theater_bookings
        if b.payment_status in ('completed',)
    )

    return render_template(
        'owner/theater_detail.html',
        brand=brand,
        theater=theater,
        shows=shows,
        screens=screens,
        all_movies=all_movies,
        theater_bookings=theater_bookings,
        theater_revenue=theater_revenue
    )


# --------------------------------------------------
# ADD SHOW
# --------------------------------------------------
@owner_bp.route('/shows/add', methods=['POST'])
@owner_required
@handle_exceptions
def add_show():
    theater_id  = request.form.get('theater_id', '').strip()
    movie_id    = request.form.get('movie_id', '').strip()
    screen_id   = request.form.get('screen_id', '').strip()
    show_date   = request.form.get('show_date', '').strip()
    start_times = request.form.getlist('start_time')   # multiple slots
    price       = request.form.get('price', '').strip()

    # Filter out blank/disabled times
    start_times = [t.strip() for t in start_times if t.strip()]

    if not all([theater_id, movie_id, screen_id, show_date, price]) or not start_times:
        flash('All fields are required to add a show. Please select at least one time slot.', 'danger')
        return redirect(url_for('owner_bp.theater_detail', theater_id=theater_id or ''))

    screen = db.session.get(Screen, screen_id)
    if not screen:
        flash('Screen not found.', 'danger')
        return redirect(url_for('owner_bp.theater_detail', theater_id=theater_id))

    brand   = get_owner_brand()
    theater = db.session.get(Theater, theater_id)
    if not theater or theater.brand_id != brand.brand_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    # Create one show per selected time slot
    shows_added = 0
    for st in start_times:
        show = Show(
            show_id='SH_' + str(uuid.uuid4())[:8].upper(),
            movie_id=movie_id,
            theater_id=theater_id,
            screen_id=screen_id,
            show_date=date.fromisoformat(show_date),
            start_time=time.fromisoformat(st),
            price=float(price),
            available_seats=screen.total_seats,
            status='active'
        )
        db.session.add(show)
        shows_added += 1

    # Also create shows for extra theaters (multi-theater scheduling)
    extra_theater_ids = request.form.getlist('extra_theater_ids')
    extra_count = 0
    for extra_tid in extra_theater_ids:
        if extra_tid == theater_id:
            continue  # already added above
        extra_theater = db.session.get(Theater, extra_tid)
        if not extra_theater or extra_theater.brand_id != brand.brand_id:
            continue
        extra_screens = Screen.query.filter_by(theater_id=extra_tid).all()
        for extra_screen in extra_screens:
            for st in start_times:
                extra_show = Show(
                    show_id='SH_' + str(uuid.uuid4())[:8].upper(),
                    movie_id=movie_id,
                    theater_id=extra_tid,
                    screen_id=extra_screen.screen_id,
                    show_date=date.fromisoformat(show_date),
                    start_time=time.fromisoformat(st),
                    price=float(price),
                    available_seats=extra_screen.total_seats,
                    status='active'
                )
                db.session.add(extra_show)
                extra_count += 1

    db.session.commit()

    slot_word = f'{shows_added} show(s)' if shows_added > 1 else 'Show'
    if extra_count:
        flash(f'{slot_word} added successfully! Also scheduled in {len(extra_theater_ids)} additional theater(s).', 'success')
    else:
        flash(f'{slot_word} added successfully!', 'success')

    redirect_to = request.form.get('redirect_to', '')
    if redirect_to == 'shows':
        return redirect(url_for('owner_bp.shows'))
    return redirect(url_for('owner_bp.theater_detail', theater_id=theater_id))


# --------------------------------------------------
# ADD MOVIE TO THEATER  (creates a show from theaters page)
# --------------------------------------------------
@owner_bp.route('/theaters/add-movie', methods=['POST'])
@owner_required
@handle_exceptions
def add_movie_to_theater():
    theater_id  = request.form.get('theater_id', '').strip()
    movie_id    = request.form.get('movie_id', '').strip()
    screen_id   = request.form.get('screen_id', '').strip()
    show_date   = request.form.get('show_date', '').strip()
    start_time  = request.form.get('start_time', '').strip()
    price       = request.form.get('price', '').strip()
    show_lang   = request.form.get('show_language', '').strip()
    avail_seats = request.form.get('available_seats', '').strip()

    if not all([theater_id, movie_id, screen_id, show_date, start_time, price]):
        flash('Theater, movie, screen, date, time and price are all required.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    brand   = get_owner_brand()
    theater = db.session.get(Theater, theater_id)
    if not theater or theater.brand_id != brand.brand_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    screen = db.session.get(Screen, screen_id)
    if not screen or screen.theater_id != theater_id:
        flash('Screen not found or does not belong to this theater.', 'danger')
        return redirect(url_for('owner_bp.theaters'))

    seats = int(avail_seats) if avail_seats.isdigit() else screen.total_seats

    show = Show(
        show_id='SH_' + str(uuid.uuid4())[:8].upper(),
        movie_id=movie_id,
        theater_id=theater_id,
        screen_id=screen_id,
        show_date=date.fromisoformat(show_date),
        start_time=time.fromisoformat(start_time),
        price=float(price),
        available_seats=seats,
        status='active'
    )
    db.session.add(show)
    db.session.commit()

    movie = db.session.get(Movie, movie_id)
    flash(f'Movie "{movie.title if movie else ""}" added to {theater.name} successfully!', 'success')
    return redirect(url_for('owner_bp.theaters'))


# --------------------------------------------------
# CANCEL SHOW  (AJAX)
# --------------------------------------------------
@owner_bp.route('/shows/cancel/<show_id>', methods=['POST'])
@owner_required
@handle_exceptions
def cancel_show(show_id):
    show = db.session.get(Show, show_id)
    if not show:
        return jsonify({'success': False, 'message': 'Show not found'}), 404

    brand   = get_owner_brand()
    theater = db.session.get(Theater, show.theater_id)
    if not theater or theater.brand_id != brand.brand_id:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    show.status = 'cancelled'
    db.session.commit()

    return jsonify({'success': True, 'message': 'Show cancelled successfully',
                    'show': show.to_dict()})


# --------------------------------------------------
# ALL SHOWS  (paginated, across all theaters)
# --------------------------------------------------
@owner_bp.route('/shows')
@owner_required
@handle_exceptions
def shows():
    brand = get_owner_brand()
    if not brand:
        return render_template('owner/no_brand.html')

    # ← ADD theaters for the filter dropdown
    theaters = Theater.query.filter_by(brand_id=brand.brand_id).all()
    theater_screens_json = build_theater_screens_json(brand.brand_id)
    movies = Movie.query.order_by(Movie.title).all()
    today = date.today().isoformat()

    page     = int(request.args.get('page', 1))
    per_page = current_app.config.get('PAGE_SIZE', 8)

    query = db.session.query(Show, Movie, Theater)\
        .join(Movie, Movie.movie_id == Show.movie_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id)\
        .order_by(Show.show_date.desc())

    total       = query.count()
    results     = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        'owner/shows.html',
        active_page='shows',
        brand=brand,
        results=results,
        theaters=theaters,
        movies=movies,
        theater_screens_json=theater_screens_json,
        today=today,
        page=page,
        total=total,
        total_pages=total_pages,
        per_page=per_page,
    )

# --------------------------------------------------
# BOOKINGS  (paginated, for owner's theaters)
# --------------------------------------------------
@owner_bp.route('/bookings')
@owner_required
@handle_exceptions
def bookings():
    brand = get_owner_brand()
    if not brand:
        return render_template('owner/no_brand.html')

    page     = int(request.args.get('page', 1))
    per_page = current_app.config.get('PAGE_SIZE', 8)

    from models import User
    query = db.session.query(Booking, Show, Movie, Theater, User)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Movie, Show.movie_id == Movie.movie_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .join(User, Booking.user_id == User.user_id)\
        .filter(Theater.brand_id == brand.brand_id)\
        .order_by(Booking.booking_date.desc())

    total       = query.count()
    results     = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    all_bookings_q = db.session.query(Booking)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id)

    paid_count = all_bookings_q.filter(Booking.payment_status.in_(['completed'])).count()
    cancelled_count = all_bookings_q.filter(Booking.payment_status == 'cancelled').count()
    total_revenue   = db.session.query(func.sum(Booking.total_amount))\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Theater, Theater.theater_id == Show.theater_id)\
        .filter(Theater.brand_id == brand.brand_id,
                Booking.payment_status.in_(['completed'])).scalar() or 0

    return render_template(
        'owner/bookings.html',
        brand=brand,
        results=results,
        page=page,
        active_page='bookings',
        total=total,
        total_pages=total_pages,
        per_page=per_page,
        paid_count=paid_count,
        cancelled_count=cancelled_count,
        total_revenue=total_revenue
    )


@owner_bp.route('/movies')
@owner_required
@handle_exceptions
def movies():
    brand = get_owner_brand()

    if not brand:
        return render_template('owner/no_brand.html')

    page     = int(request.args.get('page', 1))
    search   = request.args.get('search', '').strip()
    genre    = request.args.get('genre', '').strip()
    language = request.args.get('language', '').strip()
    status   = request.args.get('status', '').strip()

    # 🔥 ONLY OWNER THEATERS
    all_theaters = [t for t in Theater.query.filter_by(brand_id=brand.brand_id).all() if t.screens and len(t.screens) > 0]

    # Build movie query with filters
    q = Movie.query
    if search:   q = q.filter(Movie.title.ilike(f'%{search}%'))
    if genre:    q = q.filter(Movie.genre.ilike(f'%{genre}%'))
    if language: q = q.filter(Movie.language.ilike(f'%{language}%'))
    if status:   q = q.filter(Movie.status == status)
    q = q.order_by(Movie.title)

    items, total, total_pages = paginate(q, page, PER_PAGE)

    # extra data for UI filters
    all_movies_qs = Movie.query.all()
    all_states = sorted({t.state for t in all_theaters if t.state})
    all_genres = sorted({m.genre for m in all_movies_qs if m.genre})
    all_langs  = sorted({m.language for m in all_movies_qs if m.language})

    return render_template(
        'owner/movies.html',
        movies=items,
        all_theaters=all_theaters,
        all_theaters_json=[t.to_dict() for t in all_theaters],
        all_states=all_states,
        all_genres=all_genres,
        all_langs=all_langs,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=PER_PAGE,
        search=search,
        genre=genre,
        language=language,
        status=status,
        active_page='movies'
    )


@owner_bp.route('/movies/add', methods=['POST'])
@owner_required
@handle_exceptions
def add_movie():
    title    = request.form.get('title', '').strip()
    genre    = request.form.get('genre', '').strip()
    language = request.form.get('language', '').strip()

    if not title:
        flash('Movie title is required.', 'danger')
        return redirect(url_for('owner_bp.movies'))

    # Duplicate check: same title + language + genre combination
    existing = Movie.query.filter(
        db.func.lower(Movie.title) == title.lower(),
        db.func.lower(db.func.coalesce(Movie.language, '')) == language.lower(),
        db.func.lower(db.func.coalesce(Movie.genre, '')) == genre.lower()
    ).first()
    if existing:
        flash(f'This movie is already there: "{title}" ({language}, {genre}).', 'warning')
        return redirect(url_for('owner_bp.movies'))

    movie = Movie(
        movie_id='MV_' + str(uuid.uuid4())[:8].upper(),
        title=title,
        genre=genre or None,
        language=language or None,
        duration=int(request.form.get('duration')) if request.form.get('duration') else None,
        rating=float(request.form.get('rating')) if request.form.get('rating') else None,
        release_date=date.fromisoformat(request.form.get('release_date')) if request.form.get('release_date') else None,
        description=request.form.get('description'),
        status=request.form.get('status', 'active'),
        poster_url=request.form.get('poster_url')
    )

    db.session.add(movie)
    db.session.commit()

    flash(f'Movie "{movie.title}" added successfully.', 'success')
    return redirect(url_for('owner_bp.movies'))


@owner_bp.route('/movies/edit/<movie_id>', methods=['POST'])
@owner_required
@handle_exceptions
def edit_movie(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie:
        flash('Movie not found.', 'danger')
        return redirect(url_for('owner_bp.movies'))

    new_title    = request.form.get('title', movie.title).strip()
    new_genre    = request.form.get('genre', movie.genre or '').strip()
    new_language = request.form.get('language', movie.language or '').strip()

    # Duplicate check (exclude self)
    existing = Movie.query.filter(
        Movie.movie_id != movie_id,
        db.func.lower(Movie.title) == new_title.lower(),
        db.func.lower(db.func.coalesce(Movie.language, '')) == new_language.lower(),
        db.func.lower(db.func.coalesce(Movie.genre, '')) == new_genre.lower()
    ).first()
    if existing:
        flash(f'This movie is already there: "{new_title}" ({new_language}, {new_genre}).', 'warning')
        return redirect(url_for('owner_bp.movies'))

    movie.title    = new_title
    movie.genre    = new_genre or movie.genre
    movie.language = new_language or movie.language
    movie.status   = request.form.get('status', movie.status)
    movie.description = request.form.get('description', movie.description or '')

    d = request.form.get('duration')
    if d: movie.duration = int(d)
    r = request.form.get('rating')
    if r: movie.rating = float(r)
    rd = request.form.get('release_date', '').strip()
    if rd: movie.release_date = date.fromisoformat(rd)

    pu   = request.form.get('poster_url', '').strip()
    file = request.files.get('poster_file')
    if file and file.filename:
        import os
        from werkzeug.utils import secure_filename
        folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
        os.makedirs(folder, exist_ok=True)
        fname = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        file.save(os.path.join(folder, fname))
        movie.poster_url = f'/static/uploads/{fname}'
    elif pu:
        movie.poster_url = pu

    db.session.commit()
    flash(f'Movie "{movie.title}" updated.', 'success')
    return redirect(url_for('owner_bp.movies'))


@owner_bp.route('/movies/delete/<movie_id>', methods=['POST'])
@owner_required
@handle_exceptions
def delete_movie(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie:
        flash('Movie not found.', 'danger')
        return redirect(url_for('owner_bp.movies'))
    title = movie.title
    db.session.delete(movie)
    db.session.commit()
    flash(f'Movie "{title}" deleted.', 'success')
    return redirect(url_for('owner_bp.movies'))



@owner_bp.route('/movies/assign-theaters', methods=['POST'])
@owner_required
@handle_exceptions
def assign_movie_theaters():
    movie_id = request.form.get('movie_id')
    theater_ids = request.form.getlist('theater_ids')

    if not movie_id or not theater_ids:
        flash('Please select movie and theaters.', 'danger')
        return redirect(url_for('owner_bp.movies'))

    brand = get_owner_brand()
    if not brand:
        flash('No brand found.', 'danger')
        return redirect(url_for('owner_bp.movies'))

    # 🔥 FILTER ONLY OWNER THEATERS
    valid_theaters = Theater.query.filter(
        Theater.theater_id.in_(theater_ids),
        Theater.brand_id == brand.brand_id   # ✅ THIS IS THE KEY
    ).all()

    if not valid_theaters:
        flash('No valid theaters selected.', 'danger')
        return redirect(url_for('owner_bp.movies'))

    created_count = 0

    for theater in valid_theaters:
        screens = Screen.query.filter_by(theater_id=theater.theater_id).all()

        for screen in screens:
            show = Show(
                show_id='SH_' + str(uuid.uuid4())[:8].upper(),
                movie_id=movie_id,
                theater_id=theater.theater_id,
                screen_id=screen.screen_id,
                show_date=date.today(),   # default (you can customize later)
                start_time=time(9, 0),    # default time
                price=150.0,
                available_seats=screen.total_seats,
                status='active'
            )
            db.session.add(show)
            created_count += 1

    db.session.commit()

    flash(f'Movie assigned to {len(valid_theaters)} theaters ({created_count} shows created).', 'success')
    return redirect(url_for('owner_bp.movies'))

# --------------------------------------------------
# REVENUE ANALYTICS
# --------------------------------------------------
@owner_bp.route('/revenue')
@owner_required
@handle_exceptions
def revenue():
    brand = get_owner_brand()
    if not brand:
        return render_template('owner/no_brand.html')

    paid_statuses = ['completed']

    theaters = Theater.query.filter_by(brand_id=brand.brand_id).all()
    theater_ids = [t.theater_id for t in theaters]

    # Total revenue
    total_revenue = db.session.query(func.sum(Booking.total_amount))\
        .join(Show, Booking.show_id == Show.show_id)\
        .filter(Show.theater_id.in_(theater_ids))\
        .filter(Booking.payment_status.in_(paid_statuses)).scalar() or 0

    # Total bookings (paid)
    total_paid_bookings = db.session.query(func.count(Booking.booking_id))\
        .join(Show, Booking.show_id == Show.show_id)\
        .filter(Show.theater_id.in_(theater_ids))\
        .filter(Booking.payment_status.in_(paid_statuses)).scalar() or 0

    # Average ticket value
    avg_ticket = (total_revenue / total_paid_bookings) if total_paid_bookings else 0

    # Revenue by movie (top 10)
    movie_revenue = db.session.query(
        Movie.title,
        func.count(Booking.booking_id).label('bookings'),
        func.sum(Booking.total_amount).label('revenue')
    ).join(Show, Show.movie_id == Movie.movie_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Show.theater_id.in_(theater_ids))\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Movie.title)\
     .order_by(func.sum(Booking.total_amount).desc()).limit(10).all()

    # Revenue by theater
    theater_revenue = db.session.query(
        Theater.name,
        Theater.city,
        func.count(Booking.booking_id).label('bookings'),
        func.sum(Booking.total_amount).label('revenue')
    ).join(Show, Show.theater_id == Theater.theater_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Theater.brand_id == brand.brand_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Theater.theater_id, Theater.name, Theater.city)\
     .order_by(func.sum(Booking.total_amount).desc()).all()

    # Monthly revenue (last 6 months) — date-agnostic grouping
    monthly_revenue = db.session.query(
        func.to_char(Booking.booking_date,'YYYY-MM').label('month'),
        func.sum(Booking.total_amount).label('revenue'),
        func.count(Booking.booking_id).label('bookings')
    ).join(Show, Booking.show_id == Show.show_id)\
     .filter(Show.theater_id.in_(theater_ids))\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(func.to_char(Booking.booking_date,'YYYY-MM'))\
     .order_by(func.to_char(Booking.booking_date,'YYYY-MM').desc())\
     .limit(6).all()

    # Recent transactions
    recent_transactions = db.session.query(Booking, Show, Movie, Theater)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Movie, Show.movie_id == Movie.movie_id)\
        .join(Theater, Show.theater_id == Theater.theater_id)\
        .filter(Theater.brand_id == brand.brand_id)\
        .filter(Booking.payment_status.in_(paid_statuses))\
        .order_by(Booking.booking_date.desc()).limit(10).all()

    return render_template(
        'owner/revenue.html',
        brand=brand,
        active_page='revenue',
        total_revenue=total_revenue,
        total_paid_bookings=total_paid_bookings,
        avg_ticket=avg_ticket,
        movie_revenue=movie_revenue,
        theater_revenue=theater_revenue,
        monthly_revenue=list(reversed(monthly_revenue)),
        recent_transactions=recent_transactions
    )


# --------------------------------------------------
# OCCUPANCY ANALYTICS
# --------------------------------------------------
@owner_bp.route('/occupancy')
@owner_required
@handle_exceptions
def occupancy():
    brand = get_owner_brand()
    if not brand:
        return render_template('owner/no_brand.html')

    theaters = Theater.query.filter_by(brand_id=brand.brand_id).all()
    theater_ids = [t.theater_id for t in theaters]

    # Per-theater occupancy
    theater_occupancy = []
    for theater in theaters:
        screens = Screen.query.filter_by(theater_id=theater.theater_id).all()
        total_capacity = sum(s.total_seats or 0 for s in screens)

        total_booked = db.session.query(func.sum(Booking.total_tickets))\
            .join(Show, Booking.show_id == Show.show_id)\
            .filter(Show.theater_id == theater.theater_id)\
            .filter(Booking.payment_status.in_(['completed']))

        total_shows = Show.query.filter_by(theater_id=theater.theater_id).count()
        total_possible = total_capacity * total_shows if total_shows > 0 else 0
        occ_pct = round((total_booked / total_possible * 100), 1) if total_possible > 0 else 0

        theater_occupancy.append({
            'name': theater.name,
            'city': theater.city,
            'screens': len(screens),
            'total_capacity': total_capacity,
            'total_booked': total_booked,
            'total_shows': total_shows,
            'occupancy_pct': occ_pct
        })

    # Per-movie occupancy
    movie_occupancy = db.session.query(
        Movie.title,
        func.count(Show.show_id).label('total_shows'),
        func.sum(Booking.total_tickets).label('booked'),
        func.sum(Show.available_seats).label('capacity')
    ).join(Show, Show.movie_id == Movie.movie_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Show.theater_id.in_(theater_ids))\
     .filter(Booking.payment_status.in_(['completed']))\
     .group_by(Movie.title)\
     .order_by(func.sum(Booking.total_tickets).desc()).limit(10).all()

    # Overall totals
    total_capacity = sum(t['total_capacity'] for t in theater_occupancy)
    total_booked_all = sum(t['total_booked'] for t in theater_occupancy)
    total_shows_all = sum(t['total_shows'] for t in theater_occupancy)
    overall_occ = round((total_booked_all / (total_capacity * total_shows_all) * 100), 1) \
        if (total_capacity and total_shows_all) else 0

    return render_template(
        'owner/occupancy.html',
        brand=brand,
        active_page='occupancy',
        theater_occupancy=theater_occupancy,
        movie_occupancy=movie_occupancy,
        total_capacity=total_capacity,
        total_booked_all=total_booked_all,
        total_shows_all=total_shows_all,
        overall_occ=overall_occ
    )

@owner_bp.route('/locations/add', methods=['POST'])
@owner_required
@handle_exceptions
def add_location():
    # Just call the same logic
    from routes.admin import add_location as admin_add_location
    return admin_add_location()