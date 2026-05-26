import uuid
import qrcode, io, base64
from datetime import datetime, date as _date, timedelta

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from sqlalchemy import func, distinct, text

from extensions import db
from models import (Movie, Show, Theater, Screen, Seat,
                    Booking, Payment, Review, User, AppUser)
from utils.decorators import login_required, handle_exceptions

user_bp = Blueprint('user_bp', __name__)

POOL_SIZE            = 100
USER_MOVIES_PER_PAGE = 24


# --------------------------------------------------
# HELPER — current dataset user
# --------------------------------------------------
def get_dataset_user():
    dataset_user_id = session.get('dataset_user_id')
    if dataset_user_id:
        return db.session.get(User, dataset_user_id)
    return None


# --------------------------------------------------
# HELPER — format movie row for display
# --------------------------------------------------
def format_movie_display(movie):
    movie = dict(movie._mapping)

    # Genres — deduplicated, show up to 2
    genres = list(dict.fromkeys(
        g.strip()
        for g in (movie.get('genres') or '').split(', ')
        if g.strip()
    ))
    movie['genres_display'] = ' / '.join(genres[:2])

    # Languages — count + list
    langs = list(dict.fromkeys(
        l.strip()
        for l in (movie.get('languages') or '').split(', ')
        if l.strip()
    ))
    movie['lang_count']        = len(langs)
    movie['languages_list']    = langs
    movie['languages_display'] = ' • '.join(langs[:2])
    movie['languages_extra']   = max(0, len(langs) - 2)

    # Ensure release_date is a real date object (not a string)
    rd = movie.get('release_date')
    if isinstance(rd, str):
        try:
            from datetime import date
            movie['release_date'] = date.fromisoformat(rd)
        except Exception:
            movie['release_date'] = None

    return movie


# --------------------------------------------------
# API — state → city
# --------------------------------------------------
@user_bp.route('/api/locations')
@handle_exceptions
def api_locations():
    # Step 1: get ALL distinct states (including state-only sentinels
    # which have city='(placeholder)' — those need to appear in the
    # state dropdown even before any city is added to them).
    state_rows = (
        db.session.query(Theater.state)
        .filter(Theater.state != None)
        .distinct()
        .order_by(Theater.state)
        .all()
    )
    result = {}
    for (state,) in state_rows:
        state = (state or '').strip()
        if state:
            result.setdefault(state, [])

    # Step 2: get all real state+city pairs (exclude placeholder cities).
    city_rows = (
        db.session.query(Theater.state, Theater.city)
        .filter(
            Theater.state != None,
            Theater.city  != None,
            Theater.city  != '(placeholder)'
        )
        .distinct()
        .order_by(Theater.state, Theater.city)
        .all()
    )
    for state, city in city_rows:
        state = (state or '').strip()
        city  = (city  or '').strip()
        if state and city:
            result.setdefault(state, [])
            if city not in result[state]:
                result[state].append(city)

    return jsonify(result)


# --------------------------------------------------
# API — areas
# --------------------------------------------------
@user_bp.route('/api/areas')
@handle_exceptions
def api_areas():
    rows = (
        db.session.query(Theater.state, Theater.city, Theater.location)
        .filter(
            Theater.state    != None,
            Theater.city     != None,
            Theater.location != None,
            Theater.city     != '(placeholder)'
        )
        .distinct()
        .order_by(Theater.state, Theater.city, Theater.location)
        .all()
    )
    result = {}
    for state, city, location in rows:
        state    = (state    or '').strip()
        city     = (city     or '').strip()
        location = (location or '').strip()
        if state and city and location:
            key = f"{state}|{city}"
            result.setdefault(key, [])
            if location not in result[key]:
                result[key].append(location)
    return jsonify(result)


# --------------------------------------------------
# SET CITY
# --------------------------------------------------
@user_bp.route('/set-city', methods=['POST'])
@handle_exceptions
def set_city():
    data = request.get_json() or {}
    city = data.get('city', '').strip()
    if city:
        session['city'] = city
        return jsonify({'success': True, 'city': city})
    else:
        # Allow clearing the city selection
        session.pop('city', None)
        return jsonify({'success': True, 'city': ''})


