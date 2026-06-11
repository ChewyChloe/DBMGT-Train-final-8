# Task 6 Optional Bonus — Loyalty-Aware TransitFlow

> **Loyalty-Aware TransitFlow: Membership Discounts, Transfer Penalties, and Policy RAG**
>
> 會員導向 TransitFlow：會員折扣、轉乘懲罰與政策 RAG 查詢

---

## 1. Feature Name

**Loyalty-Aware TransitFlow** extends the base system with:

1. **PostgreSQL Membership Points Discount** — Users can redeem loyalty points for fare discounts during booking.
2. **Neo4j Transfer Waiting Penalty** — Routes that cross interchange stations receive a time penalty accounting for walking, waiting, and crowding.
3. **RAG Membership & Transfer Policy** — Natural language queries about loyalty programs and transfer policies are answered via vector search.
4. **Agent Integration** — Three new tools allow the chatbot to check points, book with discounts, and route with penalties.

---

## 2. Motivation

Real-world transit systems offer loyalty rewards and transfer penalties. This extension demonstrates:

- **Transactional integrity**: Booking + payment + loyalty point deduction in a single PostgreSQL transaction.
- **Graph enrichment**: INTERCHANGE_TO relationships carry crowd and wait penalties that affect routing scores.
- **RAG extensibility**: The vector store grows without breaking existing retrieval.
- **Agent modularity**: New tools plug into the existing tool-routing framework with deterministic fallbacks.

---

## 3. Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `databases/relational/schema.sql` | MODIFY | Added `user_loyalty_points` table |
| `skeleton/seed_postgres.py` | MODIFY | Added `seed_user_loyalty_points()` |
| `databases/relational/queries.py` | MODIFY | Added `query_user_loyalty_points()`, `execute_booking_with_loyalty_discount()` |
| `skeleton/seed_neo4j.py` | MODIFY | Added `transfer_wait_time_min`, `crowd_penalty` to INTERCHANGE_TO |
| `databases/graph/queries.py` | MODIFY | Added `query_route_with_transfer_penalty()` |
| `train-mock-data/membership_policy.json` | NEW | Membership rewards & transfer policy JSON |
| `skeleton/seed_vectors.py` | MODIFY | Added section 5 to load `membership_policy.json` |
| `skeleton/agent.py` | MODIFY | Added 3 new tools, execution handlers, fallback routing |
| `TASK6.md` | NEW | This documentation file |

All bonus-related code is marked with:
```python
# TASK 6 EXTENSION
```

---

## 4. PostgreSQL Implementation

### 4.1 Schema (`schema.sql`)

```sql
-- TASK 6 EXTENSION
CREATE TABLE IF NOT EXISTS user_loyalty_points (
    user_id        VARCHAR(20) PRIMARY KEY
                   REFERENCES registered_users(user_id),
    points_balance INTEGER NOT NULL DEFAULT 0
                   CHECK (points_balance >= 0),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 Seed Data (`seed_postgres.py`)

| user_id | points_balance |
|---------|---------------|
| RU01    | 120           |
| RU02    | 80            |
| RU03    | 250           |
| RU04    | 0             |
| RU05    | 500           |

Uses `INSERT ... ON CONFLICT DO NOTHING` for idempotency.

### 4.3 `query_user_loyalty_points(email)`

Looks up loyalty points by email via `LEFT JOIN` on `registered_users` and `user_loyalty_points`.

Returns:
```json
{
  "user_id": "RU01",
  "email": "alice.tan@email.com",
  "points_balance": 120,
  "redeem_rule": "100 points = 1.00 USD discount"
}
```

### 4.4 `execute_booking_with_loyalty_discount(...)`

Full transactional booking with loyalty discount:

1. Resolve user_id from email
2. Lock loyalty points row (`SELECT ... FOR UPDATE`)
3. Validate schedule, origin, destination, fare class, seat
4. Calculate original fare
5. Apply discount: 100 pts → 1.00 USD (max 1.00 per booking)
6. Insert booking + payment
7. Deduct loyalty points
8. Commit atomically (or rollback on any error)

Returns:
```json
{
  "booking_id": "BK006",
  "payment_id": "PM006",
  "user_id": "RU01",
  "original_fare_usd": 8.50,
  "discount_usd": 1.00,
  "final_amount_usd": 7.50,
  "points_before": 120,
  "points_used": 100,
  "points_after": 20,
  "loyalty_rule": "100 points = 1.00 USD discount"
}
```

---

## 5. Neo4j Implementation

### 5.1 Transfer Penalty Properties (`seed_neo4j.py`)

INTERCHANGE_TO relationships now carry:

| Property | Value | Description |
|----------|-------|-------------|
| `transfer_wait_time_min` | 4 | Fixed walking + waiting buffer |
| `crowd_penalty` | 1.5 | Central Station (MS01/NR01) — busy hub |
| `crowd_penalty` | 0.5 | Other interchanges (Old Town, Ferndale) |

### 5.2 `query_route_with_transfer_penalty(origin_id, destination_id, avoid_crowded=True)`

Uses Dijkstra shortest-path, then applies transfer penalties on the Python side:

- `base_time_min` = Dijkstra weight
- `transfer_wait_penalty_min` = sum of `transfer_wait_time_min` across interchanges
- `crowd_penalty` = sum of `crowd_penalty` (if `avoid_crowded=True`)
- `adjusted_score` = base + wait + crowd

Returns:
```json
{
  "origin": {"station_id": "MS01"},
  "destination": {"station_id": "NR05"},
  "route": [...],
  "base_time_min": 35,
  "transfer_wait_penalty_min": 4.0,
  "crowd_penalty": 1.5,
  "adjusted_score": 40.5,
  "explanation": "This route includes 1 interchange(s) ..."
}
```

---

## 6. RAG Implementation

### 6.1 New Policy Document (`membership_policy.json`)

Contains two top-level sections:

- **membership_rewards**: loyalty points earning rule, redemption rule, limits, eligibility
- **transfer_policy**: transfer waiting penalty, crowded station penalty

### 6.2 Vector Seeder Update (`seed_vectors.py`)

Section 5 processes `membership_policy.json` using the same `_flatten_dict()` strategy. Produces ~4 new policy documents with category `"membership"`.

### 6.3 RAG Test Queries

```
How do loyalty points work?
How many points do I need for a discount?
What is the transfer waiting penalty?
```

---

## 7. Agent Integration

### 7.1 New Tools

| Tool Name | Maps To | Description |
|-----------|---------|-------------|
| `check_loyalty_points` | `query_user_loyalty_points` | Check logged-in user's loyalty balance |
| `book_with_loyalty_discount` | `execute_booking_with_loyalty_discount` | Book with automatic point redemption |
| `route_with_transfer_penalty` | `query_route_with_transfer_penalty` | Route with transfer/crowd penalties |

### 7.2 Deterministic Fallbacks

- "loyalty point", "reward point", "membership point" → `check_loyalty_points`
- "transfer penalty", "avoid crowd", "crowded transfer" → `route_with_transfer_penalty`

### 7.3 System Prompt

The existing prompt + `search_policy` already covers membership policy queries. No explicit system prompt change needed — the RAG pipeline handles it.

---

## 8. Test Commands

### Compile Check
```bash
python -m py_compile databases/relational/queries.py
python -m py_compile skeleton/seed_postgres.py
python -m py_compile skeleton/seed_neo4j.py
python -m py_compile databases/graph/queries.py
python -m py_compile skeleton/seed_vectors.py
python -m py_compile skeleton/agent.py
```

### Seed
```bash
python skeleton/seed_postgres.py
python skeleton/seed_neo4j.py
python skeleton/seed_vectors.py
```

### PostgreSQL Tests
```bash
# Check loyalty points
python -c "from databases.relational.queries import query_user_loyalty_points; print(query_user_loyalty_points('alice.tan@email.com'))"

