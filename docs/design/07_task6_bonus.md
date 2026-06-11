# 7. Optional Extension Bonus: Loyalty-Aware TransitFlow

**Feature name:** Loyalty-Aware TransitFlow: Membership Discounts, Transfer Penalties, and Policy RAG

**中文名稱：** 會員導向 TransitFlow：會員折扣、轉乘懲罰與政策 RAG 查詢

## 7.1 Motivation

The base TransitFlow system can search schedules, check seat availability, calculate fares, create bookings, and process payments. These operations cover the core booking workflow, but they do not account for user-specific membership benefits, realistic transfer costs, or policy questions about loyalty programs.

Task 6 adds three connected extensions that make the assistant handle more realistic user questions:

- "How many loyalty points do I have?"
- "Can I use my points for a discount on this booking?"
- "Why does this route include a transfer penalty?"
- "How do loyalty points work?"

The extension connects three database layers. PostgreSQL stores loyalty point balances and processes discounted bookings in a single atomic transaction. Neo4j adds transfer waiting and crowding penalties to interchange relationships so route scoring reflects real travel experience. The RAG vector store gains membership and transfer policy documents so the Agent can explain the rules in natural language.

A concrete example: Alice has 120 loyalty points. She books a national rail ticket with an original fare of 8.50 USD. The system redeems 100 points for a 1.00 USD discount. The final payment amount is 7.50 USD, and Alice has 20 points remaining. The booking, payment, and point deduction all happen in one PostgreSQL transaction. If any step fails, everything rolls back.

## 7.2 PostgreSQL Extension: Loyalty Points and Discounted Booking

### Schema Change

Task 6 adds a new table `user_loyalty_points` to `schema.sql`:

```sql
-- TASK 6 EXTENSION: Membership loyalty points for fare discounts.
-- Separate table (not a column on registered_users) to isolate the
-- extension from the core user schema and preserve SRP.
CREATE TABLE IF NOT EXISTS user_loyalty_points (
    user_id        VARCHAR(20) PRIMARY KEY
                   REFERENCES registered_users(user_id),
    points_balance INTEGER NOT NULL DEFAULT 0
                   CHECK (points_balance >= 0),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
```

The `CHECK (points_balance >= 0)` constraint prevents negative balances at the database level. The table has a 1:0..1 relationship with `registered_users` (not every user is required to have a loyalty points row).

### Seed Data

`seed_postgres.py` inserts 5 initial loyalty point rows using `INSERT ... ON CONFLICT DO NOTHING` for idempotency:

| user_id | points_balance |
|---------|---------------|
| RU01    | 120           |
| RU02    | 80            |
| RU03    | 250           |
| RU04    | 0             |
| RU05    | 500           |

### Query Function: `query_user_loyalty_points(email)`

This function looks up a user's current loyalty point balance by joining `registered_users` with `user_loyalty_points` using a `LEFT JOIN`. It returns the user ID, email, current balance, and the redemption rule text.

```powershell
python -c "from databases.relational.queries import query_user_loyalty_points; print(query_user_loyalty_points('alice.tan@email.com'))"
```

Expected output:

```text
{'user_id': 'RU01', 'email': 'alice.tan@email.com', 'points_balance': 120, 'redeem_rule': '100 points = 1.00 USD discount'}
```

### Transaction Function: `execute_booking_with_loyalty_discount(...)`

This function performs the full booking with loyalty discount in a single PostgreSQL transaction. The original `execute_booking` function was not modified. The Task 6 function was added separately to reduce regression risk.

The transaction flow (simplified pseudocode):

```sql
-- Simplified Task 6 transaction flow
BEGIN;

-- 1. Resolve user_id from email
SELECT user_id FROM registered_users WHERE email = $email;

-- 2. Lock the loyalty points row to prevent concurrent double spending
SELECT points_balance
FROM user_loyalty_points
WHERE user_id = $1
FOR UPDATE;

-- 3. Application logic: check seat availability, validate schedule/origin/destination
-- 4. Calculate original fare from nr_schedule_fare_classes
-- 5. If points_balance >= 100, apply 1.00 USD discount (max 1.00 per booking)
--    Discount cannot reduce fare below 0.

-- 6. Insert the booking
INSERT INTO nr_bookings (..., amount_usd, ...)
VALUES (..., final_amount_usd, ...);

-- 7. Insert the payment
INSERT INTO payments (..., nr_booking_id, amount_usd, status, ...)
VALUES (..., booking_id, final_amount_usd, 'paid', ...);

-- 8. Deduct loyalty points
UPDATE user_loyalty_points
SET points_balance = points_balance - points_used,
    updated_at = NOW()
WHERE user_id = $1;

COMMIT;
-- If any step fails, the entire transaction rolls back.
```

