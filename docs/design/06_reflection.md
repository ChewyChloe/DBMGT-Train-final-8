# 6. Reflection and Trade-offs

## 6.1 Design decision 1: PostgreSQL for Transactional Booking Data

We chose PostgreSQL as the primary store for users, credentials, schedules, fares, seats, bookings, payments, feedback, and Task 6 loyalty points. The main reason is transaction safety. Booking a national rail ticket involves multiple writes: inserting a row into `nr_bookings`, inserting a corresponding row into `payments`, and (for Task 6) deducting loyalty points from `user_loyalty_points`. All of these must succeed together or fail together.

A concrete example is `execute_booking_with_loyalty_discount`. This function opens a single PostgreSQL transaction, locks the user's loyalty row with `FOR UPDATE`, validates the schedule and seat, calculates the discounted fare, inserts the booking and payment, updates the point balance, and then commits. If any step fails (for example, the requested seat is already booked), the entire transaction rolls back and no data is left in an inconsistent state. Without transactional guarantees, it would be possible to deduct loyalty points without actually creating the booking.

Foreign keys also help here. A booking cannot reference a non-existent user or schedule because the schema enforces referential integrity at the database level. The CHECK constraints on `payments` and `feedback` (the exclusive-OR pattern) ensure each record links to exactly one booking type.

The cost is that schema changes need more planning. Relational schemas require more upfront design than a document store, and adding new columns or tables takes more planning. For this project that was acceptable because the data model was well-defined by the task specification before we started coding.

## 6.2 Design decision 2: Neo4j for Routing Instead of SQL

We used Neo4j for station connectivity and route queries rather than implementing routing in PostgreSQL with recursive CTEs or repeated self-joins. The station network is naturally graph-shaped: metro and national rail stations are nodes, track segments and interchanges are edges, and each edge carries properties like travel time, fare cost, and line name.

Neo4j made it straightforward to implement seven distinct routing functions: `query_station_connections`, `query_shortest_route`, `query_cheapest_route`, `query_alternative_routes`, `query_interchange_path`, `query_delay_ripple`, and the Task 6 extension `query_route_with_transfer_penalty`. The interchange path function, for example, finds routes that cross from metro to national rail (or vice versa) through `INTERCHANGE_TO` edges. Writing this as a Cypher query with variable-length path traversal is natural. Doing the same in SQL would require multiple recursive CTEs or stored procedures, and the logic would be harder to read and maintain.

The Task 6 transfer penalty function adds `transfer_wait_time_min` and `crowd_penalty` properties to `INTERCHANGE_TO` edges. The route query reads these relationship properties and calculates an adjusted score for the route. For the test case MS01 to NR05, it returns the route MS01, MS07, NR03, NR05 with a base travel time of 37 minutes, a transfer wait penalty of 4.0 minutes, a crowd penalty of 0.5, and an adjusted score of 41.5.

The trade-off is data duplication. Station names and IDs exist in both PostgreSQL and Neo4j. We use the same VARCHAR business keys (MS01, NR01, etc.) in both databases to keep them aligned. The seeding scripts (`seed_postgres.py` and `seed_neo4j.py`) both read from the same JSON mock data files, which helps prevent drift. But if a station name changed in one database and not the other, the system would show inconsistent results. In a longer-lived project, we would need a single source of truth with synchronization logic.

## 6.3 Design decision 3: RAG Policy Documents with pgvector

Policy questions from users do not always use exact keywords. Someone asking "what happens if I lose something on the train" should match the lost-and-found policy even though the word "lost-and-found" does not appear in the question. We stored policy documents as text chunks with 768-dimensional vector embeddings in PostgreSQL using the pgvector extension and Ollama's `nomic-embed-text` model. The `query_policy_vector_search` function computes cosine similarity between the user's question embedding and stored document embeddings, returning the top-k most relevant chunks.

After adding the Task 6 membership policy file (`membership_policy.json`), the system stores 75 policy documents covering refund rules, booking policies, conduct guidelines, ticket information, and membership/loyalty rules. When the Agent receives a policy question, it embeds the question, retrieves relevant chunks, and passes them as context to the LLM for answer generation.

The trade-off is that flattened text chunks work well for retrieval but are less useful for structured analysis. If we needed to programmatically extract specific numbers (such as "the refund percentage for cancellations within 24 hours"), we would need to parse free text rather than query a structured field. For this project, the retrieval use case is the primary one, so the trade-off is acceptable.

## 6.4 Design decision 4: Task 6 as Additive Extensions

For Task 6, we added new functions rather than modifying existing ones. `execute_booking_with_loyalty_discount` was added alongside the original `execute_booking`. `query_route_with_transfer_penalty` was added alongside `query_cheapest_route` and `query_shortest_route`. The membership policy file was added as a new JSON source for the vector seeder without changing existing policy files.

The reasoning was practical. By the time we started Task 6, the core backend tests had already passed. Rewriting existing functions would have risked breaking previously working features close to submission. Adding separate functions let us develop and test the Task 6 logic independently. The agent tool definitions simply gained new tools pointing to the new functions.

The trade-off is some duplicated logic between the original and extended functions. For example, `execute_booking_with_loyalty_discount` repeats much of the fare calculation and seat validation logic from `execute_booking`. In a production system, we would refactor the shared logic into internal helper functions. For this project, the safer separation was worth the duplication.

## 6.5 What Would Change in a Production System

### Schema Migrations

In this project, we manage schema changes by editing `schema.sql` and re-creating the Docker volume from scratch. This works for local development but would not work in production where the database contains real user data. A production system would use a migration tool such as Alembic (for Python/SQLAlchemy) or Flyway. Each schema change would be versioned as a migration file, applied incrementally, and reversible. This matters because dropping and re-creating tables would destroy production data.

### Secret Management

Database passwords and the Neo4j credentials are currently stored in `.env` files and `docker-compose.yml`. For local development this is fine, but in production these secrets should not sit in files that could be accidentally committed or shared. A production deployment would use a secret manager (such as AWS Secrets Manager, HashiCorp Vault, or platform-level environment secrets) to inject credentials at runtime without exposing them in the codebase.

### Connection Pooling

The current query functions open a new `psycopg2` connection for each request and close it after the query. Under concurrent load, this would exhaust the database's connection limit quickly. A production system would use connection pooling (for example, `psycopg2.pool` or an external pooler like PgBouncer) to reuse connections across requests and limit the total number of active connections.

### Agent Response Grounding

The backend tools return structured JSON results, but the local lightweight LLM (llama3.2:1b) sometimes summarizes these results imperfectly in its natural-language response. For example, it might round a fare incorrectly or omit a transfer penalty detail. In production, critical outputs like fares, refund amounts, and route details should use deterministic formatting templates rather than relying entirely on LLM paraphrasing. A stronger model would also help, but even with a better LLM, structured validation of the final response against the tool output would reduce the risk of contradicting backend data.

## 6.6 Final Reflection

The main lesson from this project was that different data models are good at different things, and trying to force everything into one database would have made parts of the system much harder to build. PostgreSQL handled transactions and referential integrity well. Neo4j made route traversal simple and expressive. pgvector gave us flexible policy search without writing a dedicated SQL query for every policy topic.

The hardest part was not any single database layer. It was integration: making the Agent select the right tool, pass correct parameters, and present backend results faithfully. The lightweight local LLM occasionally misinterpreted structured outputs, which meant we relied on debug mode to verify that the backend was returning correct data even when the Agent's summary was imperfect. If we had more time, improving the Agent's response grounding and adding express-only route filtering and fewest-transfer optimization would be the next priorities.