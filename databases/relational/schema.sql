-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data (designed below)
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ────────────────────────────────────────────────────────────────
-- PK DESIGN DECISION:
-- All tables use VARCHAR business keys (e.g. RU01, MS01, NR01, BK001)
-- rather than UUID or SERIAL.
-- Rationale:
--   1. Mock-data JSON files and Neo4j graph use these IDs directly —
--      a stable business key avoids an extra mapping layer across DBs.
--   2. Human-readable IDs simplify debugging and grading demos.
--   3. For a single-region teaching project, the join-performance
--      advantage of SERIAL/BIGINT is negligible.
-- Production recommendation: UUID v7 or BIGSERIAL for scalability.
-- ────────────────────────────────────────────────────────────────
-- DELETE STRATEGY:
-- Bookings use SOFT CANCELLATION (status = 'cancelled') — rows are
-- never physically deleted.  This preserves full audit history and
-- allows accurate refund tracking.  Other reference tables (stations,
-- schedules, users) hold immutable seed data and are never removed.
-- ────────────────────────────────────────────────────────────────
-- FK CASCADE POLICY:
-- All foreign keys use PostgreSQL default NO ACTION (equivalent to
-- RESTRICT at transaction end).  Parent-row deletion is controlled
-- entirely at the application layer: the app checks references and
-- performs soft cancellation before any removal.  In production,
-- explicit ON DELETE RESTRICT or SET NULL would be specified per FK.
-- ────────────────────────────────────────────────────────────────


-- ============================================================
--  1. USERS
-- ============================================================

-- Registered User profile data
CREATE TABLE registered_users (
    user_id        VARCHAR(20)  PRIMARY KEY,
    email          VARCHAR(100) NOT NULL UNIQUE,
    first_name     VARCHAR(50)  NOT NULL,
    last_name      VARCHAR(50)  NOT NULL,
    date_of_birth  DATE,
    phone_number   VARCHAR(30),
    registered_at  TIMESTAMPTZ  DEFAULT NOW(),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE
);

-- User credentials for authentication (excludes email to avoid duplication, references registered_users)
CREATE TABLE user_credentials (
    user_id         VARCHAR(20) PRIMARY KEY
                    REFERENCES registered_users(user_id),
    -- PBKDF2-HMAC-SHA256 hash with per-user random salt.
    -- Format: pbkdf2_sha256$iterations$salt_hex$hash_hex
    -- Why: key stretching (100k rounds) + unique salt per user prevents
    -- both brute-force and rainbow-table attacks, unlike plain SHA-256.
    password_hash   TEXT        NOT NULL,
    secret_question TEXT,
    secret_answer   TEXT
);


-- ============================================================
--  2. STATIONS
-- ============================================================

-- Metro station basic information
CREATE TABLE metro_stations (
    station_id  VARCHAR(20)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    zone        VARCHAR(20)
);

-- Lines associated with metro stations (one station can belong to multiple lines)
CREATE TABLE metro_station_lines (
    station_id  VARCHAR(20) NOT NULL
                REFERENCES metro_stations(station_id),
    line_name   VARCHAR(20) NOT NULL,
    PRIMARY KEY (station_id, line_name)
);

-- National rail station basic information
CREATE TABLE national_rail_stations (
    station_id  VARCHAR(20)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    zone        VARCHAR(20)
);

-- Lines associated with national rail stations (one station can belong to multiple lines)
CREATE TABLE nr_station_lines (
    station_id  VARCHAR(20) NOT NULL
                REFERENCES national_rail_stations(station_id),
    line_name   VARCHAR(20) NOT NULL,
    PRIMARY KEY (station_id, line_name)
);


-- ============================================================
--  3. SCHEDULES / TIMETABLE
-- ============================================================

-- Metro schedules master table
CREATE TABLE metro_schedules (
    schedule_id     VARCHAR(30) PRIMARY KEY,
    line            VARCHAR(20) NOT NULL,
    direction       VARCHAR(30),
    operates_on     TEXT[]      NOT NULL,
    origin_station_id      VARCHAR(20),
    destination_station_id VARCHAR(20),
    first_train_time       TIME,
    last_train_time        TIME,
    frequency_min          INTEGER,
    base_fare_usd          NUMERIC(8,2),
    per_stop_rate_usd      NUMERIC(8,2)
);

-- Stops and sequence order associated with metro schedules
CREATE TABLE metro_schedule_stops (
    schedule_id  VARCHAR(30) NOT NULL
                 REFERENCES metro_schedules(schedule_id),
    stop_order   INTEGER     NOT NULL,
    station_id   VARCHAR(20) NOT NULL
                 REFERENCES metro_stations(station_id),
    arrival_time INTEGER,                       -- travel_time_from_origin_min
    PRIMARY KEY (schedule_id, stop_order)
);

-- National rail schedules master table
CREATE TABLE nr_schedules (
    schedule_id     VARCHAR(30) PRIMARY KEY,
    line            VARCHAR(20),
    service_type    VARCHAR(30),
    direction       VARCHAR(30),
    departure_time  TIME,
    operates_on     TEXT[]      NOT NULL,
    origin_station_id      VARCHAR(20),
    destination_station_id VARCHAR(20),
    first_train_time       TIME,
    last_train_time        TIME,
    frequency_min          INTEGER
);