# --------------------------------------------------
# HOME
# --------------------------------------------------
@user_bp.route('/')
@user_bp.route('/home')
@handle_exceptions
def home():
    city            = session.get('city', '').strip()
    today           = _date.today()
    show_city_modal = not bool(city)   # True  → JS will open modal on load

    # ── City-specific data ───────────────────────────────────
    if city:
        # movie_ids that have active shows in this city
        city_movie_ids = (
            db.session.query(Show.movie_id)
            .join(Theater, Theater.theater_id == Show.theater_id)
            .filter(
                Theater.city.ilike(f'%{city}%'),
                Show.status          == 'active',
                Show.available_seats >  0,
                ~Theater.theater_id.like('LOC_%'),
                Theater.city         != '(placeholder)'
            )
            .distinct()
            .all()
        )
        city_ids = [r[0] for r in city_movie_ids]

        # Aggregate ONLY the movie_ids that are active in this city,
        # so genres and languages reflect only what's showing here.
        city_movies_raw = [
            format_movie_display(m)
            for m in db.session.query(
                func.min(Movie.movie_id).label('movie_id'),
                Movie.title,
                func.max(Movie.rating).label('rating'),
                func.max(Movie.poster_url).label('poster_url'),
                func.max(Movie.release_date).label('release_date'),
                func.max(Movie.duration).label('duration'),
               func.string_agg(Movie.genre.distinct(), ', ').label('genres'),
               func.string_agg(Movie.language.distinct(), ', ').label('languages')
            )
            .filter(
                Movie.movie_id.in_(city_ids),   # only city-active variants
                Movie.status       == 'active',
                Movie.release_date <= today
            )
            .group_by(Movie.title)
            .order_by(func.max(Movie.rating).desc())
            .limit(15)
            .all()
        ]

        city_theaters = (
            Theater.query
            .filter(Theater.city.ilike(f'%{city}%'))
            .limit(6)
            .all()
        )
    else:
        city_movies_raw = []
        city_theaters   = []

    # ── NOW SHOWING  (release_date <= today, must have active shows in real theaters) ──
    # Build city-aware subquery: when a city is active, only aggregate
    # movie_ids (i.e. language variants) that actually have shows there.
    _home_shows_q = (
        db.session.query(Show.movie_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(
            Show.status == 'active',
            Show.available_seats > 0,
            ~Theater.theater_id.like('LOC_%'),
            Theater.city != '(placeholder)'
        )
    )
    if city:
        _home_shows_q = _home_shows_q.filter(
            Theater.city.ilike(f'%{city}%')
        )
    movies_with_shows = _home_shows_q.distinct()

    now_showing = [
        format_movie_display(m)
        for m in db.session.query(
            func.min(Movie.movie_id).label('movie_id'),
            Movie.title,
            func.max(Movie.rating).label('rating'),
            func.max(Movie.poster_url).label('poster_url'),
            func.max(Movie.release_date).label('release_date'),
            func.max(Movie.duration).label('duration'),
            func.string_agg(Movie.genre.distinct(), ', ').label('genres'),
            func.string_agg(Movie.language.distinct(), ', ').label('languages')
        )
        .filter(
            Movie.status       == 'active',
            Movie.release_date <= today,
            Movie.movie_id.in_(movies_with_shows)   # only city-active variants
        )
        .group_by(Movie.title)
        .order_by(func.max(Movie.release_date).desc())   # latest first
        .limit(15)
        .all()
    ]

    # ── NEW ADDITIONS  (last 30 days, must have active shows) ──────────────────
    thirty_days_ago = today - timedelta(days=30)

    new_additions = [
        format_movie_display(m)
        for m in db.session.query(
            func.min(Movie.movie_id).label('movie_id'),
            Movie.title,
            func.max(Movie.rating).label('rating'),
            func.max(Movie.poster_url).label('poster_url'),
            func.max(Movie.release_date).label('release_date'),
            func.max(Movie.duration).label('duration'),
            func.string_agg(Movie.genre.distinct(), ', ').label('genres'),
            func.string_agg(Movie.language.distinct(), ', ').label('languages')
        )
        .filter(
            Movie.status       == 'active',
            Movie.release_date >= thirty_days_ago,
            Movie.release_date <= today,
            Movie.movie_id.in_(movies_with_shows)   # only city-active variants
        )
        .group_by(Movie.title)
        .order_by(func.max(Movie.release_date).desc())
        .limit(15)
        .all()
    ]

    # If nothing in last 30 days, widen to 90 days so the section isn't empty
    if not new_additions:
        ninety_days_ago = today - timedelta(days=90)
        new_additions = [
            format_movie_display(m)
            for m in db.session.query(
                func.min(Movie.movie_id).label('movie_id'),
                Movie.title,
                func.max(Movie.rating).label('rating'),
                func.max(Movie.poster_url).label('poster_url'),
                func.max(Movie.release_date).label('release_date'),
                func.max(Movie.duration).label('duration'),
                func.string_agg(Movie.genre.distinct(), ', ').label('genres'),
                func.string_agg(Movie.language.distinct(), ', ').label('languages')
            )
            .filter(
                Movie.status       == 'active',
                Movie.release_date >= ninety_days_ago,
                Movie.release_date <= today,
                Movie.movie_id.in_(movies_with_shows)
            )
            .group_by(Movie.title)
            .order_by(func.max(Movie.release_date).desc())
            .limit(15)
            .all()
        ]

    # ── UPCOMING  (release_date > today) ─────────────────────
    upcoming = [
        format_movie_display(m)
        for m in db.session.query(
            func.min(Movie.movie_id).label('movie_id'),
            Movie.title,
            func.max(Movie.rating).label('rating'),
            func.max(Movie.poster_url).label('poster_url'),
            func.max(Movie.release_date).label('release_date'),
            func.max(Movie.duration).label('duration'),
            func.string_agg(distinct(Movie.genre), ', ').label('genres'),
            func.string_agg(distinct(Movie.language), ', ').label('languages')
        )
        .filter(Movie.release_date > today)
        .group_by(Movie.title)
        .order_by(func.max(Movie.release_date).asc())
        .limit(15)
        .all()
    ]

    stats = {
        'total_movies':
            db.session.query(func.count(distinct(Movie.title)))
            .filter(Movie.status == 'active')
            .scalar(),
        'total_theaters': Theater.query.count(),
    }

    return render_template(
        'user/home.html',
        now_showing     = now_showing,
        new_additions   = new_additions,
        upcoming        = upcoming,
        city_movies     = city_movies_raw,
        city_theaters   = city_theaters,
        city            = city,
        stats           = stats,
        today           = today,
        show_city_modal = show_city_modal,
        active_page     = 'home'
    )


# --------------------------------------------------
# MOVIES PAGE
# --------------------------------------------------
@user_bp.route('/movies')
@handle_exceptions
def movies():
    search        = (request.args.get('q') or '').strip()
    language      = request.args.get('language', '').strip()
    genre         = request.args.get('genre', '').strip()
    status_filter = request.args.get('filter',   '').strip()
    sort          = request.args.get('sort', 'latest').strip()
    page          = max(1, int(request.args.get('page', 1)))
    today         = _date.today()
    city          = session.get('city', '').strip()

    # ------------------------------------------------------------------
    # ONE query — joins Movie → Show → Theater directly so PostgreSQL
    # handles all filtering, grouping, deduplication, and pagination
    # without any Python-side IN list or separate COUNT round-trip.
    #
    # The active-shows correlated join replaces both the old
    # "_active_shows_q → matching_titles → title.IN(...)" round-trips.
    # COUNT(*) OVER() on the outer wrapper gives the total without an
    # extra query (window functions run before LIMIT is applied).
    # ------------------------------------------------------------------

    # Base join: Movie → Show → Theater (only real, active shows)
    base_filters = [
        Show.status         == 'active',
        Show.available_seats > 0,
        ~Theater.theater_id.like('LOC_%'),
        Theater.city        != '(placeholder)',
    ]
    if city:
        base_filters.append(Theater.city.ilike(f'%{city}%'))

    # Movie-level filters depending on status_filter tab
    if status_filter == 'upcoming':
        base_filters.append(Movie.release_date > today)
    elif status_filter == 'all':
        pass  # no extra movie filter — just needs active shows
    else:
        # default: now-showing
        base_filters.append(Movie.status       == 'active')
        base_filters.append(Movie.release_date <= today)

    if search:
        base_filters.append(Movie.title.ilike(f'%{search}%'))
    if language:
        base_filters.append(Movie.language.ilike(f'%{language}%'))
    if genre:
        base_filters.append(Movie.genre.ilike(f'%{genre}%'))

    # Grouped query — one row per distinct title, aggregating variants
    group_query = (
        db.session.query(
            func.min(Movie.movie_id).label('movie_id'),
            Movie.title,
            func.max(Movie.rating).label('rating'),
            func.max(Movie.poster_url).label('poster_url'),
            func.max(Movie.release_date).label('release_date'),
            func.max(Movie.duration).label('duration'),
            func.max(Movie.status).label('status'),
            func.string_agg(distinct(Movie.genre),    ', ').label('genres'),
            func.string_agg(distinct(Movie.language), ', ').label('languages'),
        )
        .join(Show,    Show.movie_id    == Movie.movie_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(*base_filters)
        .group_by(Movie.title)
    )

    # Sort
    if sort == 'rating':
        group_query = group_query.order_by(func.max(Movie.rating).desc())
    elif sort == 'title':
        group_query = group_query.order_by(Movie.title.asc())
    else:
        group_query = group_query.order_by(func.max(Movie.release_date).desc())

    # ------------------------------------------------------------------
    # Pagination using a COUNT(*) window function so we avoid the extra
    # group_query.count() round-trip.
    #
    # We wrap the grouped query as a subquery, then select each column
    # plus COUNT(*) OVER () from it — PostgreSQL computes the total over
    # all grouped rows before LIMIT is applied.
    # ------------------------------------------------------------------
    sub = group_query.subquery('movies_grouped')

    windowed = (
        db.session.query(
            sub,
            func.count('*').over().label('total_count'),
        )
        .limit(USER_MOVIES_PER_PAGE)
        .offset((page - 1) * USER_MOVIES_PER_PAGE)
        .all()
    )

    if windowed:
        total       = windowed[0].total_count
        movies_list = [format_movie_display(row) for row in windowed]
    else:
        total, movies_list = 0, []

    total_pages = max(1, (total + USER_MOVIES_PER_PAGE - 1) // USER_MOVIES_PER_PAGE)
    page        = min(page, total_pages)

    return render_template(
        'user/movies.html',
        movies        = movies_list,
        total         = total,
        page          = page,
        total_pages   = total_pages,
        per_page      = USER_MOVIES_PER_PAGE,
        search        = search,
        language      = language,
        status_filter = status_filter,
        sort          = sort,
        languages     = _get_all_languages(),
        genres        = _get_all_genres(),
        genre         = genre,
        active_page   = 'movies',
        city          = city,
    )


def _get_all_languages():
    # Only languages for movies that have active theater shows
    rows = (
        db.session.query(distinct(Movie.language))
        .join(Show, Show.movie_id == Movie.movie_id)
        .filter(
            Movie.language != None,
            Movie.status == 'active',
            Show.status == 'active'
        )
        .all()
    )
    langs = set()
    for (l,) in rows:
        for part in (l or '').split(','):
            part = part.strip()
            if part:
                langs.add(part)
    return sorted(langs)


def _get_all_genres():
    # Only genres for movies that have active theater shows
    rows = (
        db.session.query(distinct(Movie.genre))
        .join(Show, Show.movie_id == Movie.movie_id)
        .filter(
            Movie.genre != None,
            Movie.status == 'active',
            Show.status == 'active'
        )
        .all()
    )
    genres = set()
    for (g,) in rows:
        for part in (g or '').split(','):
            part = part.strip()
            if part:
                genres.add(part)
    return sorted(genres)


# --------------------------------------------------
# MOVIES API (for infinite scroll)
# --------------------------------------------------
@user_bp.route('/api/movies')
@handle_exceptions
def api_movies():
    search        = (request.args.get('q') or '').strip()
    language      = request.args.get('language', '').strip()
    genre         = request.args.get('genre', '').strip()
    status_filter = request.args.get('filter',   '').strip()
    sort          = request.args.get('sort', 'latest').strip()
    page          = max(1, int(request.args.get('page', 1)))
    today         = _date.today()
    city          = session.get('city', '').strip()

    _active_shows_q = (
        db.session.query(Show.movie_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(
            Show.status == 'active',
            Show.available_seats > 0,
            ~Theater.theater_id.like('LOC_%'),
            Theater.city != '(placeholder)'
        )
    )
    if city:
        _active_shows_q = _active_shows_q.filter(
            Theater.city.ilike(f'%{city}%')
        )
    movies_with_active_shows = _active_shows_q.distinct()

    base = Movie.query
    if status_filter == 'upcoming':
        base = base.filter(Movie.release_date > today)
    elif status_filter == 'all':
        base = base.filter(Movie.movie_id.in_(movies_with_active_shows))
    else:
        base = base.filter(
            Movie.status       == 'active',
            Movie.release_date <= today,
            Movie.movie_id.in_(movies_with_active_shows)
        )

    if search:
        base = base.filter(Movie.title.ilike(f'%{search}%'))
    if language:
        base = base.filter(Movie.language.ilike(f'%{language}%'))
    if genre:
        base = base.filter(Movie.genre.ilike(f'%{genre}%'))

    matching_titles = [r[0] for r in base.with_entities(Movie.title).distinct().all()]

    if not matching_titles:
        return jsonify({'movies': [], 'total': 0, 'page': page, 'has_more': False})

    # Aggregate genres/languages only from movie_ids that have active
    # shows in the city (reuses movies_with_active_shows which is already
    # city-filtered above).
    group_query = db.session.query(
        func.min(Movie.movie_id).label('movie_id'),
        Movie.title,
        func.max(Movie.rating).label('rating'),
        func.max(Movie.poster_url).label('poster_url'),
        func.max(Movie.release_date).label('release_date'),
        func.max(Movie.duration).label('duration'),
        func.string_agg(distinct(Movie.genre), ', ').label('genres'),
        func.string_agg(distinct(Movie.language), ', ').label('languages'),
    ).filter(
        Movie.title.in_(matching_titles),
        Movie.movie_id.in_(movies_with_active_shows)
    ).group_by(Movie.title)

    if sort == 'rating':
        group_query = group_query.order_by(func.max(Movie.rating).desc())
    elif sort == 'title':
        group_query = group_query.order_by(Movie.title.asc())
    else:
        group_query = group_query.order_by(func.max(Movie.release_date).desc())

    total    = group_query.count()
    per_page = USER_MOVIES_PER_PAGE
    has_more = (page * per_page) < total

    movies_list = [
        format_movie_display(m)
        for m in group_query.offset((page - 1) * per_page).limit(per_page).all()
    ]

    result = []
    for m in movies_list:
        rd = m.get('release_date')
        result.append({
            'movie_id':   m['movie_id'],
            'title':      m['title'],
            'rating':     m.get('rating'),
            'poster_url': m.get('poster_url') or '',
            'duration':   m.get('duration'),
            'genres_display':  m.get('genres_display', ''),
            'languages_list':  m.get('languages_list', []),
            'lang_count':      m.get('lang_count', 0),
            'languages_extra': m.get('languages_extra', 0),
        })

    return jsonify({'movies': result, 'total': total, 'page': page, 'has_more': has_more})


# --------------------------------------------------
# MOVIE DETAIL
# --------------------------------------------------
@user_bp.route('/movie/<movie_id>')
@handle_exceptions
def movie_detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    city  = request.args.get('city', session.get('city', '')).strip()

    # Optional language filter — UI hint only, NOT a gate to theaters
    selected_language = request.args.get('language', '').strip()

    # ── Date selector — 7-day pre-booking window ─────────────────────────
    today_date = _date.today()
    date_range = [today_date + timedelta(days=i) for i in range(7)]  # Today + 6 more days
    selected_date_str = request.args.get('date', today_date.isoformat())
    try:
        selected_date = _date.fromisoformat(selected_date_str)
        if selected_date not in date_range:
            selected_date = today_date
    except ValueError:
        selected_date = today_date

    # All active variants of this title (all languages)
    all_variants = Movie.query.filter(
        Movie.title  == movie.title,
        Movie.status == 'active'
    ).all()

    variant_ids = [v.movie_id for v in all_variants]

    # lang → movie_id map (for booking links)
    lang_to_movie = {}
    for v in all_variants:
        if v.language and v.language not in lang_to_movie:
            lang_to_movie[v.language] = v.movie_id

    # Representative movie object for the banner
    selected_movie = movie
    if selected_language:
        for v in all_variants:
            if v.language == selected_language:
                selected_movie = v
                break

    # --- Load ALL shows across ALL language variants, filtered by city ---
    # Exclude LOC_/placeholder theaters so only real venues appear.
    shows_query = (
        db.session.query(Show, Theater, Movie)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .join(Movie,   Movie.movie_id     == Show.movie_id)
        .filter(
            Show.movie_id.in_(variant_ids),
            Show.status == 'active',
            Show.available_seats > 0,
            ~Theater.theater_id.like('LOC_%'),
            Theater.city != '(placeholder)'
        )
    )
    if city:
        shows_query = shows_query.filter(
            Theater.city.ilike(f'%{city}%')
        )

    # Group: theater → language → [shows]
    theater_map = {}
    for show, theater, movie_variant in shows_query.order_by(
        Theater.name, Movie.language, Show.show_date, Show.start_time
    ).all():
        tid  = theater.theater_id
        lang = movie_variant.language or 'Unknown'
        if tid not in theater_map:
            theater_map[tid] = {'theater': theater, 'lang_shows': {}}
        theater_map[tid]['lang_shows'].setdefault(lang, []).append(show)

    theaters = []
    for tid, data in theater_map.items():
        t = data['theater']
        t.lang_shows    = data['lang_shows']          # dict: lang → [show]
        t.all_languages = sorted(data['lang_shows'].keys())
        theaters.append(t)

    # Derive available_languages DIRECTLY from theater_map — this guarantees
    # every language tab shown has at least one real theater+show visible
    # on this page (respects city filter, LOC_ exclusion, available seats, etc.)
    available_languages = sorted(set(
        lang
        for data in theater_map.values()
        for lang in data['lang_shows'].keys()
        if lang != 'Unknown'
    ))

    # Reviews across all variants
    reviews = (
        db.session.query(Review, User)
        .join(User, Review.user_id == User.user_id)
        .filter(Review.movie_id.in_(variant_ids))
        .order_by(Review.review_date.desc())
        .limit(20)
        .all()
    )

    avg_rating = (
        db.session.query(func.avg(Review.rating))
        .filter(Review.movie_id.in_(variant_ids))
        .scalar()
    )

    city_rows = (
        db.session.query(Theater.city)
        .join(Show, Show.theater_id == Theater.theater_id)
        .filter(
            Show.movie_id.in_(variant_ids),
            Show.status == 'active'
        )
        .distinct()
        .all()
    )
    city_list = sorted(set(c[0] for c in city_rows if c[0]))

    # ── Fixed 4 show time slots (displayed regardless of DB shows) ─────────
    from datetime import time as _time
    FIXED_SHOW_SLOTS = [
        {'label': 'Morning',   'time': _time(10, 0),  'display': '10:00 AM'},
        {'label': 'Afternoon', 'time': _time(13, 30), 'display': '01:30 PM'},
        {'label': 'Evening',   'time': _time(17, 0),  'display': '05:00 PM'},
        {'label': 'Night',     'time': _time(21, 0),  'display': '09:00 PM'},
    ]

    # Current IST time for disabling past slots (Render runs UTC; IST = UTC+5:30)
    from datetime import timezone
    now_dt   = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    now_time = now_dt.time()

    # Build virtual show IDs keyed by (movie_id, date, slot_time) so seats
    # page receives a stable, unique ID per show slot per date
    def _virtual_show_id(movie_id, show_date, slot_time):
        key = f"VS_{movie_id}_{show_date.isoformat()}_{slot_time.strftime('%H%M')}"
        return key

    # Pre-compute virtual show IDs for today + tomorrow x 4 slots
    virtual_shows = {}  # (date_iso, slot_display) -> virtual_show_id
    for d in date_range:
        for slot in FIXED_SHOW_SLOTS:
            vid = _virtual_show_id(movie.movie_id, d, slot['time'])
            virtual_shows[(d.isoformat(), slot['display'])] = vid

    return render_template(
        'user/movie_detail.html',
        movie               = selected_movie,
        all_variants        = all_variants,
        available_languages = available_languages,
        selected_language   = selected_language,
        lang_to_movie       = lang_to_movie,
        theaters            = theaters,
        reviews             = reviews,
        avg_rating          = round(avg_rating, 1) if avg_rating else None,
        city_list           = city_list,
        selected_city       = city,
        today               = today_date.isoformat(),
        date_range          = date_range,
        selected_date       = selected_date,
        fixed_show_slots    = FIXED_SHOW_SLOTS,
        virtual_shows       = virtual_shows,
        now_time            = now_time,
        now_date            = today_date,
    )

# --------------------------------------------------
# SEAT SELECTION
# --------------------------------------------------
@user_bp.route('/select-seats/<show_id>')
@login_required
@handle_exceptions
def select_seats(show_id):
    # ── Handle virtual show IDs (VS_<movie_id>_<date>_<HHMM>) ────────────
    # Virtual shows are generated on the movie_detail page for the 4 fixed
    # time slots.  They don't exist in the DB, so we fabricate a Show-like
    # object from the encoded parts and look up a real show (or the first
    # available one) to attach theater/screen info.
    virtual_show_obj = None
    if show_id.startswith('VS_'):
        parts = show_id.split('_')
        # VS_ <movie_id> _ <YYYY-MM-DD> _ <HHMM>
        # movie_id itself may contain underscores, so reconstruct carefully
        # format: VS_{movie_id}_{date}_{hhmm}  — date is always 10 chars, hhmm always 4
        try:
            hhmm      = parts[-1]           # last segment: HHMM
            date_str  = parts[-2]           # second-last: YYYY-MM-DD
            movie_id  = '_'.join(parts[1:-2])  # everything between VS_ and date
            from datetime import time as _time, date as _date2
            slot_hour  = int(hhmm[:2])
            slot_min   = int(hhmm[2:])
            slot_time  = _time(slot_hour, slot_min)
            show_date  = _date2.fromisoformat(date_str)
        except Exception:
            flash('Invalid show link.', 'danger')
            return redirect(url_for('user_bp.movies'))

        movie = Movie.query.get_or_404(movie_id)

        # ── Disable past slots ────────────────────────────────────────────
        from datetime import timezone
        now_dt    = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        today_d   = now_dt.date()
        now_t     = now_dt.time()
        if show_date < today_d or (show_date == today_d and slot_time <= now_t):
            flash('This show time has already passed.', 'warning')
            return redirect(url_for('user_bp.movie_detail', movie_id=movie_id))

        # Find any real show for this movie to borrow theater/screen/price
        real_show = (Show.query
                     .filter_by(movie_id=movie_id, status='active')
                     .first())

        # Build a lightweight virtual Show object
        class VirtualShow:
            pass
        vs                = VirtualShow()
        vs.show_id        = show_id
        vs.movie_id       = movie_id
        vs.show_date      = show_date
        vs.start_time     = slot_time
        vs.status         = 'active'
        vs.price          = real_show.price if real_show else 150.0
        vs.available_seats= real_show.available_seats if real_show else 60
        vs.screen_id      = real_show.screen_id if real_show else None
        vs.theater_id     = real_show.theater_id if real_show else None

        show              = vs
        theater           = db.session.get(Theater, show.theater_id) if show.theater_id else None
        virtual_show_obj  = vs
    else:
        show    = Show.query.get_or_404(show_id)
        theater = db.session.get(Theater, show.theater_id)
        movie   = db.session.get(Movie,   show.movie_id)

        # ── Disable past real shows ────────────────────────────────────────
        from datetime import timezone
        now_dt  = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        today_d = now_dt.date()
        now_t   = now_dt.time()
        if show.show_date and (
            show.show_date < today_d or
            (show.show_date == today_d and show.start_time and show.start_time <= now_t)
        ):
            flash('This show time has already passed.', 'warning')
            return redirect(url_for('user_bp.movie_detail', movie_id=show.movie_id))

    if not virtual_show_obj and show.status != 'active':
        flash('This show is no longer available.', 'danger')
        return redirect(url_for('user_bp.movie_detail', movie_id=show.movie_id))

    seats = (Seat.query
             .filter_by(screen_id=show.screen_id)
             .order_by(Seat.seat_number)
             .all())

    # FIX Bug #2: use Booking.seat_numbers as the authoritative source of booked seats.
    # Seat.show_id is only written after booking confirms, so querying it here would
    # show already-booked seats as available.  Both real-seat and synth-seat paths
    # now use the same correct source.
    def _collect_booked(show_id):
        booked = set()
        rows = (Booking.query
                .filter_by(show_id=show_id)
                .filter(Booking.payment_status != 'cancelled')
                .with_entities(Booking.seat_numbers)
                .all())
        for (seat_str,) in rows:
            for sn in (seat_str or '').split(','):
                sn = sn.strip()
                if sn:
                    booked.add(sn)
        return booked

    booked_seat_numbers = set()
    if seats:
        booked_seat_numbers = _collect_booked(show_id)

    available_count = len([s for s in seats
                           if s.seat_number not in booked_seat_numbers])

    screen = db.session.get(Screen, show.screen_id)
    screen_total = (screen.total_seats if screen else 0) or 0

    use_synth = (not seats) or (len(seats) < screen_total)

    if use_synth:
        total = screen_total or 60
        total = max(total, 1)

        # Synth path also uses Booking table (correct)
        booked_seat_numbers = _collect_booked(show_id)

        SEATS_PER_ROW = 12
        rows      = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        row_count = -(-total // SEATS_PER_ROW)

        vip_rows     = max(1, round(row_count * 0.15))
        premium_rows = max(1, round(row_count * 0.25))

        synth    = []
        seat_num = 0

        for ri in range(min(row_count, len(rows))):
            row_label = rows[ri]
            if ri < vip_rows:
                seat_type = 'VIP'
            elif ri < vip_rows + premium_rows:
                seat_type = 'Premium'
            else:
                seat_type = 'Regular'

            for col in range(1, SEATS_PER_ROW + 1):
                if seat_num >= total:
                    break
                class SynthSeat: pass
                s             = SynthSeat()
                s.seat_id     = f'synth-{row_label}{col}'
                s.seat_number = f'{row_label}{col}'
                s.seat_type   = seat_type
                s.charger     = False
                s.status      = 'Booked' if f'{row_label}{col}' in booked_seat_numbers else 'Available'
                s._is_booked  = (s.status == 'Booked')
                synth.append(s)
                seat_num += 1

        vip_seats     = [s for s in synth if s.seat_type == 'VIP']
        premium_seats = [s for s in synth if s.seat_type == 'Premium']
        regular_seats = [s for s in synth if s.seat_type == 'Regular']
        other_seats   = []
        available_count = len([s for s in synth if s.status == 'Available'])
        seats           = synth
    else:
        vip_seats     = [s for s in seats if s.seat_type and s.seat_type.lower() == 'vip']
        premium_seats = [s for s in seats if s.seat_type and s.seat_type.lower() == 'premium']
        regular_seats = [s for s in seats if s.seat_type and s.seat_type.lower() == 'regular']
        other_seats   = [s for s in seats if not s.seat_type or
                         s.seat_type.lower() not in ('vip', 'premium', 'regular')]

    # ── Per-seat-type pricing ──────────────────────────────────────────────
    # The DB stores a single base price on the Show.  We derive VIP/Premium/
    # Regular prices from that using standard multipliers so each tier has a
    # different price without requiring a schema change.
    #   Regular = base price  (1.0×)
    #   Premium = 1.5× base
    #   VIP     = 2.0× base
    base_price    = float(show.price or 0)
    seat_prices   = {
        'regular' : round(base_price,        2),
        'premium' : round(base_price * 1.5,  2),
        'vip'     : round(base_price * 2.0,  2),
    }

    # For real seats, also mark .status using the Booking-based booked set
    # so the template can use a single reliable signal (seat.status).
    if not use_synth:
        for s in seats:
            if s.seat_number in booked_seat_numbers:
                s._is_booked = True
            else:
                s._is_booked = False

    return render_template(
        'user/seat_selection.html',
        show=show, theater=theater, movie=movie,
        seats=seats, vip_seats=vip_seats,
        premium_seats=premium_seats, regular_seats=regular_seats,
        other_seats=other_seats,
        booked_seat_numbers=booked_seat_numbers,
        available_count=available_count,
        seat_prices=seat_prices,
        use_synth=use_synth,
        is_virtual_show=(virtual_show_obj is not None),
    )

"""
Replace the existing my_bookings() function with this one.

CHANGE: Fetches the Payment record for every booking so the template
can display payment_method, amount paid (incl. fees), and payment date.
"""

@user_bp.route('/my-bookings')
@login_required
@handle_exceptions
def my_bookings():
    dataset_user = get_dataset_user()
    if not dataset_user:
        flash('User profile not found.', 'danger')
        return redirect(url_for('auth_bp.login'))

    raw = (
        db.session.query(Booking, Show, Movie, Theater)
        .join(Show,    Booking.show_id    == Show.show_id)
        .join(Movie,   Show.movie_id      == Movie.movie_id)
        .join(Theater, Theater.theater_id == Show.theater_id)
        .filter(Booking.user_id == dataset_user.user_id)
        .order_by(Booking.booking_date.desc())
        .all()
    )

    # Bulk-fetch all Payment records for this user's bookings in ONE query
    booking_ids  = [b.booking_id for b, *_ in raw]
    payment_map  = {}
    if booking_ids:
        for pmt in Payment.query.filter(Payment.booking_id.in_(booking_ids)).all():
            payment_map[pmt.booking_id] = pmt

    booking_list = []
    for b, s, m, t in raw:
        b._show    = s
        b._movie   = m
        b._theater = t
        b._payment = payment_map.get(b.booking_id)   # ← NEW: attach Payment
        booking_list.append(b)

    return render_template(
        'user/my_bookings.html',
        bookings    = booking_list,
        user        = dataset_user,
        active_page = 'bookings',
        now_str     = datetime.now().strftime('%Y-%m-%dT%H:%M'),
    )

# --------------------------------------------------
# SUBMIT REVIEW
# --------------------------------------------------
@user_bp.route('/submit-review', methods=['POST'])
@login_required
@handle_exceptions
def submit_review():
    dataset_user = get_dataset_user()
    if not dataset_user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    movie_id = request.form.get('movie_id')
    rating   = request.form.get('rating')
    comment  = request.form.get('comment', '').strip()

    if not movie_id or not rating:
        return jsonify({'success': False, 'message': 'Rating is required'}), 400

    existing = Review.query.filter_by(user_id  = dataset_user.user_id,
                                      movie_id = movie_id).first()
    if existing:
        existing.rating      = float(rating)
        existing.comment     = comment
        existing.review_date = datetime.now()
    else:
        db.session.add(Review(
            review_id   = 'RV_' + str(uuid.uuid4())[:8].upper(),
            user_id     = dataset_user.user_id,
            movie_id    = movie_id,
            rating      = float(rating),
            comment     = comment,
            review_date = datetime.now()
        ))

    db.session.commit()
    return jsonify({'success': True, 'message': 'Review submitted!'})


# --------------------------------------------------
# PROFILE
# --------------------------------------------------
@user_bp.route('/profile')
@login_required
@handle_exceptions
def profile():
    dataset_user = get_dataset_user()
    app_user     = db.session.get(AppUser, session.get('user_id'))

    total_bookings = 0
    total_spent    = 0
    if dataset_user:
        total_bookings = Booking.query.filter(
            Booking.user_id        == dataset_user.user_id,
            func.lower(Booking.payment_status) == 'completed'
        ).count()
        total_spent = (
            db.session.query(func.sum(Booking.total_amount))
            .filter(Booking.user_id        == dataset_user.user_id,
                    func.lower(Booking.payment_status) == 'completed')
            .scalar() or 0
        )

    return render_template(
        'user/profile.html',
        user           = dataset_user,
        app_user       = app_user,
        total_bookings = total_bookings,
        total_spent    = total_spent,
        active_page    = 'profile'
    )


# ─────────────────────────────────────────────────
# ADD WALLET MONEY
# ─────────────────────────────────────────────────
@user_bp.route('/add-wallet-money', methods=['POST'])
@login_required
@handle_exceptions
def add_wallet_money():
    dataset_user = get_dataset_user()
    if not dataset_user:
        flash('Please log in to add money.', 'warning')
        return redirect(url_for('auth_bp.login'))

    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        amount = 0

    if amount <= 0 or amount > 50000:
        flash('Please enter a valid amount between ₹1 and ₹50,000.', 'danger')
        return redirect(url_for('user_bp.profile'))

    dataset_user.wallet_balance = round((dataset_user.wallet_balance or 0.0) + amount, 2)
    db.session.commit()
    flash(f'₹{amount:.0f} added to your wallet! New balance: ₹{dataset_user.wallet_balance:.2f}', 'success')
    return redirect(url_for('user_bp.profile'))


# ─────────────────────────────────────────────────
# WITHDRAW WALLET MONEY
# Add this route to user_routes.py, right after add_wallet_money()
# ─────────────────────────────────────────────────
@user_bp.route('/withdraw-wallet-money', methods=['POST'])
@login_required
@handle_exceptions
def withdraw_wallet_money():
    """
    Deducts the requested amount from the user's in-app wallet.
    In a real app this would trigger a payout to the selected payment method.
    Here we just deduct the balance (demo mode).
    """
    dataset_user = get_dataset_user()
    if not dataset_user:
        flash('Please log in to withdraw money.', 'warning')
        return redirect(url_for('auth_bp.login'))

    try:
        amount = float(request.form.get('amount', 0))
    except (ValueError, TypeError):
        amount = 0

    withdraw_method = request.form.get('withdraw_method', 'bank').strip()

    current_balance = round(dataset_user.wallet_balance or 0.0, 2)

    if amount <= 0:
        flash('Please enter a valid withdrawal amount.', 'danger')
        return redirect(url_for('user_bp.profile'))

    if amount > current_balance:
        flash(
            f'Insufficient balance. Your wallet has ₹{current_balance:.2f} '
            f'but you tried to withdraw ₹{amount:.2f}.',
            'danger'
        )
        return redirect(url_for('user_bp.profile'))

    if amount > 50000:
        flash('Maximum withdrawal per transaction is ₹50,000.', 'danger')
        return redirect(url_for('user_bp.profile'))

    # Deduct from wallet
    dataset_user.wallet_balance = round(current_balance - amount, 2)
    db.session.commit()

    method_labels = {
        'bank':  'Bank Account',
        'upi':   'UPI',
        'card':  'Debit Card',
        'paytm': 'Paytm / PhonePe',
    }
    method_label = method_labels.get(withdraw_method, 'your payment method')

    flash(
        f'₹{amount:.0f} withdrawn to {method_label}. '
        f'Remaining wallet balance: ₹{dataset_user.wallet_balance:.2f}.',
        'success'
    )
    return redirect(url_for('user_bp.profile'))


# --------------------------------------------------
# MOVIE OPTIONS
# --------------------------------------------------
@user_bp.route('/movie-options/<path:title>')
@handle_exceptions
def movie_options(title):
    variants = (Movie.query
                .filter(Movie.title == title, Movie.status == 'active')
                .order_by(Movie.language, Movie.genre)
                .all())
    if not variants:
        flash('Movie not found.', 'danger')
        return redirect(url_for('user_bp.movies'))

    return render_template(
        'user/movie_options.html',
        title=title, variants=variants, sample=variants[0]
    )


# --------------------------------------------------
# THEATER DETAIL
# --------------------------------------------------
@user_bp.route('/theater/<theater_id>')
@handle_exceptions
def theater_detail(theater_id):
    theater = Theater.query.get_or_404(theater_id)
    city    = session.get('city', '').strip()

    raw_shows = (
        db.session.query(Show, Movie)
        .join(Movie, Movie.movie_id == Show.movie_id)
        .filter(Show.theater_id == theater_id,
                Show.status     == 'active',
                Movie.status    == 'active')
        .order_by(Movie.title, Show.show_date, Show.start_time)
        .all()
    )

    movie_map = {}
    for show, movie in raw_shows:
        if movie.title not in movie_map:
            movie_map[movie.title] = {'movie': movie, 'shows': []}
        movie_map[movie.title]['shows'].append(show)

    screens       = Screen.query.filter_by(theater_id=theater_id).all()
    now_playing   = list(movie_map.values())

    return render_template(
        'user/theater_detail.html',
        theater       = theater,
        now_playing   = now_playing,
        screens       = screens,
        total_shows   = len(raw_shows),
        total_movies  = len(now_playing),
        total_screens = len(screens),
        city          = city
    )


# --------------------------------------------------
# THEATERS LIST
# --------------------------------------------------
@user_bp.route('/theaters')
@handle_exceptions
def theaters():
    city     = request.args.get('city',  '').strip()
    state    = request.args.get('state', '').strip()
    search   = request.args.get('q',     '').strip()
    page     = max(1, int(request.args.get('page', 1)))
    PER_PAGE = 12

    # Only show theaters that have at least one active show
    theaters_with_shows = (
        db.session.query(Show.theater_id)
        .filter(Show.status == 'active')
        .distinct()
    )

    query = Theater.query.filter(
        ~Theater.theater_id.like('LOC_%'),
        Theater.city != '(placeholder)',
        Theater.theater_id.in_(theaters_with_shows)
    )

    if city:
        query = query.filter(Theater.city.ilike(f'%{city}%'))
    if state:
        query = query.filter(Theater.state.ilike(f'%{state}%'))
    if search:
        query = query.filter(Theater.name.ilike(f'%{search}%'))

    total        = query.count()
    total_pages  = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page         = min(page, total_pages)
    theater_list = (query.order_by(Theater.name)
                         .offset((page - 1) * PER_PAGE)
                         .limit(PER_PAGE)
                         .all())

    for t in theater_list:
        t._show_count = Show.query.filter_by(theater_id=t.theater_id,
                                              status='active').count()

    all_states = sorted(set(
        r[0].strip() for r in
        db.session.query(Theater.state)
            .filter(Theater.state != None,
                    ~Theater.theater_id.like('LOC_%'),
                    Theater.theater_id.in_(theaters_with_shows))
            .distinct().all()
        if r[0] and r[0].strip()
    ))
    # Build a mapping of state -> sorted list of cities for dynamic city dropdown
    state_city_rows = (
        db.session.query(Theater.state, Theater.city)
            .filter(Theater.city  != None,
                    Theater.city  != '(placeholder)',
                    Theater.state != None,
                    ~Theater.theater_id.like('LOC_%'),
                    Theater.theater_id.in_(theaters_with_shows))
            .distinct().all()
    )
    cities_by_state = {}
    for s, c in state_city_rows:
        s = s.strip() if s else ''
        c = c.strip() if c else ''
        if s and c:
            cities_by_state.setdefault(s, set()).add(c)
    cities_by_state = {s: sorted(cs) for s, cs in cities_by_state.items()}

    return render_template(
        'user/theaters.html',
        theaters        = theater_list,
        total           = total,
        page            = page,
        total_pages     = total_pages,
        per_page        = PER_PAGE,
        search          = search,
        selected_city   = city,
        selected_state  = state,
        all_states      = all_states,
        cities_by_state = cities_by_state,
        active_page     = 'theaters'
    )


# --------------------------------------------------
# ABOUT PAGE
# --------------------------------------------------
@user_bp.route('/about')
@handle_exceptions
def about():
    # Use the same queries as home() so numbers match exactly
    total_movies   = (db.session.query(func.count(distinct(Movie.title)))
                      .filter(Movie.status == 'active')
                      .scalar() or 0)
    total_theaters = Theater.query.count() or 0
    total_bookings = Booking.query.filter(Booking.payment_status != 'cancelled').count() or 0
    total_cities   = (db.session.query(func.count(distinct(Theater.city)))
                      .filter(Theater.city != None,
                              Theater.city != '',
                              Theater.city != '(placeholder)')
                      .scalar() or 0)
 
    about_stats = {
        'total_movies'   : total_movies,
        'total_theaters' : total_theaters,
        'total_bookings' : total_bookings,
        'total_cities'   : total_cities,
    }
    return render_template('user/about.html', active_page='about', about_stats=about_stats)