### Booking Test Evidence

First booking (Alice has 120 points):

```text
execute_booking_with_loyalty_discount(...)
original_fare_usd = 8.5
discount_usd = 1.0
final_amount_usd = 7.5
points_before = 120
points_used = 100
points_after = 20
```

Second booking (Alice now has only 20 points). The function still succeeds but applies no discount because the balance is below 100:

```text
points_before = 20
discount_usd = 0.0
final_amount_usd = 8.5
points_used = 0
points_after = 20
```

### Implementation Issue and Correction

The first version of `execute_booking_with_loyalty_discount` treated `seat_id="any"` as a literal seat identifier. When tested with `seat_id="any"`, the function failed with:

```text
Seat any not found in standard for NR_SCH01.
```

The function was corrected so that when `seat_id="any"` is passed, it automatically queries for an available seat in the requested fare class and selects one, rather than looking for a seat literally named "any."

## 7.3 Neo4j Extension: Transfer Waiting and Crowd Penalties

### Why Transfer Penalties Matter

The existing Neo4j graph supports shortest routes, cheapest routes, alternative routes, interchange paths, and delay ripple queries. These all use `travel_time_min` on edges. But cross-system routes are not only about travel time. A passenger transferring between metro and national rail also experiences walking time, waiting for the next service, and crowding at busy interchange hubs. Adding penalties to interchange edges makes route scoring closer to real travel experience.

### Graph Changes

The existing graph already has `MetroStation` and `NationalRailStation` nodes connected by `METRO_LINK`, `RAIL_LINK`, and `INTERCHANGE_TO` relationships. Task 6 adds two new properties to `INTERCHANGE_TO` relationships:

- `transfer_wait_time_min`: fixed walking and waiting buffer (4 minutes for all interchanges)
- `crowd_penalty`: extra penalty for busy hubs (1.5 for Central Station, 0.5 for others)

The seeding Cypher in `seed_neo4j.py` creates these bidirectionally:

Metro to National Rail direction:

```cypher
// TASK 6 EXTENSION: added transfer_wait_time_min, crowd_penalty
MATCH (ms:MetroStation {station_id: $from_id}),
      (nr:NationalRailStation {station_id: $to_id})
MERGE (ms)-[r:INTERCHANGE_TO {travel_time_min: $travel_time_min}]->(nr)
SET r.per_stop_rate_usd = 0.0,
    r.transfer_wait_time_min = $transfer_wait,
    r.crowd_penalty = $crowd_penalty
```

National Rail to Metro direction (reverse):

```cypher
// TASK 6 EXTENSION: added transfer_wait_time_min, crowd_penalty
MATCH (nr:NationalRailStation {station_id: $from_id}),
      (ms:MetroStation {station_id: $to_id})
MERGE (nr)-[r:INTERCHANGE_TO {travel_time_min: $travel_time_min}]->(ms)
SET r.per_stop_rate_usd = 0.5,
    r.transfer_wait_time_min = $transfer_wait,
    r.crowd_penalty = $crowd_penalty
```

Central Station (MS01/NR01) is the busiest interchange. It receives `crowd_penalty = 1.5`. The other two interchanges (MS07/NR03 and MS15/NR07) each receive `crowd_penalty = 0.5`.

### Verified Seeded Property Values

The following interchange properties were verified directly in Neo4j:

```cypher
MATCH (a)-[r:INTERCHANGE_TO]->(b)
RETURN a.station_id AS from_id,
       b.station_id AS to_id,
       properties(r) AS props
ORDER BY from_id, to_id;
```

```text
MS01 -> NR01: transfer_wait_time_min = 4, crowd_penalty = 1.5
MS07 -> NR03: transfer_wait_time_min = 4, crowd_penalty = 0.5
MS15 -> NR07: transfer_wait_time_min = 4, crowd_penalty = 0.5
NR01 -> MS01: transfer_wait_time_min = 4, crowd_penalty = 1.5
NR03 -> MS07: transfer_wait_time_min = 4, crowd_penalty = 0.5
NR07 -> MS15: transfer_wait_time_min = 4, crowd_penalty = 0.5
```

### Query Function: `query_route_with_transfer_penalty(origin_id, destination_id, avoid_crowded=True)`

This function was added as a new function in `databases/graph/queries.py` instead of replacing `query_shortest_route` or `query_cheapest_route`, to avoid breaking existing graph tests. It uses Dijkstra shortest-path and then applies transfer penalties on the Python side:

- `base_time_min` = Dijkstra path weight (travel time only)
- `transfer_wait_penalty_min` = sum of `transfer_wait_time_min` across interchange edges
- `crowd_penalty` = sum of `crowd_penalty` across interchange edges (if `avoid_crowded=True`)
- `adjusted_score` = base + wait + crowd

