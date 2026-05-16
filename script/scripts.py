import pandas as pd
import psycopg2
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file = os.path.join(BASE_DIR, "BookMyShow_Dataset.xlsx")

if __name__ == "__main__":

    sheets = pd.read_excel(file, sheet_name=None)
    sheets = {k.lower(): v for k, v in sheets.items()}

    # -----------------------
    # CLEAN
    # -----------------------

    def clean(df):
        df.columns = df.columns.str.strip().str.lower()
        df = df.drop_duplicates()
        df = df.dropna(how="all")
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].astype(str).str.strip()
        return df

    for name in sheets:
        sheets[name] = clean(sheets[name])
        print(f"Cleaned: {name} ({len(sheets[name])} rows)")

    # -----------------------
    # USERS → c_user
    # -----------------------
    if "users" in sheets:
        sheets["users"] = sheets["users"].drop_duplicates(subset=["email"])
        if "date_of_birth" in sheets["users"].columns:
            sheets["users"] = sheets["users"].rename(columns={"date_of_birth": "dob"})
        sheets["c_user"] = sheets.pop("users")

    # -----------------------
    # DEDUP
    # -----------------------
    if "screens" in sheets:
        sheets["screens"] = sheets["screens"].drop_duplicates(subset=["theater_id", "screen_number"])

    if "seats" in sheets:
        sheets["seats"] = sheets["seats"].drop_duplicates(subset=["screen_id", "seat_number"])

    # -----------------------
    # RENAME
    # -----------------------
    rename_map = {
        "movies":   {"m_lang": "language", "descp": "description"},
        "theaters": {"t_name": "name"},
        "shows":    {"show_time": "start_time"},
        "bookings": {"booking_time": "booking_date"},
        "payments": {"transaction_status": "status"},
        "reviews":  {"review_text": "comment"},
    }
    for table, mapping in rename_map.items():
        if table in sheets:
            sheets[table] = sheets[table].rename(columns=mapping)

    # -----------------------
    # FIX PRICE
    # -----------------------
    if "shows" in sheets:
        if "price" not in sheets["shows"].columns and "price_per_ticket" in sheets["shows"].columns:
            sheets["shows"] = sheets["shows"].rename(columns={"price_per_ticket": "price"})
        sheets["shows"]["price"] = pd.to_numeric(sheets["shows"]["price"], errors="coerce")

    # -----------------------
    # FIX show_id CASE
    # -----------------------
    if "shows" in sheets:
        sheets["shows"]["show_id"] = sheets["shows"]["show_id"].astype(str).str.strip().str.upper()
    if "bookings" in sheets:
        sheets["bookings"]["show_id"] = sheets["bookings"]["show_id"].astype(str).str.strip().str.upper()

    # -----------------------
    # FIX NUMERIC TYPES
    # -----------------------
    if "bookings" in sheets:
        sheets["bookings"]["total_tickets"] = pd.to_numeric(
            sheets["bookings"]["total_tickets"], errors="coerce"
        ).fillna(0).astype(int)

    # -----------------------
    # SEATS: rename 'charges' → 'charger'
    # -----------------------
    if "seats" in sheets:
        if "charges" in sheets["seats"].columns and "charger" not in sheets["seats"].columns:
            sheets["seats"] = sheets["seats"].rename(columns={"charges": "charger"})

    # -----------------------
    # BRAND BUILD
    # -----------------------
    if "theaters" in sheets:
        df = sheets["theaters"].copy()
        df["brand_name"] = df["name"].apply(lambda x: str(x).strip().split()[0])

        unique_brands = sorted(df["brand_name"].unique())
        brands = pd.DataFrame({
            "brand_name": unique_brands,
            "brand_id":   ["BR_" + str(i + 1) for i in range(len(unique_brands))]
        })

        df = df.merge(brands[["brand_name", "brand_id"]], on="brand_name", how="left")

        sheets["theater_brands"] = brands[["brand_id", "brand_name"]].copy()
        sheets["theaters"] = df[["theater_id", "brand_id", "name", "location", "city", "state"]].copy()

        valid_brands = set(sheets["theater_brands"]["brand_id"])
        used_brands  = set(sheets["theaters"]["brand_id"])
        missing = used_brands - valid_brands
        if missing:
            print(f"⚠️  brand_id mismatch: {missing}")
        else:
            print(f"✅ brand_id FK OK — {len(valid_brands)} brands, {len(sheets['theaters'])} theaters")

    # -----------------------
    # FK VALIDATION
    # -----------------------
    def enforce_fk(child, parent, fk_col, pk_col):
        if child in sheets and parent in sheets:
            before = len(sheets[child])
            valid = set(sheets[parent][pk_col].astype(str))
            sheets[child] = sheets[child][sheets[child][fk_col].astype(str).isin(valid)].copy()
            print(f"FK {child}.{fk_col}: {before} → {len(sheets[child])} rows")

    enforce_fk("theaters", "theater_brands", "brand_id", "brand_id")
    enforce_fk("screens",  "theaters",       "theater_id", "theater_id")

    if "shows" in sheets:
        before = len(sheets["shows"])
        sheets["shows"] = sheets["shows"][
            sheets["shows"]["movie_id"].isin(sheets["movies"]["movie_id"]) &
            sheets["shows"]["theater_id"].isin(sheets["theaters"]["theater_id"]) &
            sheets["shows"]["screen_id"].isin(sheets["screens"]["screen_id"])
        ].copy()
        print(f"FK shows: {before} → {len(sheets['shows'])} rows")

    if "bookings" in sheets:
        before = len(sheets["bookings"])
        sheets["bookings"] = sheets["bookings"][
            sheets["bookings"]["show_id"].isin(sheets["shows"]["show_id"]) &
            sheets["bookings"]["user_id"].isin(sheets["c_user"]["user_id"])
        ].copy()
        print(f"FK bookings: {before} → {len(sheets['bookings'])} rows")

    if "payments" in sheets:
        before = len(sheets["payments"])
        sheets["payments"] = sheets["payments"][
            sheets["payments"]["booking_id"].isin(sheets["bookings"]["booking_id"]) &
            sheets["payments"]["user_id"].isin(sheets["c_user"]["user_id"])
        ].copy()
        print(f"FK payments: {before} → {len(sheets['payments'])} rows")

    if "seats" in sheets:
        before = len(sheets["seats"])
        sheets["seats"] = sheets["seats"][
            sheets["seats"]["screen_id"].isin(sheets["screens"]["screen_id"])
        ].copy()

        valid_bookings = set(sheets["bookings"]["booking_id"].astype(str))
        sheets["seats"]["booking_id"] = sheets["seats"]["booking_id"].apply(
            lambda x: x if str(x) in valid_bookings else None
        )
        print(f"FK seats (screen only): {before} → {len(sheets['seats'])} rows")

    if "reviews" in sheets:
        before = len(sheets["reviews"])
        sheets["reviews"] = sheets["reviews"][
            sheets["reviews"]["movie_id"].isin(sheets["movies"]["movie_id"]) &
            sheets["reviews"]["user_id"].isin(sheets["c_user"]["user_id"])
        ].copy()
        print(f"FK reviews: {before} → {len(sheets['reviews'])} rows")

    # -----------------------
    # STATUS STANDARDIZATION
    # FIX: normalize payment status to lowercase so analytics queries work
    # -----------------------
    STATUS_MAP = {
        "success":   "completed",
        "Success":   "completed",
        "Completed": "completed",
        "completed": "completed",
        "failed":    "failed",
        "Failed":    "failed",
        "refunded":  "refunded",
        "Refunded":  "refunded",
        "pending":   "pending",
        "Pending":   "pending",
        "cancelled": "cancelled",
        "Cancelled": "cancelled",
    }

    if "payments" in sheets:
        sheets["payments"]["status"] = (
            sheets["payments"]["status"]
            .str.strip()
            .str.lower()
            .replace({
                "success":  "completed",
                "failed":   "failed",
                "refunded": "refunded",
                "pending":  "pending",
                "cancelled": "cancelled",
            })
        )

    # -----------------------
    # MERGE PAYMENT STATUS INTO BOOKINGS
    # -----------------------
    if "bookings" in sheets and "payments" in sheets:
        sheets["bookings"] = sheets["bookings"].drop(columns=["payment_status"], errors="ignore")
        sheets["bookings"] = sheets["bookings"].merge(
            sheets["payments"][["booking_id", "status"]],
            on="booking_id", how="left"
        ).rename(columns={"status": "payment_status"})
        # FIX: normalize here too, in case bookings CSV had its own status column
        sheets["bookings"]["payment_status"] = (
            sheets["bookings"]["payment_status"]
            .fillna("failed")
            .str.strip()
            .str.lower()
            .replace({
                "success":  "completed",
                "failed":   "failed",
                "refunded": "refunded",
                "pending":  "pending",
                "cancelled": "cancelled",
            })
        )

    # -----------------------
    # ADD MISSING COLUMNS
    # -----------------------
    if "bookings" in sheets:
        if "seat_numbers" not in sheets["bookings"].columns:
            sheets["bookings"]["seat_numbers"] = None

    # -----------------------
    # TOTAL AMOUNT
    # -----------------------
    if "bookings" in sheets and "shows" in sheets:
        sheets["bookings"] = sheets["bookings"].merge(
            sheets["shows"][["show_id", "price"]], on="show_id", how="left"
        )
        sheets["bookings"]["price"] = pd.to_numeric(
            sheets["bookings"]["price"], errors="coerce"
        ).fillna(0)
        sheets["bookings"]["total_amount"] = (
            sheets["bookings"]["total_tickets"] * sheets["bookings"]["price"]
        )
        sheets["bookings"]["total_amount"] = sheets["bookings"].apply(
            lambda row: row["total_amount"] if row["payment_status"] == "completed" else 0,
            axis=1
        )
        sheets["bookings"].drop(columns=["price"], inplace=True)

    # -----------------------
    # PAYMENT AMOUNT
    # -----------------------
    if "payments" in sheets and "bookings" in sheets:
        sheets["payments"] = sheets["payments"].merge(
            sheets["bookings"][["booking_id", "total_amount"]], on="booking_id", how="left"
        )
        sheets["payments"]["amount"] = sheets["payments"].apply(
            lambda row: row["total_amount"] if row["status"] == "completed" else 0,
            axis=1
        )
        sheets["payments"].drop(columns=["total_amount"], inplace=True)

    # -----------------------
    # DEFAULTS
    # FIX: poster_url — assign numbered fallback per movie so each movie
    # shows a distinct poster (poster_001.jpg … poster_020.jpg cycling)
    # instead of the same default.png for every movie.
    # -----------------------
    if "movies" in sheets:
        NUM_POSTERS = 20
        def _poster(idx):
            n = (idx % NUM_POSTERS) + 1
            return f"uploads/posters/poster_{n:03d}.jpg"

        sheets["movies"]["poster_url"] = [
            _poster(i) for i in range(len(sheets["movies"]))
        ]
        sheets["movies"]["status"] = "active"

    if "shows" in sheets:
        sheets["shows"]["status"] = "active"

    if "bookings" in sheets:
        sheets["bookings"]["transaction_ref"] = None

    if "payments" in sheets:
        sheets["payments"]["transaction_ref"] = None

    if "seats" in sheets:
        sheets["seats"]["show_id"] = None
        sheets["seats"]["charger"] = sheets["seats"]["charger"].apply(
            lambda x: True if str(x).strip().lower() not in ["0", "false", "no", "nan", ""] else False
        )

    # -----------------------
    # FINAL COLUMN ORDER
    # -----------------------
    if "bookings" in sheets:
        sheets["bookings"] = sheets["bookings"][[
            "booking_id", "user_id", "show_id", "booking_date",
            "total_tickets", "seat_numbers", "total_amount",
            "payment_status", "transaction_ref"
        ]]

    if "payments" in sheets:
        sheets["payments"] = sheets["payments"][[
            "payment_id", "booking_id", "user_id", "amount",
            "payment_method", "payment_date", "status", "transaction_ref"
        ]]

    if "seats" in sheets:
        sheets["seats"] = sheets["seats"][[
            "seat_id", "booking_id", "screen_id", "seat_number",
            "seat_type", "charger", "status", "show_id"
        ]]

    # -----------------------
    # SAVE CSV
    # -----------------------
    for name, df in sheets.items():
        path = os.path.join(BASE_DIR, f"{name}.csv")
        df.to_csv(path, index=False)
        print(f"Saved {name}.csv ({len(df)} rows)")

