"""
CineBook — chatbot_routes.py
AI-powered chatbot using Google AI Studio (Gemini 2.5 Flash) that queries the live database
and answers movie / show / theater / booking questions.

Register in app.py:
    from routes.user.chatbot_routes import chatbot_bp
    app.register_blueprint(chatbot_bp)

Setup:
    Set GOOGLE_AI_API_KEY environment variable or replace the placeholder below.
    Get your free API key at: https://aistudio.google.com/app/apikey
"""

from flask import Blueprint, request, jsonify, session
from datetime import date
import json, re, urllib.request, urllib.error, os

from extensions import db
from models import Movie, Show, Theater, Booking, Review, Screen
from sqlalchemy import func, or_

chatbot_bp = Blueprint('chatbot_bp', __name__)

# ─────────────────────────────────────────────────────────────
# Google AI Studio (Gemini) API — plain urllib, no SDK needed
# ─────────────────────────────────────────────────────────────
GOOGLE_AI_API_KEY = os.environ.get("GOOGLE_AI_API_KEY", "AIzaSyB8xH8RCVwU62F1ok95DKfrdGowtoPtCUM")
GEMINI_MODEL      = "gemini-2.5-flash-preview-04-17"   # ← Gemini 2.5 Flash
GEMINI_API_URL    = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GOOGLE_AI_API_KEY}"
)