### Backend Test

```powershell
python -c "from databases.graph.queries import query_route_with_transfer_penalty; import json; print(json.dumps(query_route_with_transfer_penalty('MS01','NR05'), indent=2, ensure_ascii=False, default=str))"
```

Expected output summary:

```text
route = MS01 -> MS07 -> NR03 -> NR05
base_time_min = 37
transfer_wait_penalty_min = 4.0
crowd_penalty = 0.5
adjusted_score = 41.5
```

## 7.4 RAG Task 6 Extension

To support the advanced routing mechanics and user reward frameworks introduced in the Task 6 Optional Extension, the RAG knowledge infrastructure was scaled by absorbing a 5th semi-structured text asset: `membership_policy.json`.

### 1. Granular Constraint Breakdown
The newly integrated policy covers two primary domain pillars, defining exact mathematical boundaries and deterministic validation rules that the LLM Agent must enforce prior to downstream computation:

#### A. Membership Rewards & Loyalty Ledger (`membership_rewards`)
* **Earning Parameters (`loyalty_points.earning_rule`):** Registered users automatically accumulate 1 loyalty point per 1.00 USD spent exclusively on completed National Rail bookings. 
* **Redemption Constraints (`loyalty_points.redemption_rule`):** Introduces a strict minimum threshold and static conversion rate where exactly **100 loyalty points** translate to a **1.00 USD discount** on eligible rail segments.
* **Operational Hard Boundaries (`loyalty_points.limitations`):** Caps the maximum discount per individual transaction at exactly 1.00 USD. It enforces an absolute lower bound preventing points from ever reducing fares below 0.00 USD, prohibits cash exchange conversions, and restricts execution to a single redemption per booking session.
* **Tiering Specifications (`membership_tiers`):** Explicitly documents that the current implementation enforces a unified, single-tier baseline for all active profiles, while reserving semantic provisions for multi-tier scaling (Silver, Gold, Platinum) in future releases.

#### B. Intermodal Transfer & Congestion Penalties (`transfer_policy`)
* **Transfer Waiting Penalty (`transfer_waiting_penalty`):** Accounts for platform walking overhead and service latency between the City Metro and National Rail nodes by mandating a deterministic fixed addition of **4 minutes** to the cumulative journey runtime for every valid network interchange event.
* **Crowded Station Penalty Tiering (`crowded_station_penalty`):** Establishes an infrastructure-driven congestion routing penalty. The primary multi-modal hub—**Central Station (`MS01` / `NR01`)**—receives a heavy weight penalty of **1.5 minutes**. Secondary critical interchange junctions, specifically **Old Town (`MS07` / `NR03`)** and **Ferndale (`MS15` / `NR07`)**, are assigned a mitigated penalty weight of **0.5 minutes**.

### 2. Document Expansion Architecture & Metrics
The pipeline ingestion engine automatically breaks this file down into individual chunk blocks based on leaf-node configurations to prevent cross-domain token contamination. 

* **Baseline System Documents (Tasks 1–5):** 71 structural text documents.
* **Loyalty-Aware Post-Ingestion Matrix:** Ingesting membership_policy.json expands the indexing pool deterministically from **71 to 75 total structural documents**.

This precise expansion enables the LLM Agent to dynamically run semantic vector similarity lookups for terms like "how to avoid crowded transfers" or *"maximum discount limit"*—safeguarding the application against routing logic hallucinations and enforcing compliance directly before invoking PostgreSQL billing queries or Neo4j Cypher pathfinding scripts.

## 7.5 Agent Integration

The Agent in `skeleton/agent.py` exposes the Task 6 functionality through three new tools and the existing `search_policy` tool:

| Agent Tool Name | Backend Function | Purpose |
|----------------|-----------------|---------|
| `check_loyalty_points` | `query_user_loyalty_points` | Check the logged-in user's loyalty point balance |
| `book_with_loyalty_discount` | `execute_booking_with_loyalty_discount` | Book a ticket with automatic point redemption |
| `route_with_transfer_penalty` | `query_route_with_transfer_penalty` | Find a route with transfer and crowd penalties |
| `search_policy` (existing) | `query_policy_vector_search` | Retrieve membership policy documents via RAG |

The Agent also includes deterministic keyword fallbacks for common Task 6 phrases:

- "loyalty point", "reward point", "membership point" triggers `check_loyalty_points`
- "transfer penalty", "avoid crowd", "crowded transfer" triggers `route_with_transfer_penalty`

### Agent Test: Loyalty Points

```powershell
python -c "from skeleton.agent import run_agent; r=run_agent('How many loyalty points do I have?', [], debug=True, current_user_email='alice.tan@email.com'); print('REPLY:', r[0]); print('DEBUG:', r[2])"
```

