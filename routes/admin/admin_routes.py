import os, uuid, secrets, string
from datetime import date, time

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify, current_app)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, distinct

from extensions import db, mail
from flask_mail import Message
from models import (AppUser, User, Role, Movie, Theater, TheaterBrand,
                    Show, Booking, Screen, Seat, Payment, Review)
from utils.decorators import admin_required, handle_exceptions

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')

PER_PAGE = 20   # rows per page for all admin tables

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def gen_password(length=10):
    chars = string.ascii_letters + string.digits  # removed special characters
    return ''.join(secrets.choice(chars) for _ in range(length))


def send_credentials_email(to_email, user_name, role, login_email, plain_pw, brand_name=None):
    try:
        msg = Message(
            subject=f'CineBook — {role.title()} Account Created',
            recipients=[to_email]
        )
        msg.body = (
            f"Hello {user_name},\n\n"
            f"Your CineBook {role.title()} account has been created.\n\n"
            f"Login Details\n"
            f"─────────────\n"
            f"Role     : {role.title()}\n"
            f"Name     : {user_name}\n"
            f"Email    : {login_email}\n"
            f"Password : {plain_pw}\n"
        )
        if brand_name:
            msg.body += f"Brand    : {brand_name}\n"

        msg.body += (
            f"\n"
            f"Login at: http://localhost:5000/login\n"
            f"Please change your password after first login.\n\n"
            f"Regards,\nCineBook Admin Team"
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f'Email error: {e}')
        return False
    
    

def save_file(file):
    if not file or file.filename == '':
        return None
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png','jpg','jpeg','gif','webp'})
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return None
    folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
    os.makedirs(folder, exist_ok=True)
    fname = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(folder, fname))
    return fname


def paginate(query, page, per_page=PER_PAGE):
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return items, total, total_pages


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/dashboard')
@admin_required
@handle_exceptions
def dashboard():
    total_movies   = Movie.query.count()
    total_theaters = Theater.query.count()
    total_bookings = Booking.query.count()
    total_users    = AppUser.query.count()

    paid_statuses = ['completed']


    revenue = db.session.query(func.sum(Booking.total_amount))\
        .filter(Booking.payment_status.in_(paid_statuses)).scalar() or 0

    top_movies = db.session.query(
        Movie.title,
        func.count(Booking.booking_id).label('bookings'),
        func.sum(Booking.total_amount).label('revenue')
    ).join(Show, Show.movie_id == Movie.movie_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Movie.title)\
     .order_by(func.count(Booking.booking_id).desc()).limit(5).all()

    top_theaters = db.session.query(
        Theater.name,
        func.count(Booking.booking_id).label('bookings'),
        func.sum(Booking.total_amount).label('revenue')
    ).join(Show, Show.theater_id == Theater.theater_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Theater.name)\
     .order_by(func.sum(Booking.total_amount).desc()).limit(5).all()

    raw_recent = db.session.query(Booking, Show, Movie, Theater, User)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Movie, Show.movie_id == Movie.movie_id)\
        .join(Theater, Show.theater_id == Theater.theater_id)\
        .join(User, Booking.user_id == User.user_id)\
        .order_by(Booking.booking_date.desc()).limit(8).all()

    # Build flat dicts so templates can access b.user_name, b.movie_title etc.
    recent_bookings = []
    for b, s, m, t, u in raw_recent:
        recent_bookings.append({
            'booking_id':     b.booking_id,
            'user_name':      u.name if u else '–',
            'movie_title':    m.title if m else '–',
            'theater_name':   t.name if t else '–',
            'seat_numbers':   b.seat_numbers or '–',
            'total_amount':   b.total_amount or 0,
            'payment_status': b.payment_status or '–',
            'booking_date':   b.booking_date,
        })

    # Additional dashboard stats
    owner_role = Role.query.filter_by(role_name='owner').first()
    total_owners      = AppUser.query.filter_by(role_id=owner_role.role_id).count() if owner_role else 0
    active_shows      = Show.query.filter_by(status='active').count()
    cancelled_bookings= Booking.query.filter_by(payment_status='cancelled').count()

    return render_template('admin/dashboard.html',
        active_page='dashboard',
        total_movies=total_movies, total_theaters=total_theaters,
        total_bookings=total_bookings, total_users=total_users,
        total_owners=total_owners, active_shows=active_shows,
        cancelled_bookings=cancelled_bookings,
        revenue=revenue, top_movies=top_movies, top_theaters=top_theaters,
        recent_bookings=recent_bookings)


