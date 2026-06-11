# 2. Normalisation Justification

## 2.1 Overview

The TransitFlow PostgreSQL schema is designed to be **predominantly normalised**, targeting Third Normal Form (3NF) across all core operational tables. Normalisation reduces data redundancy, prevents update anomalies, and preserves referential consistency — properties that are especially important for a system where **booking, payment, and loyalty point operations must remain transactionally consistent**.

The schema separates concerns into dedicated tables for:

- **User identity** (`registered_users`) and **authentication** (`user_credentials`)
- **Station topology** (`metro_stations`, `metro_station_lines`, `national_rail_stations`, `nr_station_lines`)
- **Schedules and stops** (`metro_schedules`, `metro_schedule_stops`, `nr_schedules`, `nr_schedule_stops`)
- **Fare pricing** (`nr_schedule_fare_classes`)
- **Seat layout** (`nr_seat_coaches`, `nr_seats`)
- **Bookings and travel history** (`nr_bookings`, `metro_travel_history`)
- **Payments** (`payments`) and **feedback** (`feedback`)
- **Policy knowledge base** (`policy_documents`) with vector embeddings for RAG
- **Task 6 loyalty extension** (`user_loyalty_points`)

A small number of controlled de-normalisation trade-offs exist for seed data reproducibility, query simplicity, and auditability. These are discussed in detail in Section 2.5.

## 2.2 First Normal Form (1NF): Atomic Values and Repeating Groups

First Normal Form requires that every column contains **atomic (indivisible) values** and that there are no **repeating groups** — that is, no sets of related attributes repeated within a single row.

### Elimination of Repeating Groups

The TransitFlow schema eliminates repeating groups by decomposing multi-valued relationships into dedicated child tables:

- **Schedule stops**: Rather than storing the list of stops as a comma-separated string or JSON array inside `metro_schedules` or `nr_schedules`, each stop is stored as an individual row in `metro_schedule_stops` or `nr_schedule_stops`. Each row carries its own `station_id`, `stop_order`, and timing offset (`arrival_time` or `travel_time_from_origin_min`). This ensures every value is atomic and individually queryable — for example, finding all schedules that pass through a specific station requires a simple `WHERE station_id = %s` rather than parsing an embedded array.

- **Station-line mappings**: Rather than storing multiple line names inside a single station row (which would create a repeating group), the schema uses `metro_station_lines` and `nr_station_lines` with composite primary key `(station_id, line_name)`. Each row maps exactly one station to exactly one line. This supports stations that belong to multiple lines — for example, Central Square (MS01) belongs to both M1 and M2 — without duplicating station attributes.

### Controlled Exception: `operates_on` Array

Both `metro_schedules` and `nr_schedules` store `operates_on` as a PostgreSQL `TEXT[]` array (e.g. `{'Monday', 'Tuesday', 'Wednesday'}`). This is a **deliberate, controlled deviation** from strict 1NF. The fully normalised alternative would be a separate `schedule_operating_days` table with one row per schedule per day of the week. However, operating days are:

- A small, fixed domain (at most 7 values from a closed set of weekday names).
- Rarely queried independently — the primary access pattern is to retrieve the full operating day list alongside other schedule metadata.
- Never the target of individual updates — a schedule either operates on a given day or it does not, and changes affect the entire list atomically.

Given these characteristics, the `TEXT[]` representation simplifies seeding, schedule retrieval queries, and agent display without creating meaningful redundancy or update anomaly risk. Crucially, the main operational repeating groups — such as schedule stops and station-line mappings — are still fully normalised into separate child tables. This trade-off is discussed further in Section 2.5.

## 2.3 Second Normal Form (2NF): Avoiding Partial Dependencies

Second Normal Form requires that the schema is in 1NF **and** every non-key attribute depends on the **entire** primary key, not just a part of it. Partial dependencies arise when a table has a composite primary key and some attributes depend on only a subset of that key.

### Example 1: Schedule Stops (`metro_schedule_stops`, `nr_schedule_stops`)

The `nr_schedule_stops` table has composite primary key `(schedule_id, stop_order)`. Its non-key attributes are:

- `station_id` — which specific station is at this position in the route
- `travel_time_from_origin_min` — cumulative travel time to this stop
- `is_stopping` — whether the train stops here (relevant for express services)

**Functional dependency:**

```
(schedule_id, stop_order) → station_id, travel_time_from_origin_min, is_stopping
```

Each of these attributes depends on the **full composite key**. The station at stop position 3 on schedule NR_SCH01 may be different from the station at stop position 3 on NR_SCH05. Similarly, the travel time depends on both which schedule and which position in the route. Neither `station_id` nor `travel_time_from_origin_min` can be determined from `schedule_id` alone or `stop_order` alone.