# Booking with loyalty discount
python -c "from databases.relational.queries import execute_booking_with_loyalty_discount; ok, data = execute_booking_with_loyalty_discount(email='alice.tan@email.com', schedule_id='NR_SCH01', origin_station_id='NR01', destination_station_id='NR05', travel_date='2025-09-01', fare_class='standard', seat_id='B05'); print(ok, data)"
```

### Neo4j Tests
```bash
python -c "from databases.graph.queries import query_route_with_transfer_penalty; import json; print(json.dumps(query_route_with_transfer_penalty('MS01','NR05'), indent=2, default=str))"

python -c "from databases.graph.queries import query_route_with_transfer_penalty; import json; print(json.dumps(query_route_with_transfer_penalty('NR01','MS10'), indent=2, default=str))"
```

### RAG Tests
```bash
python -c "from databases.relational.queries import query_policy_vector_search; from skeleton.llm_provider import llm; import json; e=llm.embed('How do loyalty points work?'); print(json.dumps(query_policy_vector_search(e), indent=2, ensure_ascii=False, default=str))"
```

### Regression Tests
```bash
python databases/graph/queries.py
python -c "from databases.relational.queries import login_user; print(login_user('alice.tan@email.com','alice1990'))"
python -c "from databases.relational.queries import query_payment_info; print(query_payment_info('BK001'))"
```

---

## 9. Example Output

### Loyalty Points Query
```
Input:  "How many loyalty points do I have?"  (logged in as alice.tan@email.com)
Tool:   check_loyalty_points
Output: {"user_id": "RU01", "email": "alice.tan@email.com", "points_balance": 120, "redeem_rule": "100 points = 1.00 USD discount"}
Reply:  "You have 120 loyalty points. You can redeem 100 points for a 1.00 USD discount on your next booking."
```

### Loyalty Booking
```
Input:  "Book NR01 to NR05 using my loyalty points"
Tool:   book_with_loyalty_discount / check_national_rail_availability
Output: {"booking_id":"BK006", "original_fare_usd":8.50, "discount_usd":1.00, "final_amount_usd":7.50, "points_used":100, "points_after":20}
Reply:  "Booking confirmed! Original fare: $8.50, loyalty discount: $1.00, you paid: $7.50. Remaining points: 20."
```

### Transfer Penalty Route
```
Input:  "Find route MS01 to NR05 avoiding crowded transfers"
Tool:   route_with_transfer_penalty
Output: {"base_time_min":35, "transfer_wait_penalty_min":4.0, "crowd_penalty":1.5, "adjusted_score":40.5}
Reply:  "Route: MS01 → ... → NR05. Base time: 35 min. Transfer penalty: 4 min. Crowd penalty: 1.5. Adjusted total: 40.5 min."
```

---

## 10. Known Limitations

1. **Earned points not implemented**: After a booking, the user does not earn new loyalty points. Only point redemption (deduction) is implemented.
2. **Single-tier membership**: All users share the same earning/redemption rate. No Silver/Gold/Platinum tiers.
3. **Max 1 USD discount per booking**: The discount cap is intentionally conservative to avoid test failures.
4. **Transfer penalty is Python-side**: Penalties are computed after Dijkstra, not within the Cypher query itself. This is safe but means the shortest path is still found by `travel_time_min` only.
5. **Agent routing for `book_with_loyalty_discount`**: The LLM must extract schedule_id, seat_id, etc. from multi-turn context. For demo purposes, direct backend testing is more reliable.