# ─────────────────────────────────────────────────────────────
# MOVIES  (paginated, 100 per page, view modal, add/edit/delete)
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/movies')
@admin_required
@handle_exceptions
def movies():
    page   = int(request.args.get('page', 1))
    search = request.args.get('search', '').strip()
    genre  = request.args.get('genre', '').strip()
    lang   = request.args.get('language', '').strip()
    status = request.args.get('status', '').strip()

    q = Movie.query
    if search: q = q.filter(Movie.title.ilike(f'%{search}%'))
    if genre:  q = q.filter(Movie.genre.ilike(f'%{genre}%'))
    if lang:   q = q.filter(Movie.language.ilike(f'%{lang}%'))
    if status: q = q.filter(Movie.status == status)
    q = q.order_by(Movie.release_date.desc())

    items, total, total_pages = paginate(q, page, PER_PAGE)

    all_genres = sorted({m.genre.strip() for m in Movie.query.all() if m.genre and m.genre.strip()})
    all_langs  = sorted({m.language.strip() for m in Movie.query.all() if m.language and m.language.strip()})

    # ✅ ADD THESE
    all_theaters = Theater.query.order_by(Theater.state, Theater.city, Theater.name).all()
    all_states   = sorted({t.state for t in all_theaters if t.state})
    all_theaters_json = [
        {
            'theater_id': t.theater_id,
            'name':       t.name,
            'state':      t.state or '',
            'city':       t.city or '',
        }
        for t in all_theaters
    ]

    all_brands = TheaterBrand.query.order_by(TheaterBrand.brand_name).all()
    return render_template('admin/movies.html',
        active_page='movies', movies=items,
        total=total, page=page, total_pages=total_pages, per_page=PER_PAGE,
        search=search, genre=genre, language=lang, status=status,
        all_genres=all_genres, all_langs=all_langs,
        # ✅ ADD THESE
        all_theaters=all_theaters,
        all_states=all_states,
        all_brands=all_brands,
        all_theaters_json=all_theaters_json)