Meanwhile, schedule-level attributes such as `line`, `direction`, `service_type`, and `departure_time` depend only on `schedule_id`:

```
schedule_id → line, direction, service_type, departure_time, operates_on
```

These attributes are correctly stored in the `nr_schedules` master table, **not** repeated in `nr_schedule_stops`. If `line` or `direction` were stored in the stops table, they would create a partial dependency — `line` would depend on `schedule_id` alone, not on the full composite key `(schedule_id, stop_order)`. The current design avoids this violation.

The same reasoning applies to `metro_schedule_stops` with composite key `(schedule_id, stop_order)` and functional dependency:

```
(schedule_id, stop_order) → station_id, arrival_time
```

### Example 2: National Rail Fare Classes (`nr_schedule_fare_classes`)

The `nr_schedule_fare_classes` table has composite primary key `(schedule_id, fare_class)`. Its non-key attributes are:

- `base_fare_usd` — the base fare for this schedule and class combination
- `per_stop_rate_usd` — the per-stop surcharge for this combination

**Functional dependency:**

```
(schedule_id, fare_class) → base_fare_usd, per_stop_rate_usd
```

The fare rate depends on **both** the schedule and the fare class. Schedule NR_SCH01 (normal service) has standard rates of $2.50 base + $1.50/stop and first-class rates of $4.00 base + $2.50/stop — different values for different `fare_class` values on the same schedule. Neither `base_fare_usd` nor `per_stop_rate_usd` can be determined from `schedule_id` alone.

Storing these fare attributes directly in `nr_schedules` (which has a single-column key `schedule_id`) would create ambiguity: which fare class's rate would be stored? Storing them in `nr_bookings` would duplicate master fare data across every booking row. The current `nr_schedule_fare_classes` table correctly places fare attributes where they depend on the full composite key.

### Example 3: Station-Line Mapping (`metro_station_lines`, `nr_station_lines`)

The `metro_station_lines` table has composite primary key `(station_id, line_name)`. This table has no non-key attributes beyond the key columns themselves — it is a pure **junction table** representing the many-to-many relationship between stations and lines. By definition, a table with only key attributes satisfies 2NF trivially, because there are no non-key attributes that could exhibit partial dependency.

The design choice to use a junction table rather than storing multiple lines as a repeating group inside `metro_stations` satisfies both 1NF (no repeating groups) and enables 2NF compliance for any future non-key attributes that might be added to the mapping (e.g. platform number or line ordering).

### Candidate Keys

Several tables have candidate keys beyond their designated primary key:

- **`registered_users`**: The primary key is `user_id`, but `email` is also a candidate key due to its `UNIQUE` constraint. The functional dependency `email → user_id, first_name, last_name, phone_number, ...` holds, meaning `email` could serve as an alternative primary key. The schema designates `user_id` as the primary key because it is used as a foreign key reference across multiple tables (`nr_bookings`, `metro_travel_history`, `feedback`, `user_credentials`, `user_loyalty_points`), and a short VARCHAR business key (`RU01`) is more efficient for joins than a longer email string.

## 2.4 Third Normal Form (3NF): Avoiding Transitive Dependencies

Third Normal Form requires that the schema is in 2NF **and** no non-key attribute depends transitively on the primary key through another non-key attribute. In other words, every non-key attribute must depend **directly** on the primary key, not on some intermediate non-key attribute.

A **transitive dependency** occurs when:

```
A → B → C
```

where `A` is the primary key, `B` is a non-key attribute, and `C` is another non-key attribute that depends on `B` rather than directly on `A`. To achieve 3NF, `B → C` should be extracted into a separate table with `B` as its primary key.

### Example 1: Separation of `user_credentials` from `registered_users`

The `registered_users` table stores user profile data:

```
user_id → email, first_name, last_name, date_of_birth, phone_number, registered_at, is_active
```

The `user_credentials` table stores authentication data:

```
user_id → password_hash, secret_question, secret_answer
```

While storing `password_hash` directly in `registered_users` would technically satisfy 3NF (as it depends directly on `user_id` without transitive dependency), this separation is primarily a **security, access-control, and single-responsibility** design decision. Credential attributes are semantically distinct from profile attributes and are accessed under entirely different circumstances. The 1:1 split keeps each table cohesive, ensures that frequent profile queries do not unnecessarily touch sensitive credential columns, and prevents password updates from locking profile rows. This approach strongly supports a normalised and cohesive schema structure.

### Example 2: Separation of `payments` from `nr_bookings` and `metro_travel_history`

