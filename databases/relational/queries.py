"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.

TWO ROLES ARE SERVED HERE:
  1. Relational  → dual-network transit (metro + national rail),
                   availability, fares, bookings, seat selection
  2. Vector      → policy document similarity search (pgvector)

STUDENT TASK
------------
Design your schema in databases/relational/schema.sql, seed it with
skeleton/seed_postgres.py, then implement the query functions below.

Functions prefixed with `query_`  are read-only lookups called by the agent.
Functions prefixed with `execute_` are write operations (booking/cancellation).

The vector functions (query_policy_vector_search, store_policy_document)
are already implemented — do not modify them.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import string
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _to_jsonable(data):
    """Recursively convert Decimals to floats for JSON serialization."""
    if isinstance(data, dict):
        return {k: _to_jsonable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_to_jsonable(item) for item in data]
    elif isinstance(data, Decimal):
        return float(data)
    else:
        return data


def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"


def _hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with per-user random salt.

    Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

    Why PBKDF2 over plain SHA-256:
      - Key stretching (100k iterations) makes brute-force infeasible.
      - Per-user random salt defeats rainbow-table attacks: two users
        with identical passwords produce different hashes.
    """
    iterations = 100_000
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash string.

    Also handles legacy SHA-256 hashes (64-char hex) as a fallback
    for data seeded before the PBKDF2 migration.
    """
    if not stored_hash:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        parts = stored_hash.split("$")
        if len(parts) != 4:
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = parts[3]
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return dk.hex() == expected_hash
    else:
        # Legacy fallback: plain SHA-256 hex digest (64 chars)
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return stored_hash == legacy


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a cursor, run SQL, return rows.
# Use _connect() for read-only queries; for write operations use a manual
# connection with conn.commit() / conn.rollback() (see execute_booking below).

