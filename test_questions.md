# TransitFlow Project — RAG & Database QA Test Suite

This document contains 15 standardized evaluation queries designed to test the correctness, retrieval recall, and multi-database reasoning capabilities of the TransitFlow system.

---

## 🛑 Category A: Policy & Conduct (RAG / Vector Search Focus)
*These questions evaluate the system's ability to retrieve semantic context from parsed unstructured/semi-structured policy JSON documents via pgvector.*

1. **Emergency Response (Metro)**  
   If a passenger suddenly feels very unwell or dizzy while in a moving metro, what action should he/she take immediately to notify staff, according to the policy?
   * **Expected Test Path:** Validates vector recall against `travel_policies.json` (Conduct category) to retrieve official passenger emergency workflows.

2. **Maintenance Disruption**  
   According to the official travel policy document, what is the refund rule if a train service is canceled or suspended due to maintenance?
   * **Expected Test Path:** Validates vector recall against `refund_policy.json` under the `maintenance_rules` section.

3. **Ticket Change Window**  
   If a passenger wants to change their express train ticket 12 hours before departure, can they do so?
   * **Expected Test Path:** Hits `refund_policy.json` or `booking_rules.json` to query strict time-window boundaries.

4. **Pass Cancellation (Multi-day)**  
   If a passenger buys a monthly MRT pass, uses it for two days, and then wants to cancel it, how much of a refund can they expect?
   * **Expected Test Path:** Evaluates RAG retrieval of multi-day ticket types and partial-use cancellation rules inside `ticket_types.json`.

5. **Accessibility / Guide Dogs**  
   I am visually impaired. Can I bring a guide dog on the train?
   * **Expected Test Path:** Matches `travel_policies.json` passenger guidelines regarding accessibility accommodation rules.

6. **Pass Cancellation (Single-day)**  
   A passenger purchased a one-day MRT pass, intending to use it on the same day, but later had to cancel and didn't use the pass at any MRT station that day. How much money can the passenger expect to receive if they apply for a refund two days later?
   * **Expected Test Path:** Verifies retrieval of strict un-utilized single-day pass refund parameters and expiration timelines.

---

## 🗺️ Category B: Network Routing & Impact Analysis (Graph DB / Neo4j Focus)
*These questions evaluate graph traversal, service type filtering, and bidirectional interchange routing via Cypher queries.*

7. **Delay Propagation & Blast Radius**  
   If Metro Station `MS01` is delayed, which adjacent stations connected via `METRO_LINK` will be immediately affected?  
   * **Expected Test Path:** Evaluates whether the agent queries `(:MetroStation {station_id: 'MS01'})-[:METRO_LINK]->()` to map downstream dependencies.

8. **Alternative Pathfinding under Disruption**  
   If Metro Station `MS05` is currently closed due to maintenance, can you find up to 3 alternative metro routes to travel from `MS01` to `MS10`?  
   * **Expected Test Path:** Tests shortest path or path enumeration algorithms (e.g., `query_alternative_routes`) while filtering out `MS05` from the graph nodes.

9. **Cross-System Intermodal Routing**  
   What is the fastest route to travel from Metro Station `MS01` to National Rail Station `NR05`? Please include walking/interchange times.  
   * **Expected Test Path:** Validates if the graph agent correctly traverses the bidirectional `[:INTERCHANGE_TO]` relationship to bridge `(:MetroStation)` and `(:NationalRailStation)`.

10. **Service Type Filtering (Express vs Normal)**  
    Can you find a route from National Rail Station `NR01` to `NR08` that exclusively uses express services?  
    * **Expected Test Path:** Verifies relationship property filtering on `-[r:RAIL_LINK]->` where `r.service_type = 'express'`.

---

## 🧮 Category C: Fares & Timetables (Relational DB / PostgreSQL Focus)
*These questions evaluate SQL execution accuracy regarding precise joins, aggregates, and time-based filtering on immutable seed data.*

11. **Single Fare Lookup**  
    How much does a single ticket cost to travel from Harbour View to Maplewood using standard class?
    * **Expected Test Path:** Tests basic relational join querying station lookups against static tariff pricing matrices.

12. **Schedule Filtering**  
    I need to travel from Central Station to Ashford tomorrow morning. Which national rail trains are available before 10:00 AM?
    * **Expected Test Path:** Validates SQL `WHERE` clause generation applying strict time bounds (`departure_time < '10:00:00'`) and calendar date scheduling logic.

13. **Route Optimization (Fewest Line Transfers)**  
    What is the route from Central Square to Thornton that has the fewest line transfers, and how long does it take?
    * **Expected Test Path:** Tests SQL optimization queries or path aggregation analyzing line-grouping identifiers across consecutive route segments.

---

## ⚖️ Category D: Advanced Mixed Reasoning (Hybrid SQL + Graph / Hybrid RAG + DB)
*These edge cases test complex conditions where the LLM Agent must synthesize knowledge from text policies alongside graph database metrics.*

14. **No-Show Penalty & Partial Refund Eligibility**  
    What is the penalty if I miss my scheduled national rail train and fail to show up on time? Can I still get a refund, or am I eligible for a partial refund if I decide not to make the return journey on a round-trip ticket?
    * **Expected Test Path:** Hybrid RAG reasoning mapping `refund_policy.json` structural rules (combining `no_show_policy` and `return_ticket_notes`) to user booking states.

15. **Cross-Class Graph Fare Differential**  
    How much more does it cost to travel from `NR02` (Old Town Junction) to `NR06` (Maplewood) in first class compared to standard class based on the cumulative edge rates?  
    * 15. **Cross-Class Graph Fare Differential** How much more does it cost to travel from `NR02` (Old Town Junction) to `NR06` (Maplewood) in first class compared to standard class based on the cumulative edge rates?   
    * **Expected Test Path:** Multi-DB verification. Validates if the agent can either compound Graph edge properties (`r.per_stop_rate_usd` vs `r.per_stop_rate_usd_first`) over the traversed `RAIL_LINK` path, OR correctly join relational tariff metrics (`per_stop_rate_usd` filtered by `fare_class`) to cross-reference the math.