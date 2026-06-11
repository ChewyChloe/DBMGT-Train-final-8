# 5. AI Tool Usage Evidence

AI tools were used as programming and design assistants throughout this project. They helped with schema documentation, query implementation, debugging, and Task 6 extension development. All AI outputs were checked against the actual repository files, schema definitions, seed scripts, and runtime test results before being accepted. The examples below describe five specific cases where AI was used, including one case where the AI output was incorrect and required human correction.

## 5.1 Example 1: Relational Schema and Normalisation Review

### Context

We needed to document and verify the PostgreSQL relational schema for Sections 1 and 2 of the Design Document. The schema includes 19 tables covering users, credentials, metro and national rail stations, schedules, stops, fare classes, seat coaches, seats, bookings, travel history, payments, feedback, policy documents, and the Task 6 `user_loyalty_points` table. The goal was to produce an accurate ER diagram, correct cardinality descriptions, and a normalisation analysis that matched the actual `schema.sql` rather than assumptions about what the schema should look like.

### Prompt

We asked the AI to inspect `schema.sql`, `seed_postgres.py`, and `queries.py`, then draft Section 1 (ER diagram, entity descriptions, cardinality summary, and constraint analysis) and Section 2 (1NF/2NF/3NF examples, de-normalisation trade-offs, and password hashing explanation). The prompt specified that the AI should use functional dependency notation, name specific normal forms, and base all claims on actual constraints found in the schema file.

### Outcome

The AI produced a detailed first draft with a Mermaid ER diagram, entity group descriptions, and normalisation examples using `nr_schedule_stops` (2NF, composite key partial dependency) and `payments` separation as part of the 3NF discussion. We manually reviewed the output against `schema.sql` and found two issues that needed correction:

1. The initial draft described `REGISTERED_USERS` to `USER_LOYALTY_POINTS` as a mandatory 1:1 relationship. We corrected this to zero-or-one (1:0..1) because not every user is required to have a loyalty points row.
2. The draft described `NR_BOOKINGS` to `PAYMENTS` and `FEEDBACK` as at-most-one relationships (1:0..1). We checked `schema.sql` and found that the XOR constraints control which booking type each payment or feedback row can reference, but there are no UNIQUE constraints on `payments.nr_booking_id`, `payments.metro_trip_id`, `feedback.nr_booking_id`, or `feedback.metro_trip_id`. We therefore revised the ERD wording to show that the database schema permits one-to-many relationships, even though the current application flow normally creates one payment per booking

We also verified that the password hashing section correctly described PBKDF2-HMAC-SHA256 with per-user salt and 100,000 iterations, matching the `_hash_password` function in `queries.py`.

## 5.2 Example 2: PostgreSQL Booking Transaction and Task 6 Loyalty Discount

### Context

Task 6 required a loyalty points discount system. Users with sufficient points should receive a discount when booking a national rail ticket. The booking flow needed to create a row in `nr_bookings`, a row in `payments`, and update the user's `points_balance` in `user_loyalty_points`, all within one PostgreSQL transaction. The risk was that without proper transaction handling, points could be deducted without a booking being created, or two concurrent requests could spend the same points twice.

### Prompt

We asked the AI to implement the Task 6 loyalty extension with minimal regression risk. Specifically: add the `user_loyalty_points` table to `schema.sql`, add `query_user_loyalty_points` for looking up a user's balance, and add `execute_booking_with_loyalty_discount` as a new function alongside the existing `execute_booking` (without modifying the original). We asked the AI to use transaction safety and row-level locking for the loyalty points update.

### Outcome

The AI suggested using `SELECT ... FOR UPDATE` to lock the `user_loyalty_points` row at the start of the transaction, preventing concurrent double spending. The function calculates the discount (100 points = $1.00 USD, max $1.00 per booking), creates the booking and payment with the discounted amount, and updates the point balance, all within a single `BEGIN ... COMMIT` block. If any step fails, the entire transaction rolls back.

We tested the flow directly and confirmed the results:

- `original_fare_usd`: 8.5
- `discount_usd`: 1.0
- `final_amount_usd`: 7.5
- `points_before`: 120, `points_used`: 100, `points_after`: 20

However, one AI-generated issue required correction. The initial implementation treated `seat_id="any"` as a literal seat identifier. When we tested a booking with `seat_id="any"`, the function failed with the error "Seat any not found in standard for NR_SCH01." We fixed the function so that when `seat_id="any"` is passed, it automatically queries for an available seat in the requested fare class and selects one, rather than looking for a seat literally named "any."

## 5.3 Example 3: Neo4j Transfer Penalty and Graph Routing

### Context

Task 6 required transfer waiting penalty and crowded interchange penalty for cross-system routes. The existing Neo4j graph already supported `query_shortest_route`, `query_cheapest_route`, `query_alternative_routes`, `query_interchange_path`, and `query_delay_ripple`. We wanted to add transfer penalty logic without breaking any of these existing functions.

### Prompt