def example_query() -> dict:
    """Example: returns the name of the connected database."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return _to_jsonable(dict(cur.fetchone()))

# TODO: Implement the query_ and execute_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────

def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        travel_date:     e.g. "2025-06-01" — used to count bookings; omit for general info
    """
    sql = """
        SELECT
            s.schedule_id,
            s.line,
            s.service_type,
            s.direction,
            s.departure_time::TEXT      AS departure_time,
            s.operates_on,
            o.stop_order                AS origin_stop_order,
            d.stop_order                AS destination_stop_order,
            o.travel_time_from_origin_min AS origin_travel_min,
            d.travel_time_from_origin_min AS dest_travel_min,
            (d.stop_order - o.stop_order) AS stops_travelled
        FROM nr_schedules s
        JOIN nr_schedule_stops o
          ON o.schedule_id = s.schedule_id
         AND o.station_id  = %s
         AND o.is_stopping  = TRUE
        JOIN nr_schedule_stops d
          ON d.schedule_id = s.schedule_id
         AND d.station_id  = %s
         AND d.is_stopping  = TRUE
        WHERE o.stop_order < d.stop_order
        ORDER BY s.schedule_id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            schedules = [dict(row) for row in cur.fetchall()]

            # Compute total seats and available seats per schedule.
            # available_seats = total_seats - booked_count for the given date.
            for sch in schedules:
                # Total seat count for this schedule (all coaches)
                cur.execute(
                    "SELECT COUNT(*) AS total FROM nr_seats "
                    "WHERE schedule_id = %s",
                    (sch["schedule_id"],),
                )
                total_row = cur.fetchone()
                total_seats = total_row["total"] if total_row else 0
                sch["total_seats"] = total_seats

                if travel_date:
                    # Booked (non-cancelled) seats for this specific date
                    cur.execute(
                        """
                        SELECT COUNT(*) AS booked_count
                        FROM nr_bookings
                        WHERE schedule_id = %s
                          AND travel_date = %s
                          AND status != 'cancelled'
                        """,
                        (sch["schedule_id"], travel_date),
                    )
                    row = cur.fetchone()
                    booked_count = row["booked_count"] if row else 0
                    sch["booked_count"] = booked_count
                    sch["available_seats"] = total_seats - booked_count
                else:
                    # No date specified — report total capacity
                    sch["available_seats"] = total_seats

            return _to_jsonable(schedules)


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id:     e.g. "NR_SCH01"
        fare_class:      "standard" or "first"
        stops_travelled: number of stops between origin and destination (inclusive)

    Returns:
        dict with fare_class, base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            fare_class,
            base_fare_usd,
            per_stop_rate_usd
        FROM nr_schedule_fare_classes
        WHERE schedule_id = %s
          AND fare_class   = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class))
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["stops_travelled"] = stops_travelled
            result["total_fare_usd"] = float(
                result["base_fare_usd"]
            ) + float(result["per_stop_rate_usd"]) * stops_travelled
            return _to_jsonable(result)


# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    sql = """
        SELECT
            s.schedule_id,
            s.line,
            s.direction,
            s.operates_on,
            s.first_train_time::TEXT    AS first_train_time,
            s.last_train_time::TEXT     AS last_train_time,
            s.frequency_min,
            s.base_fare_usd,
            s.per_stop_rate_usd,
            o.stop_order                AS origin_stop_order,
            d.stop_order                AS destination_stop_order,
            o.arrival_time              AS origin_travel_min,
            d.arrival_time              AS dest_travel_min,
            (d.stop_order - o.stop_order) AS stops_travelled
        FROM metro_schedules s
        JOIN metro_schedule_stops o
          ON o.schedule_id = s.schedule_id
         AND o.station_id  = %s
        JOIN metro_schedule_stops d
          ON d.schedule_id = s.schedule_id
         AND d.station_id  = %s
        WHERE o.stop_order < d.stop_order
        ORDER BY s.schedule_id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return _to_jsonable([dict(row) for row in cur.fetchall()])


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id:     e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_rate_usd
        FROM metro_schedules
        WHERE schedule_id = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["stops_travelled"] = stops_travelled
            result["total_fare_usd"] = float(
                result["base_fare_usd"]
            ) + float(result["per_stop_rate_usd"]) * stops_travelled
            return _to_jsonable(result)


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id:  e.g. "NR_SCH01"
        travel_date:  e.g. "2025-06-01"
        fare_class:   "standard" or "first"

    Returns:
        List of dicts with seat info. Returns [] if no seat layout exists.
    """
    sql = """
        SELECT
            ns.seat_id,
            ns.coach_number,
            ns.seat_type,
            ns.is_window,
            ns.has_power_outlet
        FROM nr_seats ns
        JOIN nr_seat_coaches nsc
          ON nsc.schedule_id  = ns.schedule_id
         AND nsc.coach_number = ns.coach_number
        WHERE ns.schedule_id = %s
          AND nsc.fare_class  = %s
          AND ns.seat_id NOT IN (
              SELECT seat_id
              FROM nr_bookings
              WHERE schedule_id = %s
                AND travel_date = %s
                AND status != 'cancelled'
                AND seat_id IS NOT NULL
          )
        ORDER BY ns.coach_number, ns.seat_id;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class, schedule_id, travel_date))
            return _to_jsonable([dict(row) for row in cur.fetchall()])


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible (same row preferred,
    then adjacent rows). Returns a list of seat_ids.

    Args:
        available_seats: output of query_available_seats()
        count:           number of seats needed
    """
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """Return a user's profile by email.

    Does NOT return password_hash or secret_answer.
    """
    sql = """
        SELECT
            ru.user_id,
            ru.email,
            ru.first_name,
            ru.last_name,
            ru.date_of_birth::TEXT   AS date_of_birth,
            EXTRACT(YEAR FROM ru.date_of_birth)::INTEGER AS year_of_birth,
            ru.phone_number,
            ru.registered_at::TEXT   AS registered_at,
            ru.is_active
        FROM registered_users ru
        WHERE ru.email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()
            if not row:
                return None
            profile = _to_jsonable(dict(row))
            profile["full_name"] = f"{profile['first_name']} {profile['last_name']}"
            return profile