Expected behavior:

```text
Tool called: check_loyalty_points
points_balance returned
```

### Agent Test: Transfer Penalty Route

```powershell
python -c "from skeleton.agent import run_agent; r=run_agent('Find a route from MS01 to NR05 while avoiding crowded transfers.', [], debug=True, current_user_email='alice.tan@email.com'); print('REPLY:', r[0]); print('DEBUG:', r[2])"
```

Expected behavior:

```text
Tool called: route_with_transfer_penalty
origin_id = MS01
destination_id = NR05
```

### Agent Limitation

The backend tool results are correct and return structured JSON. However, the lightweight local LLM (llama3.2:1b) may sometimes summarize tool results imperfectly in its natural-language response. For example, it might round a fare or omit a penalty detail. Debug mode should be used to verify the actual tool calls and raw backend output when accuracy matters.

## 7.6 Files Changed and Inline Comments

`TASK6.md` at the repository root lists every file modified or added for this extension. The following files contain Task 6 changes:

| File | Change |
|------|--------|
| `TASK6.md` | NEW: This documentation file |
| `databases/relational/schema.sql` | Added `user_loyalty_points` table |
| `skeleton/seed_postgres.py` | Added `seed_user_loyalty_points()` |
| `databases/relational/queries.py` | Added `query_user_loyalty_points()`, `execute_booking_with_loyalty_discount()` |
| `skeleton/seed_neo4j.py` | Added `transfer_wait_time_min`, `crowd_penalty` to `INTERCHANGE_TO` |
| `databases/graph/queries.py` | Added `query_route_with_transfer_penalty()` |
| `train-mock-data/membership_policy.json` | NEW: Membership rewards and transfer policy JSON |
| `skeleton/seed_vectors.py` | Added section 5 to load `membership_policy.json` |
| `skeleton/agent.py` | Added 3 new tools, execution handlers, and fallback routing |

All Task 6 code includes `# TASK 6 EXTENSION` comments near the relevant new operations, including:

- `user_loyalty_points` schema definition
- Loyalty point seeding in `seed_postgres.py`
- Loyalty booking query functions in `queries.py`
- Neo4j transfer penalty relationship properties in `seed_neo4j.py`
- `query_route_with_transfer_penalty` in `databases/graph/queries.py`
- Membership policy vector ingestion in `seed_vectors.py`
- Agent tool registration and routing in `agent.py`

## 7.7 Testing Evidence Summary

| Test Area | Result |
|-----------|--------|
| PostgreSQL seed: `user_loyalty_points` | 5 rows seeded (RU01: 120, RU02: 80, RU03: 250, RU04: 0, RU05: 500) |
| RAG seed: `policy_documents` count | Increased from 71 to 75 |
| `query_user_loyalty_points('alice.tan@email.com')` | Returns `points_balance = 120` |
| `execute_booking_with_loyalty_discount(...)` first run | `original_fare = 8.5`, `discount = 1.0`, `final = 7.5`, points 120 to 20 |
| `execute_booking_with_loyalty_discount(...)` second run | `discount = 0.0`, `final = 8.5`, points stay at 20 (below threshold) |
| `query_route_with_transfer_penalty('MS01','NR05')` | `adjusted_score = 41.5` (base 37 + wait 4.0 + crowd 0.5) |
| RAG: "loyalty points" | Retrieved membership loyalty points policy |
| RAG: "transfer waiting penalty" | Retrieved transfer waiting penalty policy |
| Agent: `check_loyalty_points` | Tool call works, returns balance |
| Agent: `route_with_transfer_penalty` | Tool call works in debug mode |
| Agent: natural-language answer | PARTIAL: backend correct, LLM summary may be imprecise |

## 7.8 Known Limitations and Future Work

1. **No audit trail for points.** Loyalty points currently track only the current balance. A production system would need a `loyalty_transactions` table recording each earning and redemption event with timestamps and booking references.
2. **Fixed transfer penalty values.** Transfer waiting time and crowd penalty are fixed seed values. A production system could calculate crowding dynamically from live passenger volume data.
3. **Single membership tier.** All users share the same earning and redemption rates. The `membership_policy.json` mentions future Silver/Gold/Platinum tiers, but these are not implemented.
4. **Transfer penalty is Python-side.** Penalties are computed after Dijkstra, not within the Cypher query itself. The shortest path is found by `travel_time_min` only, and penalties are added afterward.
5. **Agent response accuracy.** The lightweight local LLM may summarize tool results imperfectly. Debug mode should be used to verify actual tool calls and raw results.
6. **Future routing features.** Express-only route filtering and fewest-transfer optimization remain future work.