We asked the AI to add `transfer_wait_time_min` and `crowd_penalty` properties to the `INTERCHANGE_TO` relationships in the Neo4j seed data, and to add `query_route_with_transfer_penalty` as a new graph query function. We specified that the new function should be additive (not replacing `query_shortest_route` or `query_cheapest_route`) so the existing graph regression tests would still pass.

### Outcome

The AI helped draft the new relationship properties in `seed_neo4j.py` and the `query_route_with_transfer_penalty` function in `databases/graph/queries.py`. We verified the seeded Neo4j relationship properties directly:

- MS01 (Central Square) to NR01 (Central Station): `transfer_wait_time_min` = 4, `crowd_penalty` = 1.5
- MS07 to NR03: `transfer_wait_time_min` = 4, `crowd_penalty` = 0.5
- MS15 to NR07: `transfer_wait_time_min` = 4, `crowd_penalty` = 0.5

The direct backend test passed:

- `query_route_with_transfer_penalty('MS01', 'NR05')`
- Route: MS01, MS07, NR03, NR05
- `base_time_min`: 37
- `transfer_wait_penalty_min`: 4.0
- `crowd_penalty`: 0.5
- `adjusted_score`: 41.5

We kept this as an additive Task 6 function. The original graph queries continued to work without modification.

## 5.4 Example 4: RAG Membership Policy and Vector Seeding

### Context

The RAG system originally contained policy documents for refund rules, booking policies, ticket information, and conduct guidelines. Task 6 needed the Agent to answer questions about loyalty points, membership rewards, and transfer waiting penalties. The goal was to add membership policy content to vector search without breaking existing policy retrieval.

### Prompt

We asked the AI to create `membership_policy.json` with policy chunks covering loyalty point earning, redemption rules, transfer waiting penalties, and crowded station penalties. We also asked the AI to update `seed_vectors.py` to load the new policy file alongside the existing ones. The seeder needed to remain idempotent (re-running it should not create duplicate documents).

### Outcome

The AI helped create `membership_policy.json` and update `seed_vectors.py` to include it in the policy loading loop. After seeding, the total `policy_documents` count increased from 71 to 75, confirming the four new membership policy chunks were added.

We tested semantic search and confirmed that relevant documents were retrieved:

- Query "loyalty points" retrieved: Membership Policy, Membership Rewards, Loyalty Points
- Query "transfer waiting penalty" retrieved: Membership Policy, Transfer Policy, Transfer Waiting Penalty
- Query "crowded station penalty" retrieved: Membership Policy, Transfer Policy, Crowded Station Penalty

We also re-tested representative existing RAG queries, such as "lost and found" and "maintenance disruption refund", and they still returned the expected policy documents.

## 5.5 Example 5: Incorrect AI Output and Human Correction

### Context

During QA testing, we asked the AI to run and analyze the full QA Test Suite covering PostgreSQL, Neo4j, RAG, and Agent layers. The goal was to classify each test case as PASS, PARTIAL, FAIL, or UNSUPPORTED based on actual runtime results.

### Prompt

We asked the AI to test the TransitFlow system across all five categories (PostgreSQL relational, Neo4j graph, RAG vector search, Agent runtime, and Task 6 optional bonus) and produce a structured test report with pass/fail classifications.

### Outcome

The AI-generated report incorrectly claimed that Task 6 was not implemented. It classified `query_user_loyalty_points` and `query_route_with_transfer_penalty` as missing, and marked the corresponding test cases as UNSUPPORTED.

We identified the error by checking `git status`. The terminal was on the branch `review/yichun-seeder-update6` instead of `task6/loyalty-transfer-rag-bonus`. The AI had tested against the wrong branch, where the Task 6 functions had not been merged yet.

After switching back to `task6/loyalty-transfer-rag-bonus`, we verified the functions directly:

- `Select-String` confirmed `query_route_with_transfer_penalty` exists in `databases/graph/queries.py`.
- `Select-String` confirmed `query_user_loyalty_points` and `execute_booking_with_loyalty_discount` exist in `databases/relational/queries.py`.
- Direct function calls confirmed both functions returned correct results at runtime.

We corrected the QA classifications:

- B5 (Task 6 Transfer Penalty): backend PASS, Agent PARTIAL (the Agent calls the tool but the lightweight LLM sometimes summarizes the penalty details imprecisely).
- C5 (Task 6 Loyalty Discount): PASS.

This example shows that AI output was not accepted without verification. Branch state, function existence, and runtime results all needed to be checked manually before the test report could be trusted.

## 5.6 How AI Output Was Reviewed

AI was useful for drafting documentation, implementing query functions, and planning test cases. However, we did not treat any AI output as final without checking it ourselves. Every AI suggestion was verified through a combination of: `git status` and branch checks, code search with `Select-String` or `grep`, `py_compile` for syntax validation, seed script execution, direct backend function calls with test parameters, and Agent debug output comparison. This review process caught errors (such as the wrong-branch QA report and the literal "any" seat bug) and prevented incorrect AI output from being merged into the project.