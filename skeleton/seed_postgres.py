"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import hashlib
import json
import os
import sys

import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


def _hash_password(plaintext):
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with a random salt.

    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

    Why PBKDF2 over plain SHA-256:
      - PBKDF2 applies key stretching (100,000 iterations), making brute-force
        attacks orders of magnitude slower than a single SHA-256 round.
      - A per-user random salt (os.urandom) defeats pre-computed rainbow-table
        attacks: two users with the same password get different hashes.
      - PBKDF2 is NIST-approved (SP 800-132) and available in the Python
        standard library — no extra packages required.
    """
    iterations = 100_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plaintext.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def _split_full_name(full_name):
    """Split 'First Last' into (first_name, last_name).

    If there is only one token, last_name will be empty string.
    If there are more than two tokens, the first token is first_name and the
    rest is last_name (e.g. 'Mei Ling' -> ('Mei', 'Ling')).
    """
    parts = full_name.strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_registered_users(cur):
    """Seed registered_users from registered_users.json."""
    data = load("registered_users.json")
    columns = [
        "user_id", "email", "first_name", "last_name",
        "date_of_birth", "phone_number", "registered_at", "is_active",
    ]
    rows = []
    for u in data:
        first_name, last_name = _split_full_name(u.get("full_name", ""))
        rows.append((
            u["user_id"],
            u["email"],
            first_name,
            last_name,
            u.get("date_of_birth"),       # already "YYYY-MM-DD"
            u.get("phone"),               # JSON key is "phone"
            u.get("registered_at"),
            u.get("is_active", True),
        ))
    n = insert_many(cur, "registered_users", columns, rows)
    print(f"  registered_users: {n} rows inserted (of {len(rows)})")


def seed_user_credentials(cur):
    """Seed user_credentials from registered_users.json.

    password is hashed; email is NOT stored here.
    """
    data = load("registered_users.json")
    columns = ["user_id", "password_hash", "secret_question", "secret_answer"]
    rows = []
    for u in data:
        rows.append((
            u["user_id"],
            _hash_password(u["password"]),
            u.get("secret_question"),
            u.get("secret_answer"),
        ))
    n = insert_many(cur, "user_credentials", columns, rows)
    print(f"  user_credentials: {n} rows inserted (of {len(rows)})")


def seed_metro_stations(cur):
    """Seed metro_stations from metro_stations.json."""
    data = load("metro_stations.json")
    columns = ["station_id", "name", "zone"]
    rows = []
    for s in data:
        rows.append((
            s["station_id"],
            s["name"],
            s.get("zone"),  # JSON has no zone field → None
        ))
    n = insert_many(cur, "metro_stations", columns, rows)
    print(f"  metro_stations: {n} rows inserted (of {len(rows)})")


def seed_metro_station_lines(cur):
    """Seed metro_station_lines from metro_stations.json (lines array)."""
    data = load("metro_stations.json")
    columns = ["station_id", "line_name"]
    rows = []
    for s in data:
        for line in s.get("lines", []):
            rows.append((s["station_id"], line))
    n = insert_many(cur, "metro_station_lines", columns, rows)
    print(f"  metro_station_lines: {n} rows inserted (of {len(rows)})")


def seed_national_rail_stations(cur):
    """Seed national_rail_stations from national_rail_stations.json."""
    data = load("national_rail_stations.json")
    columns = ["station_id", "name", "zone"]
    rows = []
    for s in data:
        rows.append((
            s["station_id"],
            s["name"],
            s.get("zone"),  # JSON has no zone field → None
        ))
    n = insert_many(cur, "national_rail_stations", columns, rows)
    print(f"  national_rail_stations: {n} rows inserted (of {len(rows)})")


def seed_nr_station_lines(cur):
    """Seed nr_station_lines from national_rail_stations.json (lines array)."""
    data = load("national_rail_stations.json")
    columns = ["station_id", "line_name"]
    rows = []
    for s in data:
        for line in s.get("lines", []):
            rows.append((s["station_id"], line))
    n = insert_many(cur, "nr_station_lines", columns, rows)
    print(f"  nr_station_lines: {n} rows inserted (of {len(rows)})")


def seed_metro_schedules(cur):
    """Seed metro_schedules main table from metro_schedules.json."""
    data = load("metro_schedules.json")
    columns = [
        "schedule_id", "line", "direction", "operates_on",
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time",
        "frequency_min", "base_fare_usd", "per_stop_rate_usd",
    ]
    rows = []
    for s in data:
        rows.append((
            s["schedule_id"],
            s["line"],
            s.get("direction"),
            s.get("operates_on", []),     # TEXT[] — psycopg2 handles list→array
            s.get("origin_station_id"),
            s.get("destination_station_id"),
            s.get("first_train_time"),
            s.get("last_train_time"),
            s.get("frequency_min"),
            s.get("base_fare_usd"),
            s.get("per_stop_rate_usd"),
        ))
    n = insert_many(cur, "metro_schedules", columns, rows)
    print(f"  metro_schedules: {n} rows inserted (of {len(rows)})")


def seed_metro_schedule_stops(cur):
    """Seed metro_schedule_stops from metro_schedules.json.

    Expands stops_in_order + travel_time_from_origin_min into rows with
    stop_order (1-based).
    """
    data = load("metro_schedules.json")
    columns = ["schedule_id", "stop_order", "station_id", "arrival_time"]
    rows = []
    for s in data:
        stops = s.get("stops_in_order", [])
        time_map = s.get("travel_time_from_origin_min", {})
        for idx, station_id in enumerate(stops, start=1):
            arrival_time = time_map.get(station_id)  # int or None
            rows.append((s["schedule_id"], idx, station_id, arrival_time))
    n = insert_many(cur, "metro_schedule_stops", columns, rows)
    print(f"  metro_schedule_stops: {n} rows inserted (of {len(rows)})")


def seed_nr_schedules(cur):
    """Seed nr_schedules main table from national_rail_schedules.json."""
    data = load("national_rail_schedules.json")
    columns = [
        "schedule_id", "line", "service_type", "direction",
        "departure_time", "operates_on",
        "origin_station_id", "destination_station_id",
        "first_train_time", "last_train_time", "frequency_min",
    ]
    rows = []
    for s in data:
        rows.append((
            s["schedule_id"],
            s.get("line"),
            s.get("service_type"),
            s.get("direction"),
            s.get("first_train_time"),    # use first_train_time as departure_time
            s.get("operates_on", []),
            s.get("origin_station_id"),
            s.get("destination_station_id"),
            s.get("first_train_time"),
            s.get("last_train_time"),
            s.get("frequency_min"),
        ))
    n = insert_many(cur, "nr_schedules", columns, rows)
    print(f"  nr_schedules: {n} rows inserted (of {len(rows)})")


def seed_nr_schedule_stops(cur):
    """Seed nr_schedule_stops from national_rail_schedules.json.

    For express services, passed_through_stations are included with
    is_stopping = FALSE and travel_time_from_origin_min = None.

    All stations (stopping + passed-through) are merged and sorted by
    the original line order to assign correct stop_order values.
    """
    data = load("national_rail_schedules.json")
    columns = [
        "schedule_id", "stop_order", "station_id",
        "travel_time_from_origin_min", "is_stopping",
    ]
    rows = []
    for s in data:
        stops_in_order = s.get("stops_in_order", [])
        passed = set(s.get("passed_through_stations", []))
        time_map = s.get("travel_time_from_origin_min", {})

        # For normal services: all stations in stops_in_order are stopping
        # For express services: stops_in_order only lists stopping stations.
        # We need to include passed_through_stations with is_stopping=FALSE.
        # The full station order needs to be reconstructed.

        if not passed:
            # Normal service — all stations stop
            for idx, station_id in enumerate(stops_in_order, start=1):
                travel_time = time_map.get(station_id)
                rows.append((
                    s["schedule_id"], idx, station_id, travel_time, True
                ))
        else:
            # Express service — need to determine the full route order.
            # We have stopping stations in stops_in_order and skipped in passed.
            # The line's normal schedule has the full order.
            # For simplicity, we combine stopping + passed and sort by
            # position relative to a reference normal schedule on the same line.

            # Build a combined list: stopping stations keep their time,
            # passed stations have is_stopping=FALSE, time=None
            all_stations = []
            for station_id in stops_in_order:
                all_stations.append({
                    "station_id": station_id,
                    "travel_time": time_map.get(station_id),
                    "is_stopping": True,
                })
            for station_id in passed:
                all_stations.append({
                    "station_id": station_id,
                    "travel_time": None,  # Express doesn't provide times for skipped
                    "is_stopping": False,
                })

            # Sort by using the stopping stations' positions to establish order.
            # The passed-through stations sit between stopping stations on the line.
            # We need a stable reference order. Use the full NR line order from
            # the normal schedules on the same line + direction.

            # Find matching normal schedule for ordering reference
            normal_order = None
            for ref in data:
                if (ref.get("line") == s.get("line")
                        and ref.get("direction") == s.get("direction")
                        and ref.get("service_type") == "normal"):
                    normal_order = ref.get("stops_in_order", [])
                    break

            if normal_order:
                order_map = {sid: i for i, sid in enumerate(normal_order)}
                all_stations.sort(
                    key=lambda x: order_map.get(x["station_id"], 999)
                )
            else:
                # Fallback: keep stopping first, passed after (less ideal)
                print(f"    WARNING: No normal schedule found for line "
                      f"{s.get('line')} {s.get('direction')} to order "
                      f"express stops. Using stops_in_order + passed order.")

            for idx, st in enumerate(all_stations, start=1):
                rows.append((
                    s["schedule_id"], idx, st["station_id"],
                    st["travel_time"], st["is_stopping"],
                ))

    n = insert_many(cur, "nr_schedule_stops", columns, rows)
    print(f"  nr_schedule_stops: {n} rows inserted (of {len(rows)})")


def seed_nr_schedule_fare_classes(cur):
    """Seed nr_schedule_fare_classes from national_rail_schedules.json."""
    data = load("national_rail_schedules.json")
    columns = ["schedule_id", "fare_class", "base_fare_usd", "per_stop_rate_usd"]
    rows = []
    for s in data:
        fare_classes = s.get("fare_classes", {})
        for fare_class, fares in fare_classes.items():
            rows.append((
                s["schedule_id"],
                fare_class,
                fares["base_fare_usd"],
                fares["per_stop_rate_usd"],
            ))
    n = insert_many(cur, "nr_schedule_fare_classes", columns, rows)
    print(f"  nr_schedule_fare_classes: {n} rows inserted (of {len(rows)})")


def seed_nr_seat_coaches(cur):
    """Seed nr_seat_coaches from national_rail_seat_layouts.json."""
    data = load("national_rail_seat_layouts.json")
    columns = ["schedule_id", "coach_number", "fare_class"]
    rows = []
    for layout in data:
        schedule_id = layout["schedule_id"]
        for coach in layout.get("coaches", []):
            rows.append((
                schedule_id,
                coach["coach"],        # coach letter, e.g. "A", "B"
                coach.get("fare_class"),
            ))
    n = insert_many(cur, "nr_seat_coaches", columns, rows)
    print(f"  nr_seat_coaches: {n} rows inserted (of {len(rows)})")


def seed_nr_seats(cur):
    """Seed nr_seats from national_rail_seat_layouts.json.

    PK is (schedule_id, seat_id).
    JSON only has seat_id, row, column — seat_type, is_window,
    has_power_outlet are not in JSON, so they are set to None.
    """
    data = load("national_rail_seat_layouts.json")
    columns = [
        "schedule_id", "seat_id", "coach_number",
        "seat_type", "is_window", "has_power_outlet",
    ]
    rows = []
    for layout in data:
        schedule_id = layout["schedule_id"]
        for coach in layout.get("coaches", []):
            coach_number = coach["coach"]
            for seat in coach.get("seats", []):
                rows.append((
                    schedule_id,
                    seat["seat_id"],
                    coach_number,
                    seat.get("seat_type"),         # Not in JSON → None
                    seat.get("is_window"),          # Not in JSON → None
                    seat.get("has_power_outlet"),   # Not in JSON → None
                ))
    n = insert_many(cur, "nr_seats", columns, rows)
    print(f"  nr_seats: {n} rows inserted (of {len(rows)})")


def seed_nr_bookings(cur):
    """Seed nr_bookings from bookings.json."""
    data = load("bookings.json")
    columns = [
        "booking_id", "user_id", "schedule_id",
        "origin_station_id", "destination_station_id",
        "travel_date", "departure_time",
        "ticket_type", "fare_class", "coach", "seat_id",
        "stops_travelled", "amount_usd", "status",
        "booked_at", "travelled_at",
    ]
    rows = []
    for b in data:
        rows.append((
            b["booking_id"],
            b["user_id"],
            b["schedule_id"],
            b.get("origin_station_id"),
            b.get("destination_station_id"),
            b.get("travel_date"),
            b.get("departure_time"),
            b.get("ticket_type"),
            b.get("fare_class"),
            b.get("coach"),
            b.get("seat_id"),
            b.get("stops_travelled"),
            b.get("amount_usd"),
            b.get("status", "confirmed"),
            b.get("booked_at"),
            b.get("travelled_at"),
        ))
    n = insert_many(cur, "nr_bookings", columns, rows)
    print(f"  nr_bookings: {n} rows inserted (of {len(rows)})")


def seed_metro_travel_history(cur):
    """Seed metro_travel_history from metro_travel_history.json.

    purchased_at and amount_usd may be null per AI_SESSION_CONTEXT.md.
    """
    data = load("metro_travel_history.json")
    columns = [
        "trip_id", "user_id", "schedule_id",
        "origin_station_id", "destination_station_id",
        "travel_date", "ticket_type", "day_pass_ref",
        "stops_travelled", "amount_usd", "status",
        "purchased_at", "travelled_at",
    ]
    rows = []
    for t in data:
        rows.append((
            t["trip_id"],
            t["user_id"],
            t.get("schedule_id"),
            t.get("origin_station_id"),
            t.get("destination_station_id"),
            t.get("travel_date"),
            t.get("ticket_type"),
            t.get("day_pass_ref"),
            t.get("stops_travelled"),
            t.get("amount_usd"),           # nullable
            t.get("status"),
            t.get("purchased_at"),         # nullable
            t.get("travelled_at"),
        ))
    n = insert_many(cur, "metro_travel_history", columns, rows)
    print(f"  metro_travel_history: {n} rows inserted (of {len(rows)})")


def seed_payments(cur):
    """Seed payments from payments.json.

    The JSON has a single 'booking_id' field that may start with 'BK' (national
    rail) or 'MT' (metro). We route it to nr_booking_id or metro_trip_id
    accordingly, satisfying the exclusive CHECK constraint.
    """
    data = load("payments.json")
    columns = [
        "payment_id", "nr_booking_id", "metro_trip_id",
        "amount_usd", "payment_method", "status", "paid_at",
    ]
    rows = []
    for p in data:
        bid = p["booking_id"]
        if bid.startswith("BK"):
            nr_booking_id = bid
            metro_trip_id = None
        elif bid.startswith("MT"):
            nr_booking_id = None
            metro_trip_id = bid
        else:
            print(f"    WARNING: payments — skipping unknown booking_id prefix: {bid}")
            continue  # skip — both FK NULL would violate CHECK constraint

        rows.append((
            p["payment_id"],
            nr_booking_id,
            metro_trip_id,
            p["amount_usd"],
            p["method"],          # JSON key is "method", schema column is "payment_method"
            p.get("status", "paid"),
            p.get("paid_at"),
        ))
    n = insert_many(cur, "payments", columns, rows)
    print(f"  payments: {n} rows inserted (of {len(rows)})")


def seed_feedback(cur):
    """Seed feedback from feedback.json.

    Same BK/MT routing as payments for the exclusive FK constraint.
    """
    data = load("feedback.json")
    columns = [
        "feedback_id", "nr_booking_id", "metro_trip_id",
        "user_id", "rating", "comment", "submitted_at",
    ]
    rows = []
    for f in data:
        bid = f["booking_id"]
        if bid.startswith("BK"):
            nr_booking_id = bid
            metro_trip_id = None
        elif bid.startswith("MT"):
            nr_booking_id = None
            metro_trip_id = bid
        else:
            print(f"    WARNING: feedback — skipping unknown booking_id prefix: {bid}")
            continue  # skip — both FK NULL would violate CHECK constraint

        rows.append((
            f["feedback_id"],
            nr_booking_id,
            metro_trip_id,
            f.get("user_id"),
            f.get("rating"),
            f.get("comment"),        # may be null
            f.get("submitted_at"),
        ))
    n = insert_many(cur, "feedback", columns, rows)
    print(f"  feedback: {n} rows inserted (of {len(rows)})")


# TASK 6 EXTENSION: Seed initial membership loyalty points
def seed_user_loyalty_points(cur):
    """Seed user_loyalty_points with initial membership points.

    Points are hard-coded for the five demo users so the feature is
    immediately testable without external dependencies.
    """
    # TASK 6 EXTENSION
    INITIAL_POINTS = [
        ("RU01", 120),
        ("RU02", 80),
        ("RU03", 250),
        ("RU04", 0),
        ("RU05", 500),
    ]
    columns = ["user_id", "points_balance"]
    n = insert_many(cur, "user_loyalty_points", columns, INITIAL_POINTS)
    print(f"  user_loyalty_points: {n} rows inserted (of {len(INITIAL_POINTS)})")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):\n")

        # 1. Users
        seed_registered_users(cur)
        seed_user_credentials(cur)

        # 2. Stations
        seed_metro_stations(cur)
        seed_metro_station_lines(cur)
        seed_national_rail_stations(cur)
        seed_nr_station_lines(cur)

        # 3. Schedules
        seed_metro_schedules(cur)
        seed_metro_schedule_stops(cur)
        seed_nr_schedules(cur)
        seed_nr_schedule_stops(cur)
        seed_nr_schedule_fare_classes(cur)

        # 4. Seats
        seed_nr_seat_coaches(cur)
        seed_nr_seats(cur)

        # 5. Bookings / Travel History
        seed_nr_bookings(cur)
        seed_metro_travel_history(cur)

        # 6. Payments & Feedback
        seed_payments(cur)
        seed_feedback(cur)

        # TASK 6 EXTENSION: Loyalty points
        seed_user_loyalty_points(cur)

        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