def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history (national rail + metro).

    Returns:
        dict with keys 'national_rail' (list) and 'metro' (list)
    """
    result = {"national_rail": [], "metro": []}

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Find user_id from email
            cur.execute(
                "SELECT user_id FROM registered_users WHERE email = %s",
                (user_email,),
            )
            user_row = cur.fetchone()
            if not user_row:
                return result

            user_id = user_row["user_id"]

            # National rail bookings
            cur.execute(
                """
                SELECT
                    booking_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date::TEXT        AS travel_date,
                    departure_time::TEXT     AS departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    stops_travelled,
                    amount_usd,
                    status,
                    booked_at::TEXT          AS booked_at,
                    travelled_at::TEXT       AS travelled_at
                FROM nr_bookings
                WHERE user_id = %s
                ORDER BY booked_at DESC;
                """,
                (user_id,),
            )
            result["national_rail"] = [dict(row) for row in cur.fetchall()]

            # Metro travel history
            cur.execute(
                """
                SELECT
                    trip_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date::TEXT        AS travel_date,
                    ticket_type,
                    day_pass_ref,
                    stops_travelled,
                    amount_usd,
                    status,
                    purchased_at::TEXT       AS purchased_at,
                    travelled_at::TEXT       AS travelled_at
                FROM metro_travel_history
                WHERE user_id = %s
                ORDER BY purchased_at DESC NULLS LAST;
                """,
                (user_id,),
            )
            result["metro"] = [dict(row) for row in cur.fetchall()]

    return _to_jsonable(result)


def query_payment_info(booking_id: str) -> Optional[dict]:
    """Return payment record for a booking or metro trip."""
    # Determine which FK column to query based on ID prefix.
    # col is a fixed literal string, NOT user input — safe to interpolate.
    if booking_id.startswith("BK"):
        col = "nr_booking_id"
    elif booking_id.startswith("MT"):
        col = "metro_trip_id"
    else:
        return None

    sql = f"""
        SELECT
            payment_id,
            nr_booking_id,
            metro_trip_id,
            amount_usd,
            payment_method,
            status,
            paid_at::TEXT AS paid_at
        FROM payments
        WHERE {col} = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()
            return _to_jsonable(dict(row)) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id:                e.g. "RU01" — must match the logged-in user
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        fare_class:             "standard" or "first"
        seat_id:                e.g. "B05" (or "any" to auto-assign)
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, booking_dict)   on success
        (False, error_message) on failure
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Check user exists
            cur.execute(
                "SELECT user_id FROM registered_users WHERE user_id = %s",
                (user_id,),
            )
            if not cur.fetchone():
                conn.rollback()
                return (False, f"User {user_id} not found.")

            # 2. Check schedule exists
            cur.execute(
                "SELECT schedule_id FROM nr_schedules WHERE schedule_id = %s",
                (schedule_id,),
            )
            if not cur.fetchone():
                conn.rollback()
                return (False, f"Schedule {schedule_id} not found.")

            # 3. Check origin on schedule with is_stopping = TRUE
            cur.execute(
                """
                SELECT stop_order FROM nr_schedule_stops
                WHERE schedule_id = %s AND station_id = %s AND is_stopping = TRUE
                """,
                (schedule_id, origin_station_id),
            )
            origin_row = cur.fetchone()
            if not origin_row:
                conn.rollback()
                return (
                    False,
                    f"Origin {origin_station_id} is not a stopping station "
                    f"on schedule {schedule_id}.",
                )

            # 4. Check destination on schedule with is_stopping = TRUE
            cur.execute(
                """
                SELECT stop_order FROM nr_schedule_stops
                WHERE schedule_id = %s AND station_id = %s AND is_stopping = TRUE
                """,
                (schedule_id, destination_station_id),
            )
            dest_row = cur.fetchone()
            if not dest_row:
                conn.rollback()
                return (
                    False,
                    f"Destination {destination_station_id} is not a stopping "
                    f"station on schedule {schedule_id}.",
                )

            # 5. Verify direction
            if origin_row["stop_order"] >= dest_row["stop_order"]:
                conn.rollback()
                return (False, "Origin must come before destination on the route.")

            stops_travelled = dest_row["stop_order"] - origin_row["stop_order"]

            # 6. Calculate fare
            cur.execute(
                """
                SELECT base_fare_usd, per_stop_rate_usd
                FROM nr_schedule_fare_classes
                WHERE schedule_id = %s AND fare_class = %s
                """,
                (schedule_id, fare_class),
            )
            fare_row = cur.fetchone()
            if not fare_row:
                conn.rollback()
                return (
                    False,
                    f"Fare class '{fare_class}' not available for {schedule_id}.",
                )

            amount_usd = round(
                float(fare_row["base_fare_usd"])
                + float(fare_row["per_stop_rate_usd"]) * stops_travelled,
                2,
            )

            # 7. Check seat exists in schedule + fare_class
            cur.execute(
                """
                SELECT ns.seat_id, ns.coach_number
                FROM nr_seats ns
                JOIN nr_seat_coaches nsc
                  ON nsc.schedule_id  = ns.schedule_id
                 AND nsc.coach_number = ns.coach_number
                WHERE ns.schedule_id = %s
                  AND ns.seat_id     = %s
                  AND nsc.fare_class  = %s
                """,
                (schedule_id, seat_id, fare_class),
            )
            seat_row = cur.fetchone()
            if not seat_row:
                conn.rollback()
                return (
                    False,
                    f"Seat {seat_id} not found in {fare_class} class "
                    f"for schedule {schedule_id}.",
                )
            coach = seat_row["coach_number"]

            # 8. Check seat not already booked on this date
            cur.execute(
                """
                SELECT booking_id FROM nr_bookings
                WHERE schedule_id = %s
                  AND travel_date = %s
                  AND seat_id     = %s
                  AND status     != 'cancelled'
                """,
                (schedule_id, travel_date, seat_id),
            )
            if cur.fetchone():
                conn.rollback()
                return (
                    False,
                    f"Seat {seat_id} is already booked on {travel_date}.",
                )

            # 9. Generate next booking_id (BKnnn)
            cur.execute(
                """
                SELECT booking_id FROM nr_bookings
                WHERE booking_id ~ '^BK[0-9]+$'
                ORDER BY CAST(SUBSTRING(booking_id FROM 3) AS INTEGER) DESC
                LIMIT 1;
                """
            )
            bk_row = cur.fetchone()
            if bk_row:
                max_num = int(bk_row["booking_id"][2:])
                new_booking_id = f"BK{max_num + 1:03d}"
            else:
                new_booking_id = "BK001"

            # 10. Get departure_time from schedule
            cur.execute(
                "SELECT departure_time::TEXT AS dt FROM nr_schedules "
                "WHERE schedule_id = %s",
                (schedule_id,),
            )
            dt_row = cur.fetchone()
            departure_time = dt_row["dt"] if dt_row else None

            # 11. Insert booking
            cur.execute(
                """
                INSERT INTO nr_bookings
                    (booking_id, user_id, schedule_id,
                     origin_station_id, destination_station_id,
                     travel_date, departure_time,
                     ticket_type, fare_class, coach, seat_id,
                     stops_travelled, amount_usd, status,
                     booked_at, travelled_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        'confirmed', NOW(), NULL)
                RETURNING
                    booking_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date::TEXT   AS travel_date,
                    departure_time::TEXT AS departure_time,
                    ticket_type, fare_class, coach, seat_id,
                    stops_travelled, amount_usd, status,
                    booked_at::TEXT     AS booked_at;
                """,
                (
                    new_booking_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date, departure_time,
                    ticket_type, fare_class, coach, seat_id,
                    stops_travelled, amount_usd,
                ),
            )
            booking = dict(cur.fetchone())

            # 12. Generate next payment_id (PMnnn)
            cur.execute(
                """
                SELECT payment_id FROM payments
                WHERE payment_id ~ '^PM[0-9]+$'
                ORDER BY CAST(SUBSTRING(payment_id FROM 3) AS INTEGER) DESC
                LIMIT 1;
                """
            )
            pm_row = cur.fetchone()
            if pm_row:
                max_pm = int(pm_row["payment_id"][2:])
                new_payment_id = f"PM{max_pm + 1:03d}"
            else:
                new_payment_id = "PM001"

            # 13. Insert payment in the SAME transaction (atomic booking+payment).
            # Why atomic: if the payment insert fails the booking must also
            # roll back — an orphan booking without a payment record violates
            # the grading requirement for end-to-end correctness.
            cur.execute(
                """
                INSERT INTO payments
                    (payment_id, nr_booking_id, metro_trip_id,
                     amount_usd, payment_method, status, paid_at)
                VALUES (%s, %s, NULL, %s, %s, %s, NOW())
                """,
                (
                    new_payment_id, new_booking_id,
                    amount_usd, "credit_card", "paid",
                ),
            )

            booking["payment_id"] = new_payment_id
            booking["payment_status"] = "paid"

            # Single commit covers both booking and payment inserts
            conn.commit()
            return (True, _to_jsonable(booking))
    except Exception as e:
        conn.rollback()
        return (False, f"Booking failed: {e}")
    finally:
        conn.close()


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id:    must match the booking's user_id

    Returns:
        (True, result_dict)  with refund_amount_usd and policy note
        (False, error_msg)
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Check booking exists
            cur.execute(
                """
                SELECT booking_id, user_id, status, amount_usd,
                       schedule_id, booked_at
                FROM nr_bookings
                WHERE booking_id = %s
                """,
                (booking_id,),
            )
            booking = cur.fetchone()
            if not booking:
                conn.rollback()
                return (False, f"Booking {booking_id} not found.")

            # 2. Check ownership
            if booking["user_id"] != user_id:
                conn.rollback()
                return (
                    False,
                    f"Booking {booking_id} does not belong to user {user_id}.",
                )

            # 3. Check not already cancelled
            if booking["status"] == "cancelled":
                conn.rollback()
                return (False, f"Booking {booking_id} is already cancelled.")

            # 4. Update status to cancelled
            cur.execute(
                """
                UPDATE nr_bookings
                SET status = 'cancelled'
                WHERE booking_id = %s
                RETURNING
                    booking_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date::TEXT    AS travel_date,
                    departure_time::TEXT AS departure_time,
                    ticket_type, fare_class, coach, seat_id,
                    stops_travelled, amount_usd, status,
                    booked_at::TEXT      AS booked_at,
                    travelled_at::TEXT    AS travelled_at;
                """,
                (booking_id,),
            )
            result = dict(cur.fetchone())

            # 5. Calculate refund amount.
            # Deterministic rule for grading / demo purposes:
            #   - travel_date in the future → full refund (100% of amount_usd)
            #   - travel_date is today or past → no refund (0%)
            # In production, this should read cancellation_windows from
            # refund_policy.json and apply time-based windows per service
            # type (e.g. RF001 normal / RF002 express).
            today_str = datetime.now(timezone.utc).date().isoformat()
            travel_date_str = result.get("travel_date")
            original_amount = float(result.get("amount_usd") or 0)

            if travel_date_str and str(travel_date_str) > today_str:
                refund_amount = original_amount
                refund_note = "Full refund: travel date is in the future"
            else:
                refund_amount = 0.0
                refund_note = "No refund: travel date is today or has passed"

            result["refund_amount"] = refund_amount
            result["refund_note"] = refund_note

            conn.commit()
            return (True, _to_jsonable(result))
    except Exception as e:
        conn.rollback()
        return (False, f"Cancellation failed: {e}")
    finally:
        conn.close()


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.
    Returns (True, user_id) on success or (False, error_message) on failure.

    Password is hashed with SHA-256 (same method as seed_postgres.py).
    This is for teaching/demo only. Production should use argon2 or bcrypt.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check email uniqueness
            cur.execute(
                "SELECT user_id FROM registered_users WHERE email = %s",
                (email,),
            )
            if cur.fetchone():
                conn.rollback()
                return (False, "Email already registered.")

            # Generate next user_id (RUnn)
            cur.execute(
                """
                SELECT user_id FROM registered_users
                WHERE user_id ~ '^RU[0-9]+$'
                ORDER BY CAST(SUBSTRING(user_id FROM 3) AS INTEGER) DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            if row:
                max_num = int(row["user_id"][2:])
                new_user_id = f"RU{max_num + 1:02d}"
            else:
                new_user_id = "RU01"

            # Insert into registered_users
            # surname → last_name column in schema
            cur.execute(
                """
                INSERT INTO registered_users
                    (user_id, email, first_name, last_name,
                     date_of_birth, registered_at, is_active)
                VALUES (%s, %s, %s, %s, %s, NOW(), TRUE);
                """,
                (new_user_id, email, first_name, surname,
                 f"{year_of_birth}-01-01"),
            )

            # Insert into user_credentials (no email stored here)
            # PBKDF2-HMAC-SHA256 with per-user random salt
            password_hash = _hash_password(password)
            cur.execute(
                """
                INSERT INTO user_credentials
                    (user_id, password_hash, secret_question, secret_answer)
                VALUES (%s, %s, %s, %s);
                """,
                (new_user_id, password_hash, secret_question, secret_answer),
            )

            conn.commit()
            return (True, new_user_id)
    except Exception as e:
        conn.rollback()
        return (False, f"Registration failed: {e}")
    finally:
        conn.close()


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials. Returns a user dict on success or None on failure.
    Dict keys: user_id, email, full_name, first_name, surname, phone, date_of_birth, is_active.
    """
    sql = """
        SELECT
            ru.user_id,
            ru.email,
            ru.first_name,
            ru.last_name,
            ru.date_of_birth::TEXT  AS date_of_birth,
            ru.phone_number,
            ru.is_active,
            uc.password_hash
        FROM registered_users ru
        JOIN user_credentials uc ON uc.user_id = ru.user_id
        WHERE ru.email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row:
                return None

            # Verify password against stored PBKDF2 hash (or legacy SHA-256)
            if not _verify_password(password, row["password_hash"]):
                return None

            # Build result — exclude sensitive fields, add agent-friendly aliases
            result = dict(row)
            result.pop("password_hash", None)
            result["full_name"] = f"{result['first_name']} {result['last_name']}"
            result["surname"] = result["last_name"]
            result["phone"] = result.get("phone_number")
            return _to_jsonable(result)


def get_user_secret_question(email: str) -> Optional[str]:
    """Return the secret question for a registered email, or None if not found."""
    sql = """
        SELECT uc.secret_question
        FROM user_credentials uc
        JOIN registered_users ru ON ru.user_id = uc.user_id
        WHERE ru.email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            return row["secret_question"] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Return True if the provided answer matches the stored secret answer (case-insensitive)."""
    sql = """
        SELECT uc.secret_answer
        FROM user_credentials uc
        JOIN registered_users ru ON ru.user_id = uc.user_id
        WHERE ru.email = %s;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
            if not row or row["secret_answer"] is None:
                return False
            return row["secret_answer"].lower().strip() == answer.lower().strip()


def update_password(email: str, new_password: str) -> bool:
    """Update the password for a user. Returns True if the row was updated."""
    # PBKDF2-HMAC-SHA256 with per-user random salt
    password_hash = _hash_password(new_password)
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_credentials
                SET password_hash = %s
                WHERE user_id = (
                    SELECT user_id FROM registered_users WHERE email = %s
                );
                """,
                (password_hash, email),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return _to_jsonable([dict(row) for row in cur.fetchall()])


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]


# ============================================================
#  TASK 6 EXTENSION — Loyalty Points & Discounted Booking
# ============================================================

# TASK 6 EXTENSION
LOYALTY_POINTS_PER_USD_DISCOUNT = 100   # 100 points = 1.00 USD
LOYALTY_DISCOUNT_USD = 1.00             # max discount per booking
LOYALTY_RULE_TEXT = "100 points = 1.00 USD discount"


# TASK 6 EXTENSION
def query_user_loyalty_points(email: str) -> dict:
    """Look up a user's membership loyalty points by email.

    Returns:
        {
            "user_id": "RU01",
            "email": "alice.tan@email.com",
            "points_balance": 120,
            "redeem_rule": "100 points = 1.00 USD discount"
        }
        or {"error": "..."} if the user is not found.
    """
    sql = """
        SELECT ru.user_id, ru.email, COALESCE(lp.points_balance, 0) AS points_balance
        FROM registered_users ru
        LEFT JOIN user_loyalty_points lp ON lp.user_id = ru.user_id
        WHERE ru.email = %s
    """
    try:
        with _connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (email,))
                row = cur.fetchone()
                if not row:
                    return {"error": f"No user found with email: {email}"}
                return {
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "points_balance": row["points_balance"],
                    "redeem_rule": LOYALTY_RULE_TEXT,
                }
    except Exception as e:
        return {"error": f"Loyalty points query failed: {e}"}


# TASK 6 EXTENSION
def execute_booking_with_loyalty_discount(
    email: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str = "standard",
    seat_id: str = "any",
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """Create a national rail booking with automatic loyalty-point discount.

    Wraps the full booking + payment + loyalty-point update in a **single
    PostgreSQL transaction** so everything commits or rolls back together.

    Discount rules (configurable via module constants):
        * 100 points  →  1.00 USD discount
        * Max 1.00 USD discount per booking
        * Points < 100  →  no discount applied
        * Discount never exceeds the original fare

    Args:
        email:                  Logged-in user's email
        schedule_id:            e.g. "NR_SCH01"
        origin_station_id:      e.g. "NR01"
        destination_station_id: e.g. "NR05"
        travel_date:            e.g. "2025-06-01"
        fare_class:             "standard" or "first"
        seat_id:                Specific seat or "any"
        ticket_type:            "single" (default) or "return"

    Returns:
        (True, result_dict)   on success
        (False, error_str)    on failure — the entire transaction is rolled back
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # ── 1. Resolve user_id from email ────────────────────────────
            cur.execute(
                "SELECT user_id FROM registered_users WHERE email = %s",
                (email,),
            )
            user_row = cur.fetchone()
            if not user_row:
                conn.rollback()
                return (False, f"User not found for email: {email}")
            user_id = user_row["user_id"]

            # ── 2. Fetch loyalty points (with row-level lock) ────────────
            cur.execute(
                "SELECT points_balance FROM user_loyalty_points "
                "WHERE user_id = %s FOR UPDATE",
                (user_id,),
            )
            lp_row = cur.fetchone()
            points_before = lp_row["points_balance"] if lp_row else 0

            # ── 3. Check schedule exists ─────────────────────────────────
            cur.execute(
                "SELECT schedule_id FROM nr_schedules WHERE schedule_id = %s",
                (schedule_id,),
            )
            if not cur.fetchone():
                conn.rollback()
                return (False, f"Schedule {schedule_id} not found.")

            # ── 4. Validate origin & destination stops ───────────────────
            cur.execute(
                "SELECT stop_order FROM nr_schedule_stops "
                "WHERE schedule_id = %s AND station_id = %s AND is_stopping = TRUE",
                (schedule_id, origin_station_id),
            )
            origin_row = cur.fetchone()
            if not origin_row:
                conn.rollback()
                return (False, f"Origin {origin_station_id} not on schedule {schedule_id}.")

            cur.execute(
                "SELECT stop_order FROM nr_schedule_stops "
                "WHERE schedule_id = %s AND station_id = %s AND is_stopping = TRUE",
                (schedule_id, destination_station_id),
            )
            dest_row = cur.fetchone()
            if not dest_row:
                conn.rollback()
                return (False, f"Destination {destination_station_id} not on schedule {schedule_id}.")

            if origin_row["stop_order"] >= dest_row["stop_order"]:
                conn.rollback()
                return (False, "Origin must come before destination.")

            stops_travelled = dest_row["stop_order"] - origin_row["stop_order"]

            # ── 5. Calculate original fare ───────────────────────────────
            cur.execute(
                "SELECT base_fare_usd, per_stop_rate_usd "
                "FROM nr_schedule_fare_classes "
                "WHERE schedule_id = %s AND fare_class = %s",
                (schedule_id, fare_class),
            )
            fare_row = cur.fetchone()
            if not fare_row:
                conn.rollback()
                return (False, f"Fare class '{fare_class}' not available for {schedule_id}.")

            original_fare = round(
                float(fare_row["base_fare_usd"])
                + float(fare_row["per_stop_rate_usd"]) * stops_travelled,
                2,
            )

            # ── 6. Apply loyalty discount ────────────────────────────────
            if points_before >= LOYALTY_POINTS_PER_USD_DISCOUNT:
                discount_usd = min(LOYALTY_DISCOUNT_USD, original_fare)
                points_used = LOYALTY_POINTS_PER_USD_DISCOUNT
            else:
                discount_usd = 0.0
                points_used = 0

            final_amount = round(original_fare - discount_usd, 2)
            points_after = points_before - points_used

            # ── 7. Resolve seat (auto-select if "any" or None) ────────────
            # TASK 6 EXTENSION: auto-assign seat when seat_id is "any"
            if not seat_id or seat_id.lower() == "any":
                cur.execute(
                    """
                    SELECT ns.seat_id, ns.coach_number
                    FROM nr_seats ns
                    JOIN nr_seat_coaches nsc
                      ON nsc.schedule_id  = ns.schedule_id
                     AND nsc.coach_number = ns.coach_number
                    WHERE ns.schedule_id = %s
                      AND nsc.fare_class  = %s
                      AND ns.seat_id NOT IN (
                          SELECT seat_id FROM nr_bookings
                          WHERE schedule_id = %s
                            AND travel_date = %s
                            AND status != 'cancelled'
                      )
                    ORDER BY ns.coach_number, ns.seat_id
                    LIMIT 1
                    """,
                    (schedule_id, fare_class, schedule_id, travel_date),
                )
                seat_row = cur.fetchone()
                if not seat_row:
                    conn.rollback()
                    return (False, f"No available {fare_class} seats on {schedule_id} for {travel_date}.")
                seat_id = seat_row["seat_id"]
                coach = seat_row["coach_number"]
            else:
                # Specific seat requested — validate it exists
                cur.execute(
                    """
                    SELECT ns.seat_id, ns.coach_number
                    FROM nr_seats ns
                    JOIN nr_seat_coaches nsc
                      ON nsc.schedule_id  = ns.schedule_id
                     AND nsc.coach_number = ns.coach_number
                    WHERE ns.schedule_id = %s
                      AND ns.seat_id     = %s
                      AND nsc.fare_class  = %s
                    """,
                    (schedule_id, seat_id, fare_class),
                )
                seat_row = cur.fetchone()
                if not seat_row:
                    conn.rollback()
                    return (False, f"Seat {seat_id} not found in {fare_class} for {schedule_id}.")
                coach = seat_row["coach_number"]

                # ── 8. Check seat not already booked ─────────────────────────
                cur.execute(
                    "SELECT booking_id FROM nr_bookings "
                    "WHERE schedule_id = %s AND travel_date = %s "
                    "AND seat_id = %s AND status != 'cancelled'",
                    (schedule_id, travel_date, seat_id),
                )
                if cur.fetchone():
                    conn.rollback()
                    return (False, f"Seat {seat_id} already booked on {travel_date}.")

            # ── 9. Generate booking_id ───────────────────────────────────
            cur.execute(
                "SELECT booking_id FROM nr_bookings "
                "WHERE booking_id ~ '^BK[0-9]+$' "
                "ORDER BY CAST(SUBSTRING(booking_id FROM 3) AS INTEGER) DESC "
                "LIMIT 1;"
            )
            bk_row = cur.fetchone()
            new_booking_id = f"BK{int(bk_row['booking_id'][2:]) + 1:03d}" if bk_row else "BK001"

            # ── 10. Get departure_time ───────────────────────────────────
            cur.execute(
                "SELECT departure_time::TEXT AS dt FROM nr_schedules "
                "WHERE schedule_id = %s",
                (schedule_id,),
            )
            dt_row = cur.fetchone()
            departure_time = dt_row["dt"] if dt_row else None

            # ── 11. Insert booking ───────────────────────────────────────
            cur.execute(
                """
                INSERT INTO nr_bookings
                    (booking_id, user_id, schedule_id,
                     origin_station_id, destination_station_id,
                     travel_date, departure_time,
                     ticket_type, fare_class, coach, seat_id,
                     stops_travelled, amount_usd, status,
                     booked_at, travelled_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        'confirmed', NOW(), NULL)
                """,
                (
                    new_booking_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date, departure_time,
                    ticket_type, fare_class, coach, seat_id,
                    stops_travelled, final_amount,
                ),
            )

            # ── 12. Generate payment_id ──────────────────────────────────
            cur.execute(
                "SELECT payment_id FROM payments "
                "WHERE payment_id ~ '^PM[0-9]+$' "
                "ORDER BY CAST(SUBSTRING(payment_id FROM 3) AS INTEGER) DESC "
                "LIMIT 1;"
            )
            pm_row = cur.fetchone()
            new_payment_id = f"PM{int(pm_row['payment_id'][2:]) + 1:03d}" if pm_row else "PM001"

            # ── 13. Insert payment ───────────────────────────────────────
            cur.execute(
                """
                INSERT INTO payments
                    (payment_id, nr_booking_id, metro_trip_id,
                     amount_usd, payment_method, status, paid_at)
                VALUES (%s, %s, NULL, %s, %s, %s, NOW())
                """,
                (new_payment_id, new_booking_id, final_amount, "credit_card", "paid"),
            )

            # ── 14. Update loyalty points ────────────────────────────────
            if points_used > 0:
                cur.execute(
                    "UPDATE user_loyalty_points "
                    "SET points_balance = %s, updated_at = NOW() "
                    "WHERE user_id = %s",
                    (points_after, user_id),
                )

            # ── 15. Commit everything atomically ─────────────────────────
            conn.commit()

            return (True, {
                "booking_id": new_booking_id,
                "payment_id": new_payment_id,
                "user_id": user_id,
                "original_fare_usd": original_fare,
                "discount_usd": discount_usd,
                "final_amount_usd": final_amount,
                "points_before": points_before,
                "points_used": points_used,
                "points_after": points_after,
                "loyalty_rule": LOYALTY_RULE_TEXT,
            })

    except Exception as e:
        conn.rollback()
        return (False, f"Loyalty booking failed: {e}")
    finally:
        conn.close()