Payment attributes (`payment_method`, `status`, `paid_at`) depend on `payment_id`:

```
payment_id → nr_booking_id | metro_trip_id, amount_usd, payment_method, status, paid_at
```

If these were stored inside `nr_bookings`, a transitive dependency would emerge:

```
booking_id → payment_id → payment_method, payment_status, paid_at
```

Here, `payment_method` depends on `payment_id` (the payment entity's identity), not directly on `booking_id` (the booking entity's identity). This is a classic transitive dependency through the non-key attribute `payment_id`.

By separating `payments` into its own table, the schema:
- Eliminates the transitive dependency.
- Allows booking status (`confirmed` / `cancelled`) and payment status (`paid` / `refunded`) to evolve independently.
- Enables the exclusive-OR CHECK constraint (`chk_payments_exclusive_fk`) that ensures each payment links to exactly one booking type (national rail or metro), which would be impossible if payment data were embedded in both booking tables.

### Example 3: Separation of `user_loyalty_points` from `registered_users` (Task 6)

The Task 6 extension stores loyalty point balances in a dedicated table:

```
user_id → points_balance, updated_at
```

If `points_balance` were added as a column on `registered_users`, it would be functionally dependent on `user_id` and technically would not violate 3NF. However, the separation is motivated by the **Single Responsibility Principle** applied to schema design:

- The loyalty system is a Task 6 extension that should not modify the core user table's structure.
- Not all users may have loyalty points (the relationship is 1:0..1, not 1:1).
- The `points_balance` column has its own CHECK constraint (`points_balance >= 0`) and its own `updated_at` timestamp, forming a self-contained entity.
- The `execute_booking_with_loyalty_discount` function uses `FOR UPDATE` row-level locking on `user_loyalty_points` — isolating this lock to a separate table avoids blocking concurrent profile queries on `registered_users`.

### Example 4: `policy_documents` as a Standalone Entity

Policy documents have their own identity and attributes:

```
id → title, category, content, embedding, source_file, created_at
```

These attributes depend solely on the policy document's auto-generated `id`. Policy knowledge represents static knowledge-base data, and its attributes depend on the policy document ID, not on users, bookings, or payments. Storing policy content inside a transactional table would improperly mix static reference data with operational records. The standalone design ensures policy attributes remain functionally dependent only on their own primary key, keeping the RAG retrieval layer fully independent.

## 2.5 Deliberate De-normalisation and Design Trade-offs

While the schema targets 3NF for core operational tables, several controlled de-normalisation choices are made for practical reasons.

### Trade-off 1: `operates_on` as a `TEXT[]` Array

As discussed in Section 2.2, both `metro_schedules` and `nr_schedules` store `operates_on` as a PostgreSQL `TEXT[]` array rather than normalising it into a separate `schedule_operating_days` table.

- **Fully normalised alternative**: A junction table `schedule_operating_days(schedule_id, day_name)` with one row per schedule per operating day.
- **Why the array is used**: Operating days form a small, closed domain (seven weekday names). They are always retrieved as a complete set alongside other schedule metadata and are never queried, updated, or joined independently. A separate table would add join overhead to every schedule retrieval query without meaningful normalisation benefit.
- **Trade-off acknowledged**: The array representation makes it harder to answer queries like "which schedules operate on Saturdays?" without array containment operators (`@>`). However, the current system does not require such queries — schedule filtering is done by date matching in the application layer. Crucially, while this small schedule property is de-normalised for convenience, the core operational repeating groups (schedule stops and station-line mappings) remain strictly normalised in child tables.

### Trade-off 2: `amount_usd` Stored in Both `nr_bookings` and `payments`

The fare amount is stored in two places:

- `nr_bookings.amount_usd` — the fare charged at booking time
- `payments.amount_usd` — the amount processed in the payment record

This duplication is a **deliberate snapshot/audit trade-off**. The fare can theoretically be recalculated from `nr_schedule_fare_classes.base_fare_usd + per_stop_rate_usd × stops_travelled`, but storing the computed `amount_usd` at booking time preserves the **price the customer was actually charged**, even if fare rules are later updated. This is essential for:

- **Refund calculation**: The `execute_cancellation` function reads `amount_usd` directly from `nr_bookings` to determine the refund, without re-deriving it from potentially-changed fare tables.
- **Payment reconciliation**: The payment record's `amount_usd` should match what was charged, providing an independent audit trail.
- **Loyalty discount auditability**: Task 6's `execute_booking_with_loyalty_discount` stores the discounted `final_amount` in `nr_bookings.amount_usd` and `payments.amount_usd`, preserving the loyalty-adjusted price.