# -----------------------
# RENDER DB SEEDING
# -----------------------

from extensions import db

from models import (
    User,
    Movie,
    TheaterBrand,
    Theater,
    Screen,
    Show,
    Seat,
    Booking,
    Payment,
    Review,
)

# Number of poster files in static/uploads/posters/
_NUM_POSTERS = 20


def _poster_for_index(idx: int) -> str:
    """Return a cycling poster filename so every movie gets a distinct image."""
    n = (idx % _NUM_POSTERS) + 1
    return f"uploads/posters/poster_{n:03d}.jpg"


def _bulk_insert(session, objects, chunk=500):
    """Add objects in chunks to avoid huge transactions."""
    for i in range(0, len(objects), chunk):
        session.add_all(objects[i:i + chunk])
        session.commit()


def seed_csv_data():

    # Prevent duplicate inserts
    if Movie.query.first():
        print("CSV data already seeded")
        return

    print("Starting CSV database seeding...")

    # ---------------- USERS ----------------
    path = os.path.join(BASE_DIR, "c_user.csv")
    if os.path.exists(path):
        users_df = pd.read_csv(path)
        objs = []
        for _, row in users_df.iterrows():
            objs.append(User(
                user_id=row["user_id"],
                name=row["name"],
                email=row["email"],
                phone_number=row["phone_number"],
                dob=row["dob"] if not pd.isna(row.get("dob", None)) else None,
            ))
        _bulk_insert(db.session, objs)
        print(f"Users inserted ({len(objs)})")

    # ---------------- MOVIES ----------------
    path = os.path.join(BASE_DIR, "movies.csv")
    if os.path.exists(path):
        movies_df = pd.read_csv(path)
        objs = []
        for idx, row in movies_df.iterrows():
            raw_poster = row.get("poster_url", "")
            # FIX: if seeded CSV still has empty poster_url, assign a numbered fallback
            if pd.isna(raw_poster) or str(raw_poster).strip() in ("", "nan"):
                poster = _poster_for_index(idx)
            else:
                poster = str(raw_poster).strip()
            objs.append(Movie(
                movie_id=row["movie_id"],
                title=row["title"],
                genre=row["genre"],
                language=row["language"],
                duration=row["duration"] if not pd.isna(row.get("duration")) else None,
                rating=row["rating"] if not pd.isna(row.get("rating")) else None,
                release_date=row["release_date"] if not pd.isna(row.get("release_date")) else None,
                description=row["description"] if not pd.isna(row.get("description")) else None,
                poster_url=poster,
                status=row.get("status", "active"),
            ))
        _bulk_insert(db.session, objs)
        print(f"Movies inserted ({len(objs)})")

    # ---------------- THEATER BRANDS ----------------
    path = os.path.join(BASE_DIR, "theater_brands.csv")
    if os.path.exists(path):
        brands_df = pd.read_csv(path)
        objs = [
            TheaterBrand(brand_id=row["brand_id"], brand_name=row["brand_name"])
            for _, row in brands_df.iterrows()
        ]
        _bulk_insert(db.session, objs)
        print(f"Brands inserted ({len(objs)})")

    # ---------------- THEATERS ----------------
    path = os.path.join(BASE_DIR, "theaters.csv")
    if os.path.exists(path):
        theaters_df = pd.read_csv(path)
        objs = [
            Theater(
                theater_id=row["theater_id"],
                brand_id=row["brand_id"],
                name=row["name"],
                location=row.get("location"),
                city=row.get("city"),
                state=row.get("state"),
            )
            for _, row in theaters_df.iterrows()
        ]
        _bulk_insert(db.session, objs)
        print(f"Theaters inserted ({len(objs)})")

    # ---------------- SCREENS ----------------
    path = os.path.join(BASE_DIR, "screens.csv")
    if os.path.exists(path):
        screens_df = pd.read_csv(path)
        objs = [
            Screen(
                screen_id=row["screen_id"],
                theater_id=row["theater_id"],
                screen_number=row["screen_number"],
                total_seats=row["total_seats"] if not pd.isna(row.get("total_seats")) else None,
            )
            for _, row in screens_df.iterrows()
        ]
        _bulk_insert(db.session, objs)
        print(f"Screens inserted ({len(objs)})")

    # ---------------- SHOWS ----------------
    path = os.path.join(BASE_DIR, "shows.csv")
    if os.path.exists(path):
        shows_df = pd.read_csv(path)
        objs = [
            Show(
                show_id=row["show_id"],
                movie_id=row["movie_id"],
                theater_id=row["theater_id"],
                screen_id=row["screen_id"],
                show_date=row["show_date"] if not pd.isna(row.get("show_date")) else None,
                start_time=row["start_time"] if not pd.isna(row.get("start_time")) else None,
                price=row["price"] if not pd.isna(row.get("price")) else None,
                available_seats=row["available_seats"] if not pd.isna(row.get("available_seats")) else None,
                status=row.get("status", "active"),
            )
            for _, row in shows_df.iterrows()
        ]
        _bulk_insert(db.session, objs)
        print(f"Shows inserted ({len(objs)})")

    # ---------------- BOOKINGS ----------------
    # FIX: Bookings were not being seeded at all — this is why revenue showed 0
    path = os.path.join(BASE_DIR, "bookings.csv")
    if os.path.exists(path):
        bookings_df = pd.read_csv(path)
        # Normalize payment_status so analytics queries match 'completed'
        bookings_df["payment_status"] = (
            bookings_df["payment_status"]
            .astype(str).str.strip().str.lower()
            .replace({
                "success":   "completed",
                "complete":  "completed",
            })
            .fillna("failed")
        )
        objs = []
        for _, row in bookings_df.iterrows():
            objs.append(Booking(
                booking_id=row["booking_id"],
                user_id=row["user_id"],
                show_id=row["show_id"],
                booking_date=row["booking_date"] if not pd.isna(row.get("booking_date")) else None,
                total_tickets=int(row["total_tickets"]) if not pd.isna(row.get("total_tickets")) else 0,
                seat_numbers=row["seat_numbers"] if not pd.isna(row.get("seat_numbers")) else None,
                total_amount=float(row["total_amount"]) if not pd.isna(row.get("total_amount")) else 0.0,
                payment_status=row["payment_status"],
                transaction_ref=row["transaction_ref"] if not pd.isna(row.get("transaction_ref")) else None,
            ))
        _bulk_insert(db.session, objs)
        print(f"Bookings inserted ({len(objs)})")

    # ---------------- PAYMENTS ----------------
    # FIX: Payments were not being seeded — payment method chart was empty
    path = os.path.join(BASE_DIR, "payments.csv")
    if os.path.exists(path):
        payments_df = pd.read_csv(path)
        payments_df["status"] = (
            payments_df["status"]
            .astype(str).str.strip().str.lower()
            .replace({
                "success":  "completed",
                "complete": "completed",
            })
            .fillna("failed")
        )
        objs = []
        for _, row in payments_df.iterrows():
            objs.append(Payment(
                payment_id=row["payment_id"],
                booking_id=row["booking_id"] if not pd.isna(row.get("booking_id")) else None,
                user_id=row["user_id"] if not pd.isna(row.get("user_id")) else None,
                amount=float(row["amount"]) if not pd.isna(row.get("amount")) else 0.0,
                payment_method=row["payment_method"] if not pd.isna(row.get("payment_method")) else None,
                payment_date=row["payment_date"] if not pd.isna(row.get("payment_date")) else None,
                status=row["status"],
                transaction_ref=row["transaction_ref"] if not pd.isna(row.get("transaction_ref")) else None,
            ))
        _bulk_insert(db.session, objs)
        print(f"Payments inserted ({len(objs)})")

    # ---------------- REVIEWS ----------------
    # FIX: Reviews were not being seeded
    path = os.path.join(BASE_DIR, "reviews.csv")
    if os.path.exists(path):
        reviews_df = pd.read_csv(path)
        objs = []
        for _, row in reviews_df.iterrows():
            objs.append(Review(
                review_id=row["review_id"],
                user_id=row["user_id"],
                movie_id=row["movie_id"],
                rating=float(row["rating"]) if not pd.isna(row.get("rating")) else None,
                comment=row["comment"] if not pd.isna(row.get("comment")) else None,
                review_date=row.get("review_date") if not pd.isna(row.get("review_date", None)) else None,
            ))
        _bulk_insert(db.session, objs)
        print(f"Reviews inserted ({len(objs)})")

    # ---------------- SEATS ----------------
    path = os.path.join(BASE_DIR, "seats.csv")
    if os.path.exists(path):
        seats_df = pd.read_csv(path)
        objs = []
        for _, row in seats_df.iterrows():
            objs.append(Seat(
                seat_id=row["seat_id"],
                booking_id=None if pd.isna(row.get("booking_id")) else row.get("booking_id"),
                screen_id=row["screen_id"],
                seat_number=row["seat_number"],
                seat_type=row["seat_type"] if not pd.isna(row.get("seat_type")) else None,
                charger=row["charger"] if not pd.isna(row.get("charger")) else False,
                status=row["status"] if not pd.isna(row.get("status")) else "available",
                show_id=None if pd.isna(row.get("show_id")) else row.get("show_id"),
            ))
        _bulk_insert(db.session, objs)
        print(f"Seats inserted ({len(objs)})")

    print("CSV seeding completed successfully")