@admin_bp.route('/movies/edit/<movie_id>', methods=['POST'])
@admin_required
@handle_exceptions
def edit_movie(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie:
        flash('Movie not found.', 'danger')
        return redirect(url_for('admin_bp.movies'))

    movie.title    = request.form.get('title', movie.title).strip()
    movie.genre    = request.form.get('genre', movie.genre or '').strip()
    movie.language = request.form.get('language', movie.language or '').strip()
    movie.status   = request.form.get('status', movie.status)
    movie.description = request.form.get('description', movie.description or '')

    # Duplicate check (exclude self)
    existing = Movie.query.filter(
        Movie.movie_id != movie_id,
        db.func.lower(Movie.title) == movie.title.lower(),
        db.func.lower(db.func.coalesce(Movie.language, '')) == movie.language.lower(),
        db.func.lower(db.func.coalesce(Movie.genre, '')) == movie.genre.lower()
    ).first()
    if existing:
        flash(f'This movie is already there: "{movie.title}" ({movie.language}, {movie.genre}).', 'warning')
        return redirect(url_for('admin_bp.movies'))

    d = request.form.get('duration')
    if d: movie.duration = int(d)
    r = request.form.get('rating')
    if r: movie.rating = float(r)
    rd = request.form.get('release_date','').strip()
    if rd: movie.release_date = date.fromisoformat(rd)

    pu = request.form.get('poster_url','').strip()
    file = request.files.get('poster_file')
    if file and file.filename:
        saved = save_file(file)
        if saved:
            movie.poster_url = f'/static/uploads/{saved}'
    elif pu:
        movie.poster_url = pu

    db.session.commit()
    flash(f'Movie "{movie.title}" updated.', 'success')
    return redirect(url_for('admin_bp.movies'))


@admin_bp.route('/movies/delete/<movie_id>', methods=['POST'])
@admin_required
@handle_exceptions
def delete_movie(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie:
        flash('Movie not found.', 'danger')
        return redirect(url_for('admin_bp.movies'))
    title = movie.title
    db.session.delete(movie)
    db.session.commit()
    flash(f'Movie "{title}" deleted.', 'success')
    return redirect(url_for('admin_bp.movies'))


@admin_bp.route('/movies/toggle/<movie_id>', methods=['POST'])
@admin_required
@handle_exceptions
def toggle_movie(movie_id):
    movie = db.session.get(Movie, movie_id)
    if not movie:
        return jsonify({'success': False}), 404
    movie.status = 'inactive' if movie.status == 'active' else 'active'
    db.session.commit()
    return jsonify({'success': True, 'status': movie.status})

# ─────────────────────────────────────────
# BRAND FILTER APIs (NEW)
# ─────────────────────────────────────────

@admin_bp.route('/api/brand-states')
@admin_required
def get_brand_states():
    brand_id = request.args.get('brand_id')

    states = db.session.query(distinct(Theater.state))\
        .filter(Theater.brand_id == brand_id).all()

    return jsonify([s[0] for s in states if s[0]])


@admin_bp.route('/api/brand-cities')
@admin_required
def get_brand_cities():
    brand_id = request.args.get('brand_id')
    state = request.args.get('state')

    cities = db.session.query(distinct(Theater.city))\
        .filter(Theater.brand_id == brand_id, Theater.state == state).all()

    return jsonify([c[0] for c in cities if c[0]])


@admin_bp.route('/api/brand-theaters')
@admin_required
def get_brand_theaters():
    brand_id = request.args.get('brand_id')
    state = request.args.get('state')
    city = request.args.get('city')

    theaters = Theater.query.filter_by(
        brand_id=brand_id,
        state=state,
        city=city
    ).all()

    return jsonify([
    {
        'theater_id': t.theater_id,
        'name': t.name,
        'brand': t.brand.brand_name if t.brand else '',
        'city': t.city,
        'state': t.state,
        'screens': len(t.screens) if t.screens else 0
    }
    for t in theaters
    if t.screens and len(t.screens) > 0
])


# ─────────────────────────────────────────────────────────────
# THEATERS  (paginated, full CRUD, filters by owner/state/city/location)
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/theaters')
@admin_required
@handle_exceptions
def theaters():
    page     = int(request.args.get('page', 1))
    search   = request.args.get('search', '').strip()
    state    = request.args.get('state', '').strip()
    city     = request.args.get('city', '').strip()
    location = request.args.get('location', '').strip()
    brand_id = request.args.get('brand_id', '').strip()
    owner_id = request.args.get('owner_id', '').strip()

    # Exclude location-anchor sentinel rows (theater_id starts with 'LOC_')
    q = Theater.query.filter(~Theater.theater_id.like('LOC_%'))
    if search:   q = q.filter(Theater.name.ilike(f'%{search}%'))
    if state:    q = q.filter(Theater.state.ilike(f'%{state}%'))
    if city:     q = q.filter(Theater.city.ilike(f'%{city}%'))
    if location: q = q.filter(Theater.location.ilike(f'%{location}%'))
    if brand_id: q = q.filter(Theater.brand_id == brand_id)
    if owner_id:
        # filter theaters whose brand belongs to this owner
        brand_ids = [b.brand_id for b in TheaterBrand.query.filter_by(owner_id=int(owner_id)).all()]
        if brand_ids:
            q = q.filter(Theater.brand_id.in_(brand_ids))
        else:
            q = q.filter(False)

    q = q.order_by(Theater.state, Theater.city, Theater.name)
    items, total, total_pages = paginate(q, page, PER_PAGE)

    brands = TheaterBrand.query.order_by(TheaterBrand.brand_name).all()
    # owners who are theater owners
    owner_role = Role.query.filter_by(role_name='owner').first()
    owners = AppUser.query.filter_by(role_id=owner_role.role_id).all() if owner_role else []

    # distinct states/cities for filter dropdowns (exclude sentinels and placeholders)
    real_theaters = Theater.query.filter(~Theater.theater_id.like('LOC_%')).all()
    all_states    = sorted({t.state for t in real_theaters if t.state})
    all_cities    = sorted({t.city for t in real_theaters if t.city and t.city != '(placeholder)'})

    return render_template('admin/theaters.html',
        active_page='theaters',
        theaters=items, total=total, page=page, total_pages=total_pages, per_page=PER_PAGE,
        brands=brands, owners=owners,
        all_states=all_states, all_cities=all_cities,
        search=search, state=state, city=city, location=location,
        brand_id=brand_id, owner_id=owner_id)


@admin_bp.route('/theaters/add', methods=['POST'])
@admin_required
@handle_exceptions
def add_theater():
    name     = request.form.get('name','').strip()
    brand_id = request.form.get('brand_id','').strip()
    state    = request.form.get('state','').strip()
    city     = request.form.get('city','').strip()
    location = request.form.get('location','').strip()
    address  = request.form.get('address','').strip()
    owner_id = request.form.get('owner_id','').strip()

    if not name:
        flash('Theater name is required.', 'danger')
        return redirect(url_for('admin_bp.theaters'))

    # If no brand but owner selected, create a brand (or reuse existing by same name)
    if not brand_id and owner_id:
        brand_name = request.form.get('brand_name', name).strip() or name
        existing_brand = TheaterBrand.query.filter(
            db.func.lower(TheaterBrand.brand_name) == brand_name.lower()
        ).first()
        if existing_brand:
            brand_id = existing_brand.brand_id
            existing_brand.owner_id = int(owner_id)
        else:
            brand = TheaterBrand(
                brand_id='BR_' + str(uuid.uuid4())[:6].upper(),
                brand_name=brand_name,
                owner_id=int(owner_id)
            )
            db.session.add(brand)
            db.session.flush()
            brand_id = brand.brand_id

    theater = Theater(
        theater_id='TH_' + str(uuid.uuid4())[:6].upper(),
        name=name,
        brand_id=brand_id or None,
        state=state, city=city,
        location=location or address,
    )
    db.session.add(theater)

    # Add screens
    n_screens = int(request.form.get('num_screens', 1) or 1)
    for i in range(1, n_screens + 1):
        cap  = request.form.get(f'screen_capacity_{i}', 150)
        sname= request.form.get(f'screen_name_{i}', f'Screen {i}')
        scr  = Screen(
            screen_id=f'SC_{uuid.uuid4().hex[:6].upper()}',
            theater_id=theater.theater_id,
            screen_number=i,
            total_seats=int(cap) if cap else 150
        )
        db.session.add(scr)

    db.session.commit()
    flash(f'Theater "{name}" added successfully.', 'success')
    return redirect(url_for('admin_bp.theaters'))


@admin_bp.route('/theaters/edit/<theater_id>', methods=['POST'])
@admin_required
@handle_exceptions
def edit_theater(theater_id):
    t = db.session.get(Theater, theater_id)
    if not t:
        flash('Theater not found.', 'danger')
        return redirect(url_for('admin_bp.theaters'))

    t.name     = request.form.get('name', t.name).strip()
    t.state    = request.form.get('state', t.state or '').strip()
    t.city     = request.form.get('city', t.city or '').strip()
    t.location = request.form.get('location', t.location or '').strip()
    bid = request.form.get('brand_id','').strip()
    if bid: t.brand_id = bid

    # Reassign brand owner if owner_id provided
    oid = request.form.get('owner_id','').strip()
    if oid and t.brand:
        t.brand.owner_id = int(oid)

    db.session.commit()
    flash(f'Theater "{t.name}" updated.', 'success')
    return redirect(url_for('admin_bp.theaters'))


@admin_bp.route('/theaters/delete/<theater_id>', methods=['POST'])
@admin_required
@handle_exceptions
def delete_theater(theater_id):
    t = db.session.get(Theater, theater_id)
    if not t:
        flash('Theater not found.', 'danger')
        return redirect(url_for('admin_bp.theaters'))
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f'Theater "{name}" deleted.', 'success')
    return redirect(url_for('admin_bp.theaters'))


# ─────────────────────────────────────────────────────────────
# THEATER OWNERS  (add + send credentials email; CRUD)
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/owners')
@admin_required
@handle_exceptions
def owners():
    page   = int(request.args.get('page', 1))
    search = request.args.get('search', '').strip()

    owner_role = Role.query.filter_by(role_name='owner').first()
    q = AppUser.query
    if owner_role:
        q = q.filter_by(role_id=owner_role.role_id)
    if search:
        q = q.filter(
            db.or_(AppUser.name.ilike(f'%{search}%'), AppUser.email.ilike(f'%{search}%'))
        )
    q = q.order_by(AppUser.name)
    items, total, total_pages = paginate(q, page, PER_PAGE)
    brands = TheaterBrand.query.order_by(TheaterBrand.brand_name).all()

    # ← ADD THIS: collect brand IDs that already have an owner
    assigned_brand_ids = {b.brand_id for b in brands if b.owner_id is not None}

    return render_template('admin/owners.html',
        active_page='owners', owners=items,
        total=total, page=page, total_pages=total_pages, per_page=PER_PAGE,
        search=search, brands=brands,
        assigned_brand_ids=assigned_brand_ids)  # ← pass it



@admin_bp.route('/owners/create', methods=['POST'])
@admin_required
@handle_exceptions
def create_owner():
    name       = request.form.get('name','').strip()
    email      = request.form.get('email','').strip()
    brand_name = request.form.get('brand_name','').strip()
    brand_id   = request.form.get('brand_id','').strip()

    if not name or not email:
        flash('Name and email are required.', 'danger')
        return redirect(url_for('admin_bp.owners'))
    if AppUser.query.filter_by(email=email).first():
        flash('Email already exists.', 'danger')
        return redirect(url_for('admin_bp.owners'))

    owner_role = Role.query.filter_by(role_name='owner').first()
    if not owner_role:
        owner_role = Role(role_name='owner')
        db.session.add(owner_role)
        db.session.flush()

    plain_pw = gen_password()
    new_owner = AppUser(
        name=name, email=email,
        password=generate_password_hash(plain_pw),
        role_id=owner_role.role_id,
        is_first_login=True, is_active=True
    )
    db.session.add(new_owner)
    db.session.flush()

    # Create brand if name provided and no existing brand selected
    if brand_name and not brand_id:
        # Check if a brand with this name already exists; reuse it instead of creating a duplicate
        existing_brand = TheaterBrand.query.filter(
            db.func.lower(TheaterBrand.brand_name) == brand_name.lower()
        ).first()
        if existing_brand:
            existing_brand.owner_id = new_owner.id
        else:
            brand = TheaterBrand(
                brand_id='BR_' + str(uuid.uuid4())[:6].upper(),
                brand_name=brand_name,
                owner_id=new_owner.id
            )
            db.session.add(brand)
    elif brand_id:
        # Assign existing brand to this owner
        brand = db.session.get(TheaterBrand, brand_id)
        if brand:
            brand.owner_id = new_owner.id

    db.session.commit()

    email_sent = send_credentials_email(email, name, 'owner', email, plain_pw)
    if email_sent:
        flash(f'Owner "{name}" created. Credentials sent to {email}.', 'success')
    else:
        flash(
            f'Owner "{name}" created successfully. '
            f'Email delivery failed — temporary password: <strong>{plain_pw}</strong>. '
            f'Please share it manually.',
            'warning'
        )
    return redirect(url_for('admin_bp.owners'))


@admin_bp.route('/owners/edit/<int:owner_id>', methods=['POST'])
@admin_required
@handle_exceptions
def edit_owner(owner_id):
    owner = db.session.get(AppUser, owner_id)
    if not owner:
        flash('Owner not found.', 'danger')
        return redirect(url_for('admin_bp.owners'))
    owner.name  = request.form.get('name', owner.name).strip()
    owner.email = request.form.get('email', owner.email).strip()
    bid = request.form.get('brand_id','').strip()
    if bid:
        brand = db.session.get(TheaterBrand, bid)
        if brand:
            brand.owner_id = owner_id
    db.session.commit()
    flash(f'Owner "{owner.name}" updated.', 'success')
    return redirect(url_for('admin_bp.owners'))


@admin_bp.route('/owners/delete/<int:owner_id>', methods=['POST'])
@admin_required
@handle_exceptions
def delete_owner(owner_id):
    owner = db.session.get(AppUser, owner_id)
    if not owner:
        flash('Owner not found.', 'danger')
        return redirect(url_for('admin_bp.owners'))
    name = owner.name
    db.session.delete(owner)
    db.session.commit()
    flash(f'Owner "{name}" deleted.', 'success')
    return redirect(url_for('admin_bp.owners'))


@admin_bp.route('/owners/toggle/<int:owner_id>', methods=['POST'])
@admin_required
@handle_exceptions
def toggle_owner(owner_id):
    owner = db.session.get(AppUser, owner_id)
    if not owner:
        return jsonify({'success': False}), 404
    owner.is_active = not owner.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': owner.is_active})


@admin_bp.route('/owners/resend-credentials/<int:owner_id>', methods=['POST'])
@admin_required
@handle_exceptions
def resend_credentials(owner_id):
    owner = db.session.get(AppUser, owner_id)
    if not owner:
        return jsonify({'success': False, 'message': 'Owner not found'}), 404
    plain_pw = gen_password()
    owner.password = generate_password_hash(plain_pw)
    owner.is_first_login = True
    db.session.commit()
    sent = send_credentials_email(owner.email, owner.name, 'owner', owner.email, plain_pw)
    if sent:
        return jsonify({'success': True, 'message': 'New credentials sent to email!'})
    return jsonify({
        'success': False,
        'message': f'Email delivery failed. Temporary password: {plain_pw} — share manually.'
    })


# ─────────────────────────────────────────────────────────────
# PARTNERSHIP REQUESTS  (approve → auto-create owner account + email)
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/partnerships')
@admin_required
@handle_exceptions
def partnerships():
    from models import PartnershipRequest
    page   = int(request.args.get('page', 1))
    status = request.args.get('status','').strip()

    q = PartnershipRequest.query
    if status: q = q.filter(PartnershipRequest.status == status)
    q = q.order_by(PartnershipRequest.created_at.desc())
    items, total, total_pages = paginate(q, page, PER_PAGE)
    pending = PartnershipRequest.query.filter_by(status='pending').count()

    return render_template('admin/partnerships.html',
        active_page='partnerships',
        requests=items, total=total, page=page, total_pages=total_pages,
        pending_count=pending, status_filter=status)


@admin_bp.route('/partnerships/<int:req_id>/approve', methods=['POST'])
@admin_required
@handle_exceptions
def approve_partnership(req_id):
    from models import PartnershipRequest
    req = PartnershipRequest.query.get_or_404(req_id)

    if req.status != 'pending':
        return jsonify({'success': False, 'message': 'Already processed'}), 400

    # Check duplicate
    if AppUser.query.filter_by(email=req.owner_email).first():
        req.status = 'approved'
        db.session.commit()
        return jsonify({'success': False,
                        'message': 'Email already has an account. Status marked approved.'})

    owner_role = Role.query.filter_by(role_name='owner').first()
    if not owner_role:
        owner_role = Role(role_name='owner')
        db.session.add(owner_role)
        db.session.flush()

    plain_pw  = gen_password()
    new_owner = AppUser(
        name=req.owner_name, email=req.owner_email,
        password=generate_password_hash(plain_pw),
        role_id=owner_role.role_id,
        is_first_login=True, is_active=True
    )
    db.session.add(new_owner)
    db.session.flush()

    # Create brand from request
    brand = TheaterBrand(
        brand_id='BR_' + str(uuid.uuid4())[:6].upper(),
        brand_name=req.brand_name,
        owner_id=new_owner.id
    )
    db.session.add(brand)
    req.status = 'approved'
    db.session.commit()

    sent = send_credentials_email(req.owner_email, req.owner_name, 'owner', req.owner_email, plain_pw)
    return jsonify({
        'success': True,
        'message': f'Owner account created for {req.owner_name}. ' +
                   ('Credentials emailed.' if sent else 'Email failed — check server logs.')
    })


@admin_bp.route('/partnerships/<int:req_id>/reject', methods=['POST'])
@admin_required
@handle_exceptions
def reject_partnership(req_id):
    from models import PartnershipRequest
    req = PartnershipRequest.query.get_or_404(req_id)
    req.status = 'rejected'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Request rejected.'})


# ─────────────────────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
@handle_exceptions
def users():
    page   = int(request.args.get('page', 1))
    search = request.args.get('search', '').strip()

    user_role = Role.query.filter_by(role_name='user').first()
    q = AppUser.query
    if user_role: q = q.filter_by(role_id=user_role.role_id)
    if search:
        q = q.filter(db.or_(AppUser.name.ilike(f'%{search}%'), AppUser.email.ilike(f'%{search}%')))
    q = q.order_by(AppUser.name)
    items, total, total_pages = paginate(q, page, PER_PAGE)

    return render_template('admin/users.html',
        active_page='users', users=items,
        total=total, page=page, total_pages=total_pages, per_page=PER_PAGE, search=search)


@admin_bp.route('/users/toggle/<int:user_id>', methods=['POST'])
@admin_required
@handle_exceptions
def toggle_user(user_id):
    u = db.session.get(AppUser, user_id)
    if not u: return jsonify({'success': False}), 404
    u.is_active = not u.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': u.is_active})


# ─────────────────────────────────────────────────────────────
# BOOKINGS
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/bookings')
@admin_required
@handle_exceptions
def bookings():
    page   = int(request.args.get('page', 1))
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    q = db.session.query(Booking, Show, Movie, Theater, User)\
        .join(Show, Booking.show_id == Show.show_id)\
        .join(Movie, Show.movie_id == Movie.movie_id)\
        .join(Theater, Show.theater_id == Theater.theater_id)\
        .join(User, Booking.user_id == User.user_id)

    if status: q = q.filter(Booking.payment_status == status)
    if search: q = q.filter(db.or_(
        Movie.title.ilike(f'%{search}%'),
        Theater.name.ilike(f'%{search}%'),
        User.name.ilike(f'%{search}%')
    ))
    q = q.order_by(Booking.booking_date.desc())

    total = q.count()
    rows  = q.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    bookings_data = [{'b': b, 's': s, 'm': m, 't': t, 'u': u} for b, s, m, t, u in rows]

    return render_template('admin/bookings.html',
        active_page='bookings', bookings=bookings_data,
        total=total, page=page, total_pages=total_pages, per_page=PER_PAGE,
        status=status, search=search)


# ─────────────────────────────────────────────────────────────
# CONTACT MESSAGES
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/contact-messages')
@admin_required
@handle_exceptions
def contact_messages():
    from models import ContactMessage
    page   = int(request.args.get('page', 1))
    status = request.args.get('status', '').strip()
    mtype  = request.args.get('type', '').strip()

    q = ContactMessage.query
    if status: q = q.filter(ContactMessage.status == status)
    if mtype:  q = q.filter(ContactMessage.message_type == mtype)
    q = q.order_by(ContactMessage.created_at.desc())
    items, total, total_pages = paginate(q, page, PER_PAGE)
    unread = ContactMessage.query.filter_by(status='unread').count()

    return render_template('admin/contact_messages.html',
        active_page='contact_messages', messages=items,
        total=total, page=page, total_pages=total_pages,
        unread_count=unread, status_filter=status, type_filter=mtype)


@admin_bp.route('/contact-messages/<int:msg_id>/resolve', methods=['POST'])
@admin_required
@handle_exceptions
def resolve_contact_message(msg_id):
    from models import ContactMessage
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.status = 'resolved'
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/contact-messages/<int:msg_id>/read', methods=['POST'])
@admin_required
@handle_exceptions
def mark_message_read(msg_id):
    from models import ContactMessage
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.status = 'read'
    db.session.commit()
    return jsonify({'success': True})



# ─────────────────────────────────────────────────────────────
# LOCATIONS  (add state / city / location via AJAX)
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/locations/add', methods=['POST'])
@admin_required
@handle_exceptions
def add_location():
    """
    Accepts JSON: { type: 'state'|'city'|'location', name, state, city }
    Saves by creating a placeholder theater entry or using existing theater
    rows as the source of truth for /api/locations.

    Since states/cities live IN the theaters table, we save a sentinel
    Theater row that acts as a location anchor (no name clash with real
    theaters because we check first).
    """
    from flask import request as req
    data  = req.get_json() or {}
    ltype = data.get('type', '').strip()
    name  = data.get('name', '').strip()
    state = data.get('state', '').strip()
    city  = data.get('city', '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Name is required.'})

    if ltype == 'state':
        # Check duplicate
        existing = Theater.query.filter(
            db.func.lower(Theater.state) == name.lower()
        ).first()
        if existing:
            return jsonify({'success': False, 'message': f'State "{name}" already exists.'})
        # Create a sentinel theater row to anchor the state
        sentinel = Theater(
            theater_id='LOC_' + str(uuid.uuid4())[:8].upper(),
            name=f'[Location Anchor – {name}]',
            state=name, city='(placeholder)', location=None
        )
        db.session.add(sentinel)
        db.session.commit()
        return jsonify({'success': True, 'message': f'State "{name}" added.'})

    elif ltype == 'city':
        if not state:
            return jsonify({'success': False, 'message': 'State is required for adding a city.'})
        existing = Theater.query.filter(
            db.func.lower(Theater.state) == state.lower(),
            db.func.lower(Theater.city)  == name.lower()
        ).first()
        if existing:
            return jsonify({'success': False, 'message': f'City "{name}" already exists in {state}.'})
        sentinel = Theater(
            theater_id='LOC_' + str(uuid.uuid4())[:8].upper(),
            name=f'[Location Anchor – {state} / {name}]',
            state=state, city=name, location=None
        )
        db.session.add(sentinel)
        db.session.commit()
        return jsonify({'success': True, 'message': f'City "{name}" added to {state}.'})

    elif ltype == 'location':
        if not state:
            return jsonify({'success': False, 'message': 'State is required.'})
        if not city:
            return jsonify({'success': False, 'message': 'City is required.'})
        # Location/area is just a string field — no separate table needed.
        # We return success; the caller will fill the text input directly.
        # Optionally persist it by tagging an existing sentinel:
        sentinel = Theater.query.filter(
            Theater.state == state, Theater.city == city,
            Theater.name.like('[Location Anchor%')
        ).first()
        if sentinel:
            sentinel.location = name
        else:
            sentinel = Theater(
                theater_id='LOC_' + str(uuid.uuid4())[:8].upper(),
                name=f'[Location Anchor – {state} / {city}]',
                state=state, city=city, location=name
            )
            db.session.add(sentinel)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Location "{name}" saved.'})

    return jsonify({'success': False, 'message': 'Invalid type.'})