-- Stops and sequence order associated with national rail schedules
CREATE TABLE nr_schedule_stops (
    schedule_id               VARCHAR(30) NOT NULL
                              REFERENCES nr_schedules(schedule_id),
    stop_order                INTEGER     NOT NULL,
    station_id                VARCHAR(20) NOT NULL
                              REFERENCES national_rail_stations(station_id),
    travel_time_from_origin_min INTEGER,          -- NULL when is_stopping = FALSE
    is_stopping               BOOLEAN     NOT NULL DEFAULT TRUE,
    PRIMARY KEY (schedule_id, stop_order)
);

-- Fare classes and rates for national rail schedules
CREATE TABLE nr_schedule_fare_classes (
    schedule_id      VARCHAR(30)  NOT NULL
                     REFERENCES nr_schedules(schedule_id),
    fare_class       VARCHAR(30)  NOT NULL,
    base_fare_usd    NUMERIC(8,2) NOT NULL,
    per_stop_rate_usd NUMERIC(8,2) NOT NULL,
    PRIMARY KEY (schedule_id, fare_class)
);


-- ============================================================
--  4. SEATS
-- ============================================================

-- Seat coaches assigned to national rail schedules
CREATE TABLE nr_seat_coaches (
    schedule_id   VARCHAR(30) NOT NULL
                  REFERENCES nr_schedules(schedule_id),
    coach_number  VARCHAR(10) NOT NULL,
    fare_class    VARCHAR(30),
    PRIMARY KEY (schedule_id, coach_number)
);

-- Seat configuration mapping for national rail schedules
CREATE TABLE nr_seats (
    schedule_id      VARCHAR(30) NOT NULL,
    seat_id          VARCHAR(20) NOT NULL,
    coach_number     VARCHAR(10),
    seat_type        VARCHAR(30),
    is_window        BOOLEAN,
    has_power_outlet BOOLEAN,
    PRIMARY KEY (schedule_id, seat_id)
);


-- ============================================================
--  5. BOOKINGS / TRAVEL HISTORY
-- ============================================================

-- Booking records for national rail journeys
CREATE TABLE nr_bookings (
    booking_id            VARCHAR(30) PRIMARY KEY,
    user_id               VARCHAR(20) NOT NULL
                          REFERENCES registered_users(user_id),
    schedule_id           VARCHAR(30) NOT NULL
                          REFERENCES nr_schedules(schedule_id),
    origin_station_id     VARCHAR(20),
    destination_station_id VARCHAR(20),
    travel_date           DATE,
    departure_time        TIME,
    ticket_type           VARCHAR(30),
    fare_class            VARCHAR(30),
    coach                 VARCHAR(10),
    seat_id               VARCHAR(20),
    stops_travelled       INTEGER,
    amount_usd            NUMERIC(10,2),
    status                VARCHAR(30)  NOT NULL DEFAULT 'confirmed',
    booked_at             TIMESTAMPTZ  DEFAULT NOW(),
    travelled_at          TIMESTAMPTZ
);

-- Journey and travel history for metro trips
CREATE TABLE metro_travel_history (
    trip_id               VARCHAR(30) PRIMARY KEY,
    user_id               VARCHAR(20) NOT NULL
                          REFERENCES registered_users(user_id),
    schedule_id           VARCHAR(30),
    origin_station_id     VARCHAR(20),
    destination_station_id VARCHAR(20),
    travel_date           DATE,
    ticket_type           VARCHAR(30),
    day_pass_ref          VARCHAR(30),
    stops_travelled       INTEGER,
    amount_usd            NUMERIC(10,2),      -- nullable per context
    status                VARCHAR(30),
    purchased_at          TIMESTAMPTZ,        -- nullable per context
    travelled_at          TIMESTAMPTZ
);


-- ============================================================
--  6. PAYMENTS
-- ============================================================

CREATE TABLE payments (
    payment_id      VARCHAR(30) PRIMARY KEY,
    nr_booking_id   VARCHAR(30)
                    REFERENCES nr_bookings(booking_id),
    metro_trip_id   VARCHAR(30)
                    REFERENCES metro_travel_history(trip_id),
    amount_usd      NUMERIC(10,2) NOT NULL,
    payment_method  VARCHAR(30)   NOT NULL,
    status          VARCHAR(30)   NOT NULL DEFAULT 'paid',
    paid_at         TIMESTAMPTZ   DEFAULT NOW(),

    -- Exactly one foreign key must be non-null (XOR constraint)
    CONSTRAINT chk_payments_exclusive_fk CHECK (
        (nr_booking_id IS NOT NULL AND metro_trip_id IS NULL) OR
        (nr_booking_id IS NULL     AND metro_trip_id IS NOT NULL)
    )
);


-- ============================================================
--  7. FEEDBACK
-- ============================================================

CREATE TABLE feedback (
    feedback_id     VARCHAR(30) PRIMARY KEY,
    nr_booking_id   VARCHAR(30)
                    REFERENCES nr_bookings(booking_id),
    metro_trip_id   VARCHAR(30)
                    REFERENCES metro_travel_history(trip_id),
    user_id         VARCHAR(20)
                    REFERENCES registered_users(user_id),
    rating          INTEGER     CHECK (rating >= 1 AND rating <= 5),
    comment         TEXT,
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),

    -- Exactly one foreign key must be non-null (XOR constraint)
    CONSTRAINT chk_feedback_exclusive_fk CHECK (
        (nr_booking_id IS NOT NULL AND metro_trip_id IS NULL) OR
        (nr_booking_id IS NULL     AND metro_trip_id IS NOT NULL)
    )
);


-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
