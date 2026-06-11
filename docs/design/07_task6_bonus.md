# 7. Optional Bonus — Loyalty-Aware TransitFlow

## 7.1 Feature Name

**Loyalty-Aware TransitFlow: Membership Discounts, Transfer Penalties, and Policy RAG**

中文名稱：會員導向 TransitFlow：會員折扣、轉乘懲罰與政策 RAG 查詢

## 7.2 Motivation

The Task 6 extension demonstrates cross-database reasoning by combining PostgreSQL transactions, Neo4j route scoring, and RAG policy retrieval.

## 7.3 PostgreSQL Loyalty Points Discount

PostgreSQL stores loyalty point balances in `user_loyalty_points`.

The function `query_user_loyalty_points` retrieves a user's current point balance.

The function `execute_booking_with_loyalty_discount` applies the rule:

- 100 points = 1.00 USD discount
- maximum discount per booking = 1.00 USD
- points are updated in the same transaction as booking and payment creation

Example result:

- original fare: 8.50 USD
- points before: 120
- points used: 100
- discount: 1.00 USD
- final amount: 7.50 USD
- points after: 20

## 7.4 Neo4j Transfer Waiting Penalty

Task 6 adds transfer penalty properties to `INTERCHANGE_TO` relationships:

- `transfer_wait_time_min`
- `crowd_penalty`

The function `query_route_with_transfer_penalty` returns:

- route
- base time
- transfer waiting penalty
- crowd penalty
- adjusted score

## 7.5 RAG Membership Policy

Task 6 adds `membership_policy.json`, which allows RAG to answer questions such as:

- How do loyalty points work?
- How many points are needed for a discount?
- What is the transfer waiting penalty?

## 7.6 Agent Integration

The Agent includes Task 6 tools:

- `check_loyalty_points`
- `book_with_loyalty_discount`
- `route_with_transfer_penalty`

## 7.7 Known Limitation

The backend Task 6 tools return correct structured results. However, the Agent's final natural-language answer may occasionally summarize tool outputs imperfectly. Debug mode should be used to verify actual tool calls and raw results.