# ─────────────────────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────────────────────
@admin_bp.route('/reports')
@admin_required
@handle_exceptions
def reports():
    paid_statuses = ['completed']

    movie_revenue = db.session.query(
        Movie.title,
        func.count(Booking.booking_id).label('total_bookings'),
        func.sum(Booking.total_amount).label('total_revenue')
    ).join(Show, Show.movie_id == Movie.movie_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Movie.title)\
     .order_by(func.sum(Booking.total_amount).desc()).limit(10).all()

    city_revenue = db.session.query(
        Theater.city,
        Theater.state,
        func.count(Booking.booking_id).label('total_bookings'),
        func.sum(Booking.total_amount).label('total_revenue')
    ).join(Show, Show.theater_id == Theater.theater_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Theater.city, Theater.state)\
     .order_by(func.sum(Booking.total_amount).desc()).limit(10).all()

    # Summary totals
    total_revenue  = db.session.query(func.sum(Booking.total_amount))\
        .filter(Booking.payment_status.in_(paid_statuses)).scalar() or 0
    total_bookings = Booking.query.filter(Booking.payment_status.in_(paid_statuses)).count()

    return render_template('admin/reports.html',
        active_page='reports',
        movie_revenue=movie_revenue,
        city_revenue=city_revenue,
        total_revenue=total_revenue,
        total_bookings=total_bookings)



