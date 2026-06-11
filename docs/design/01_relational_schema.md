# 1. Entity-Relationship Diagram and Relational Schema

## 1.1 Overview

TransitFlow uses PostgreSQL as the relational database for structured operational data, including users, credentials, stations, schedules, seats, bookings, payments, feedback, and policy document embeddings.

## 1.2 Main Entities

The main relational entities include:

- `registered_users`
- `user_credentials`
- `metro_stations`
- `national_rail_stations`
- `metro_schedules`
- `metro_schedule_stops`
- `nr_schedules`
- `nr_schedule_stops`
- `nr_fare_classes`
- `nr_seats`
- `nr_bookings`
- `payments`
- `feedback`
- `policy_documents`
- `user_loyalty_points` for Task 6

## 1.3 Relationships

Key relationships include:

- One registered user has one credential record.
- One user can have many national rail bookings.
- One national rail schedule has many schedule stops.
- One booking can have one payment.
- One user can have one loyalty points record in the Task 6 extension.

## 1.4 Integrity Constraints

The schema uses primary keys, foreign keys, unique constraints, and check constraints to preserve data consistency.