### Trade-off 3: VARCHAR Business Keys Instead of Surrogate Keys

All core tables use human-readable VARCHAR business keys (e.g. `RU01`, `MS01`, `NR01`, `BK001`) as primary keys rather than auto-generated `SERIAL` or `UUID` values. This is documented in the schema header and serves several purposes:

- **Cross-system consistency**: The same IDs are used in PostgreSQL, Neo4j, and the JSON mock data files, avoiding an extra mapping layer.
- **Debugging and grading**: Human-readable IDs simplify interactive testing and demonstration.
- **Deterministic seeding**: `seed_postgres.py` uses `ON CONFLICT DO NOTHING` with fixed IDs, making re-seeding idempotent.

The trade-off is that VARCHAR keys have slightly higher join cost compared to integer keys, and require application-layer ID generation logic (e.g. finding the maximum numeric suffix and incrementing). For a single-region teaching project, this performance difference is negligible. The schema header notes that production systems should use `UUID v7` or `BIGSERIAL` for scalability.

### Trade-off 4: `policy_documents` Flattened Text Content

The `policy_documents` table stores policy content as free-text chunks (`content TEXT`) paired with 768-dimensional vector embeddings. A fully normalised approach might decompose policy documents into structured fields (e.g. separate tables for policy rules, conditions, and exceptions). However:

- **RAG retrieval** depends on natural-language text chunks for semantic similarity search. Decomposing content into structured fields would reduce embedding quality.
- The current design optimises for the primary access pattern: `query_policy_vector_search` computes cosine similarity on the `embedding` column and returns `title`, `category`, and `content` as context for the LLM.
- The trade-off is that structured policy analytics (e.g. "list all refund window thresholds") require parsing free text rather than querying structured fields.

## 2.6 Password Hashing and Credential Storage

### Algorithm: PBKDF2-HMAC-SHA256

TransitFlow uses **PBKDF2-HMAC-SHA256** (Password-Based Key Derivation Function 2 with HMAC-SHA256) for password hashing. This algorithm is implemented in both `seed_postgres.py` (for seeding initial user data) and `databases/relational/queries.py` (for runtime registration and login verification).

Password hashes are stored in `user_credentials.password_hash` in the following format:

```
pbkdf2_sha256$100000$<salt_hex>$<hash_hex>
```

Where:
- `pbkdf2_sha256` — algorithm identifier label
- `100000` — iteration count (100,000 rounds)
- `<salt_hex>` — 16-byte random salt encoded as hexadecimal (32 hex characters)
- `<hash_hex>` — derived key (hash output) encoded as hexadecimal

### Key Stretching: Why PBKDF2 Over MD5 or SHA-1

MD5 and SHA-1 are **general-purpose cryptographic hash functions** designed to be fast. Fast hashes allow an attacker to brute-force typical passwords in seconds to minutes. These algorithms are **not suitable for password storage** because:

- Their speed makes brute-force and dictionary attacks trivially fast.
- MD5 has known collision vulnerabilities.
- SHA-1 has demonstrated collision attacks and is deprecated by NIST for most purposes.

PBKDF2 addresses this by applying **key stretching**: it iterates the underlying HMAC-SHA256 function **100,000 times** for each password hash. This means:

- Computing one hash takes approximately 100,000× longer than a single SHA-256 call.
- PBKDF2 significantly reduces password guessing throughput compared with fast single-pass hashes.
- This makes brute-force attacks computationally infeasible for strong passwords within practical time constraints.

The iteration count is stored in the hash string itself (`100000`), allowing future upgrades to higher iteration counts without invalidating existing hashes.

### Salt Management: Defeating Rainbow Tables

Each user receives a **unique random salt** generated by `os.urandom(16)` — a cryptographically secure random number generator producing 16 bytes (128 bits) of entropy. The salt is concatenated with the password before hashing and stored alongside the hash output.

The purpose of per-user salting is to ensure that **two users with identical passwords produce different stored hashes**:

**Example:**

Suppose User A (Alice, `RU01`) and User B (Bob, `RU02`) both choose the password `"transit123"`.

- User A's salt: `S1 = a3b7c9...` (random 16 bytes)
- User B's salt: `S2 = f1d2e8...` (different random 16 bytes)
- User A's hash: `PBKDF2("transit123", S1, 100000)` → `hash_A`
- User B's hash: `PBKDF2("transit123", S2, 100000)` → `hash_B`
- Result: `hash_A ≠ hash_B`

Because the salts differ, the derived hashes differ, even though the input passwords are identical. This prevents two critical attack vectors:

1. **Rainbow table attacks**: A rainbow table is a precomputed lookup table mapping passwords to hashes. Without salt, an attacker can build one rainbow table and match it against every user in the database. With per-user salts, the attacker would need a separate rainbow table for each of the 2¹²⁸ possible salt values — a computationally impossible task.

2. **Hash comparison attacks**: Without salt, if an attacker observes that two user accounts have identical stored hashes, they immediately know both users share the same password. With per-user salts, identical passwords produce different hashes, revealing no information about password reuse.

### Login Verification

When a user logs in (via `login_user` in `queries.py`), the system:

1. Retrieves the stored hash string from `user_credentials` for the given email.
2. Parses the stored string to extract the algorithm label, iteration count, salt, and expected hash.
3. Recomputes `PBKDF2-HMAC-SHA256(input_password, stored_salt, stored_iterations)`.
4. Compares the recomputed hash against the stored expected hash.
5. Returns the user profile only if the hashes match.

The `_verify_password` function in `queries.py` also includes a legacy fallback for plain SHA-256 hashes (64-character hex strings) to support data that may have been seeded before the PBKDF2 migration. This ensures backward compatibility while the primary hashing path uses the stronger PBKDF2 algorithm.

## 2.7 Summary of Normalisation Benefits

The normalised schema design provides the following benefits for TransitFlow:

| Benefit | How the Schema Achieves It |
|---|---|
| **Reduced redundancy** | Fare rules are stored once in `nr_schedule_fare_classes`, not repeated across every booking row. Station names are stored once in station tables, not duplicated in every stop or booking row. |
| **Update consistency** | Changing a station name requires updating one row in `metro_stations` or `national_rail_stations`, not every schedule stop and booking that references it. |
| **Referential integrity** | Foreign keys across 18 relationships ensure that bookings cannot reference non-existent users, schedules, or stations. |
| **Transaction safety** | Separate `nr_bookings` and `payments` tables allow `execute_booking` and `execute_booking_with_loyalty_discount` to insert, validate, and commit booking + payment + loyalty update atomically within a single PostgreSQL transaction. |
| **Modular extension** | Task 6 loyalty points were added as a new `user_loyalty_points` table without modifying the core `registered_users` schema, demonstrating that the normalised design supports clean extension. |
| **Credential isolation** | Separating `user_credentials` from `registered_users` ensures that profile queries never access password hashes, and credential updates never lock profile data. |
| **Independent lifecycle** | Booking status (`confirmed` / `cancelled`) and payment status (`paid` / `refunded`) can evolve independently because they reside in separate tables with separate primary keys. |

## 2.8 Known Limitations and Future Improvements

- **`operates_on` array**: The `TEXT[]` array in `metro_schedules` and `nr_schedules` could be normalised into a `schedule_operating_days(schedule_id, day_name)` table if the system needed to support more complex calendar rules (e.g. holiday exceptions, seasonal schedules, or per-day frequency variations). The current array representation is sufficient for the fixed weekday-name domain used by TransitFlow.

- **Stored `amount_usd` snapshots**: Both `nr_bookings.amount_usd` and `payments.amount_usd` store the fare at transaction time. If fare rules change retroactively, care must be taken to distinguish the historical booked amount from the current fare calculation. The refund logic in `execute_cancellation` correctly reads from the stored `amount_usd` rather than recalculating.

- **`policy_documents` flattened content**: The free-text `content` column is appropriate for RAG-based semantic retrieval but not ideal for structured policy reporting. If the system needed to extract specific policy parameters programmatically (e.g. "what is the refund percentage for cancellations within 24 hours?"), a more structured policy table with separate columns for policy type, time windows, and percentages would be beneficial.

- **Loyalty point audit trail**: The current `user_loyalty_points` table stores only the current `points_balance` and `updated_at`. It does not maintain a transaction log of point accruals and redemptions. If the membership system became more complex (e.g. point expiration, earning points from trips, tier-based multipliers), a `loyalty_transactions` audit table with columns such as `(transaction_id, user_id, change_amount, reason, booking_id, created_at)` would be needed to support dispute resolution and point history queries.

- **No UNIQUE constraint on payment/feedback FK columns**: The `payments.nr_booking_id` and `payments.metro_trip_id` columns do not have UNIQUE constraints, meaning the schema technically permits multiple payment records per booking. The same applies to `feedback.nr_booking_id` and `feedback.metro_trip_id`. The application layer currently creates exactly one payment per booking, but the schema does not enforce this at the database level. Adding UNIQUE constraints on these FK columns (within a partial index that excludes NULLs) would tighten the 1:0..1 relationship if business rules require it.