@admin_bp.route('/movies/assign-theaters', methods=['POST'])
@admin_required
@handle_exceptions
def assign_movie_theaters():
    movie_id    = request.form.get('movie_id')
    theater_ids = request.form.getlist('theater_ids')
    
    if not movie_id:
        flash('No movie selected.', 'danger')
        return redirect(url_for('admin_bp.movies'))

    movie = db.session.get(Movie, movie_id)
    if not movie:
        flash('Movie not found.', 'danger')
        return redirect(url_for('admin_bp.movies'))

# 🔥 CREATE SHOWS HERE
    for tid in theater_ids:
        screens = Screen.query.filter_by(theater_id=tid).all()

        for screen in screens:
            show = Show(
                show_id='SH_' + str(uuid.uuid4())[:8].upper(),
                movie_id=movie_id,
                theater_id=tid,
                screen_id=screen.screen_id,
                show_date=date.today(),
                start_time=time(9,0),
                price=150,
                available_seats=screen.total_seats,
                status='active'
            )
            db.session.add(show)

    db.session.commit()

    flash(f'Movie "{movie.title}" assigned to {len(theater_ids)} theater(s).', 'success')
    return redirect(url_for('admin_bp.movies'))


@admin_bp.route('/movies/add', methods=['POST'])
@admin_required
@handle_exceptions
def add_movie():
    title    = request.form.get('title', '').strip()
    genre    = request.form.get('genre', '').strip()
    language = request.form.get('language', '').strip()

    if not title:
        flash('Movie title is required.', 'danger')
        return redirect(url_for('admin_bp.movies'))

    # Duplicate check: same title + language + genre
    existing = Movie.query.filter(
        db.func.lower(Movie.title) == title.lower(),
        db.func.lower(db.func.coalesce(Movie.language, '')) == language.lower(),
        db.func.lower(db.func.coalesce(Movie.genre, '')) == genre.lower()
    ).first()
    if existing:
        flash(f'This movie is already there: "{title}" ({language}, {genre}).', 'warning')
        return redirect(url_for('admin_bp.movies'))

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

    # handle file upload (same style as edit)
    file = request.files.get('poster_file')
    if file and file.filename:
        saved = save_file(file)
        if saved:
            movie.poster_url = f'/static/uploads/{saved}'

    db.session.add(movie)
    db.session.commit()

    flash(f'Movie "{movie.title}" added successfully.', 'success')
    return redirect(url_for('admin_bp.movies'))


@admin_bp.route('/analytics/api/top-theaters')
@admin_required
def api_top_theaters():
    paid_statuses = ['completed']
    rows = db.session.query(
        Theater.name.label('theater'),
        func.sum(Booking.total_amount).label('revenue')
    ).join(Show, Show.theater_id == Theater.theater_id)\
     .join(Booking, Booking.show_id == Show.show_id)\
     .filter(Booking.payment_status.in_(paid_statuses))\
     .group_by(Theater.name)\
     .order_by(func.sum(Booking.total_amount).desc())\
     .limit(10).all()
    return jsonify([{'theater': r.theater, 'revenue': float(r.revenue or 0)} for r in rows])