def call_gemini(system_prompt: str, messages: list) -> str:
    """Call the Google AI Studio Gemini 2.5 Flash API."""
    contents = []

    # Inject system prompt as a user/model exchange (Gemini's recommended pattern)
    contents.append({
        "role": "user",
        "parts": [{"text": f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n[/SYSTEM INSTRUCTIONS]\n\nAcknowledge these instructions."}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Understood! I am CineBot, your CineBook AI assistant powered by Google AI. Ready to help with movies, shows, theaters, and bookings!"}]
    })

    for msg in messages:
        role    = msg.get('role', 'user')
        content = msg.get('content', '')
        gemini_role = 'model' if role in ('assistant', 'model') else 'user'
        contents.append({"role": gemini_role, "parts": [{"text": content}]})

    payload = json.dumps({
        "contents": contents,
        "generationConfig": {
            "temperature"    : 0.7,
            "maxOutputTokens": 1024,
            "topP"           : 0.9,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
    }).encode()

    req = urllib.request.Request(
        GEMINI_API_URL,
        data    = payload,
        method  = "POST",
        headers = {"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "Sorry, I couldn't generate a response. Please try again!"


# ─────────────────────────────────────────────────────────────
# DB context builder
# ─────────────────────────────────────────────────────────────
def build_db_context(user_message: str) -> str:
    msg_lower = user_message.lower()
    ctx_parts  = []
    today      = date.today()

    # 1. Currently running / upcoming movies
    if any(w in msg_lower for w in [
        "now showing", "running", "currently", "showing", "today",
        "movies", "film", "watch", "book", "ticket", "what's on",
        "available", "playing"
    ]):
        rows = (
            db.session.query(Movie, func.count(Show.show_id).label('show_count'))
            .join(Show, Movie.movie_id == Show.movie_id)
            .filter(Show.show_date >= today, Show.status == 'active', Movie.status == 'active')
            .group_by(Movie.movie_id)
            .order_by(func.count(Show.show_id).desc())
            .limit(12).all()
        )
        if rows:
            lines = ["CURRENTLY SHOWING MOVIES (with active shows):"]
            for m, cnt in rows:
                lines.append(f"  - {m.title} | Genre: {m.genre} | Lang: {m.language} | Rating: {m.rating}/10 | {cnt} show(s)")
            ctx_parts.append("\n".join(lines))

    # 2. Top rated movies
    if any(w in msg_lower for w in ["best", "top", "highest rated", "recommend", "good", "popular", "must watch"]):
        rows = Movie.query.filter(Movie.status == 'active', Movie.rating >= 7).order_by(Movie.rating.desc()).limit(8).all()
        if rows:
            lines = ["TOP RATED MOVIES (rating >= 7):"]
            for m in rows:
                lines.append(f"  - {m.title} {m.rating}/10 | {m.genre} | {m.language}")
            ctx_parts.append("\n".join(lines))

    # 3. Genre search
    genres = ["action", "comedy", "drama", "thriller", "horror", "romance",
              "sci-fi", "animation", "family", "crime", "mystery", "adventure"]
    for genre in [g for g in genres if g in msg_lower][:2]:
        rows = Movie.query.filter(Movie.status == 'active', Movie.genre.ilike(f'%{genre}%')).order_by(Movie.rating.desc()).limit(6).all()
        if rows:
            lines = [f"{genre.upper()} MOVIES:"]
            for m in rows:
                lines.append(f"  - {m.title} {m.rating} | {m.language}")
            ctx_parts.append("\n".join(lines))

    # 4. Language search
    langs = ["hindi", "english", "tamil", "telugu", "kannada", "malayalam", "marathi", "bengali", "punjabi"]
    for lang in [l for l in langs if l in msg_lower][:2]:
        rows = Movie.query.filter(Movie.status == 'active', Movie.language.ilike(f'%{lang}%')).order_by(Movie.rating.desc()).limit(6).all()
        if rows:
            lines = [f"{lang.upper()} MOVIES:"]
            for m in rows:
                lines.append(f"  - {m.title} {m.rating} | {m.genre}")
            ctx_parts.append("\n".join(lines))

    # 5. Specific movie lookup
    words = re.findall(r'[a-zA-Z]{3,}', user_message)
    if len(words) >= 2:
        for combo_len in [4, 3, 2]:
            for i in range(len(words) - combo_len + 1):
                phrase = " ".join(words[i:i+combo_len])
                m = Movie.query.filter(Movie.title.ilike(f'%{phrase}%'), Movie.status == 'active').first()
                if m:
                    shows = (
                        db.session.query(Show, Theater)
                        .join(Theater, Show.theater_id == Theater.theater_id)
                        .filter(Show.movie_id == m.movie_id, Show.show_date >= today, Show.status == 'active')
                        .order_by(Show.show_date, Show.start_time).limit(5).all()
                    )
                    avg_rev = db.session.query(func.avg(Review.rating)).filter(Review.movie_id == m.movie_id).scalar()
                    info = [
                        f"MOVIE DETAILS - '{m.title}':",
                        f"  Genre: {m.genre} | Language: {m.language} | Duration: {m.duration} min",
                        f"  Rating: {m.rating}/10 (user avg: {round(avg_rev,1) if avg_rev else 'N/A'})",
                        f"  Released: {m.release_date}",
                        f"  Synopsis: {(m.description or '')[:200]}...",
                    ]
                    if shows:
                        info.append("  Upcoming shows:")
                        for sh, th in shows:
                            info.append(f"    - {sh.show_date} {sh.start_time.strftime('%I:%M %p')} at {th.name}, {th.city} - Rs.{sh.price:.0f} ({sh.available_seats} seats)")
                    else:
                        info.append("  No upcoming shows scheduled.")
                    ctx_parts.append("\n".join(info))
                    break
            else:
                continue
            break

    # 6. Theater / city search
    cities = ["mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata",
              "pune", "ahmedabad", "jaipur", "surat", "lucknow", "kochi", "nagpur", "indore",
              "kurnool", "mangalore", "vizag", "visakhapatnam"]
    found_cities = [c for c in cities if c in msg_lower]
    if found_cities or any(w in msg_lower for w in ["theater", "theatre", "cinema", "multiplex", "hall"]):
        for city in found_cities[:2]:
            rows = Theater.query.filter(Theater.city.ilike(f'%{city}%')).limit(6).all()
            if rows:
                lines = [f"THEATERS IN {city.upper()}:"]
                for t in rows:
                    lines.append(f"  - {t.name} | {t.location}")
                ctx_parts.append("\n".join(lines))
        if not found_cities and any(w in msg_lower for w in ["theater", "theatre", "cinema"]):
            total = Theater.query.count()
            cities_list = db.session.query(Theater.city).distinct().limit(10).all()
            ctx_parts.append(f"We have {total} theaters across: " + ", ".join(c[0] for c in cities_list if c[0]))

    # 7. Show timings today
    if any(w in msg_lower for w in ["timing", "time", "schedule", "show time", "when", "slot"]):
        rows = (
            db.session.query(Show, Movie, Theater)
            .join(Movie, Show.movie_id == Movie.movie_id)
            .join(Theater, Show.theater_id == Theater.theater_id)
            .filter(Show.show_date == today, Show.status == 'active')
            .order_by(Show.start_time).limit(8).all()
        )
        if rows:
            lines = [f"TODAY'S SHOW TIMINGS ({today}):"]
            for sh, mv, th in rows:
                lines.append(f"  - {sh.start_time.strftime('%I:%M %p')} - {mv.title} at {th.name}, {th.city} | Rs.{sh.price:.0f}")
            ctx_parts.append("\n".join(lines))

    # 8. User bookings
    uid = session.get('dataset_user_id') or session.get('user_id')
    if uid and any(w in msg_lower for w in ["my booking", "my ticket", "my reservation", "i booked", "cancel", "history", "past booking"]):
        rows = (
            db.session.query(Booking, Show, Movie)
            .join(Show, Booking.show_id == Show.show_id)
            .join(Movie, Show.movie_id == Movie.movie_id)
            .filter(Booking.user_id == uid)
            .order_by(Booking.booking_date.desc()).limit(5).all()
        )
        if rows:
            lines = ["YOUR RECENT BOOKINGS:"]
            for bk, sh, mv in rows:
                lines.append(f"  - {mv.title} on {sh.show_date} | Seats: {bk.seat_numbers} | Rs.{bk.total_amount:.0f} | {bk.payment_status} | ID: {bk.booking_id}")
            ctx_parts.append("\n".join(lines))

    # 9. Platform stats
    if any(w in msg_lower for w in ["how many", "total", "statistics", "stats", "count"]):
        movie_count   = Movie.query.filter_by(status='active').count()
        theater_count = Theater.query.count()
        show_count    = Show.query.filter(Show.show_date >= today, Show.status == 'active').count()
        ctx_parts.append(f"PLATFORM STATS: {movie_count} active movies | {theater_count} theaters | {show_count} upcoming shows")

    # 10. Ticket prices
    if any(w in msg_lower for w in ["price", "cost", "cheap", "expensive", "affordable", "ticket price", "how much"]):
        result = db.session.query(func.min(Show.price), func.max(Show.price), func.avg(Show.price)).filter(Show.show_date >= today, Show.status == 'active').first()
        if result and result[0]:
            ctx_parts.append(f"TICKET PRICES: Min Rs.{result[0]:.0f} | Max Rs.{result[1]:.0f} | Avg Rs.{result[2]:.0f}")

    return "\n\n".join(ctx_parts) if ctx_parts else ""


# ─────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are CineBot, the friendly AI assistant for CineBook — an online movie ticket booking platform. You are powered by Google AI Studio (Gemini 2.5 Flash).

You help users with:
- Finding movies currently showing or upcoming
- Movie details: genre, language, rating, synopsis, duration
- Show timings and theater locations
- Ticket prices and seat availability
- Booking tickets (guide them to the website — you cannot book directly)
- Checking their booking history
- Recommendations based on genre, language, or mood

Tone: Friendly, enthusiastic about movies, concise. Use emojis sparingly (🎬🎟️⭐).
Format: Use short bullet lists when listing movies/shows. Keep replies under 200 words.
Only answer questions related to movies, bookings, theaters, and the CineBook platform.
Always use the DATABASE CONTEXT provided to give accurate, live answers.
If no context matches, say you don't have that info and suggest they browse the site."""


# ─────────────────────────────────────────────────────────────
# Chatbot API endpoint — Google AI Studio (Gemini 2.5 Flash)
# ─────────────────────────────────────────────────────────────
@chatbot_bp.route('/api/chatbot/google', methods=['POST'])
def chatbot_google():
    data     = request.get_json(silent=True) or {}
    user_msg = (data.get('message') or '').strip()
    history  = data.get('history', [])

    if not user_msg:
        return jsonify({'reply': 'Please type a message!'}), 400
    if len(user_msg) > 500:
        return jsonify({'reply': 'Please keep your message under 500 characters.'}), 400

    try:
        db_context = build_db_context(user_msg)
    except Exception as e:
        db_context = ""
        print(f"[chatbot] DB context error: {e}")

    system = SYSTEM_PROMPT
    if db_context:
        system += f"\n\n=== LIVE DATABASE CONTEXT ===\n{db_context}\n=== END CONTEXT ==="

    messages = []
    for turn in history[-6:]:
        role    = turn.get('role', '')
        content = turn.get('content', '')
        if role in ('user', 'assistant', 'model') and content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': user_msg})

    try:
        reply = call_gemini(system, messages)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"[chatbot] Gemini API HTTP error {e.code}: {err_body}")
        reply = "Sorry, I'm having trouble connecting right now. Please try again! 🙏"
    except Exception as e:
        print(f"[chatbot] Gemini API error: {e}")
        reply = "Oops! Something went wrong. Please try again shortly."

    return jsonify({'reply': reply})


# Backwards-compatibility alias
@chatbot_bp.route('/api/chatbot', methods=['POST'])
def chatbot():
    return chatbot_google()