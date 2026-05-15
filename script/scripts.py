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
    # BRAND BUILD  ← KEY FIX: build ONCE, consistently, no post-upper() needed
    # -----------------------
    if "theaters" in sheets:
        df = sheets["theaters"].copy()
        df["brand_name"] = df["name"].apply(lambda x: str(x).strip().split()[0])

        # Sort brand names for stable IDs across runs
        unique_brands = sorted(df["brand_name"].unique())
        brands = pd.DataFrame({
            "brand_name": unique_brands,
            "brand_id":   ["BR_" + str(i + 1) for i in range(len(unique_brands))]
        })

        df = df.merge(brands[["brand_name", "brand_id"]], on="brand_name", how="left")

        sheets["theater_brands"] = brands[["brand_id", "brand_name"]].copy()
        sheets["theaters"] = df[["theater_id", "brand_id", "name", "location", "city", "state"]].copy()

        # Verify FK consistency immediately
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

    enforce_fk("theaters", "theater_brands", "brand_id", "brand_id")  # ← added
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

        # Nullify booking_id values that don't exist in bookings (avoids FK violation)
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
    # -----------------------
    if "payments" in sheets:
        sheets["payments"]["status"] = sheets["payments"]["status"].str.lower().replace({
            "success":  "completed",
            "failed":   "failed",
            "refunded": "refunded",
            "pending":  "pending",
        })

    # -----------------------
    # MERGE PAYMENT STATUS INTO BOOKINGS
    # -----------------------
    if "bookings" in sheets and "payments" in sheets:
        sheets["bookings"] = sheets["bookings"].drop(columns=["payment_status"], errors="ignore")
        sheets["bookings"] = sheets["bookings"].merge(
            sheets["payments"][["booking_id", "status"]],
            on="booking_id", how="left"
        ).rename(columns={"status": "payment_status"})
        sheets["bookings"]["payment_status"] = sheets["bookings"]["payment_status"].fillna("failed")

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
    # -----------------------
    if "movies" in sheets:
        sheets["movies"]["poster_url"] = None
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
    Seat
)


def seed_csv_data():

    # Prevent duplicate inserts
    if Movie.query.first():
        print("CSV data already seeded")
        return

    print("Starting CSV database seeding...")

    # ---------------- USERS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "c_user.csv")):

        users = pd.read_csv(os.path.join(BASE_DIR, "c_user.csv"))

        for _, row in users.iterrows():

            user = User(
                user_id=row["user_id"],
                name=row["name"],
                email=row["email"],
                phone_number=row["phone_number"],
                dob=row["dob"]
            )

            db.session.add(user)

        db.session.commit()

        print("Users inserted")

    # ---------------- MOVIES ----------------

    if os.path.exists(os.path.join(BASE_DIR, "movies.csv")):

        movies = pd.read_csv(os.path.join(BASE_DIR, "movies.csv"))

        for _, row in movies.iterrows():

            poster_path = row.get("poster_url")

            if pd.isna(poster_path) or not poster_path:
                poster_path = "uploads/posters/default.jpg"

            movie = Movie(
                movie_id=row["movie_id"],
                title=row["title"],
                genre=row["genre"],
                language=row["language"],
                duration=row["duration"],
                rating=row["rating"],
                release_date=row["release_date"],
                description=row["description"],
                poster_url=poster_path,
                status=row["status"]
            )

            db.session.add(movie)

        db.session.commit()

        print("Movies inserted")

    # ---------------- THEATER BRANDS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "theater_brands.csv")):

        brands = pd.read_csv(os.path.join(BASE_DIR, "theater_brands.csv"))

        for _, row in brands.iterrows():

            brand = TheaterBrand(
                brand_id=row["brand_id"],
                brand_name=row["brand_name"]
            )

            db.session.add(brand)

        db.session.commit()

        print("Brands inserted")

    # ---------------- THEATERS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "theaters.csv")):

        theaters = pd.read_csv(os.path.join(BASE_DIR, "theaters.csv"))

        for _, row in theaters.iterrows():

            theater = Theater(
                theater_id=row["theater_id"],
                brand_id=row["brand_id"],
                name=row["name"],
                location=row["location"],
                city=row["city"],
                state=row["state"]
            )

            db.session.add(theater)

        db.session.commit()

        print("Theaters inserted")

    # ---------------- SCREENS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "screens.csv")):

        screens = pd.read_csv(os.path.join(BASE_DIR, "screens.csv"))

        for _, row in screens.iterrows():

            screen = Screen(
                screen_id=row["screen_id"],
                theater_id=row["theater_id"],
                screen_number=row["screen_number"],
                total_seats=row["total_seats"]
            )

            db.session.add(screen)

        db.session.commit()

        print("Screens inserted")

    # ---------------- SHOWS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "shows.csv")):

        shows = pd.read_csv(os.path.join(BASE_DIR, "shows.csv"))

        for _, row in shows.iterrows():

            show = Show(
                show_id=row["show_id"],
                movie_id=row["movie_id"],
                theater_id=row["theater_id"],
                screen_id=row["screen_id"],
                show_date=row["show_date"],
                start_time=row["start_time"],
                price=row["price"],
                available_seats=row["available_seats"],
                status=row["status"]
            )

            db.session.add(show)

        db.session.commit()

        print("Shows inserted")

    # ---------------- SEATS ----------------

    if os.path.exists(os.path.join(BASE_DIR, "seats.csv")):

        seats = pd.read_csv(os.path.join(BASE_DIR, "seats.csv"))

        for _, row in seats.iterrows():

            seat = Seat(
                seat_id=row["seat_id"],
                booking_id=(
                    None
                    if pd.isna(row.get("booking_id"))
                    else row.get("booking_id")
                ),
                screen_id=row["screen_id"],
                seat_number=row["seat_number"],
                seat_type=row["seat_type"],
                charger=row["charger"],
                status=row["status"],
                show_id=(
                    None
                    if pd.isna(row.get("show_id"))
                    else row.get("show_id")
                )
            )

            db.session.add(seat)

        db.session.commit()

        print("Seats inserted")

    print("CSV seeding completed successfully")