# 2. Normalisation Justification

## 2.1 First Normal Form

All tables store atomic values. Repeating groups such as schedule stops are separated into junction-style tables such as `metro_schedule_stops` and `nr_schedule_stops`.

## 2.2 Second Normal Form

Non-key attributes depend on the full primary key. For example, schedule stop data is separated from station data so that station names and schedule ordering do not depend on partial identifiers.

## 2.3 Third Normal Form

Transitive dependencies are minimized. User identity data, credentials, bookings, payments, stations, schedules, and seats are stored separately.

## 2.4 Design Trade-offs

The schema separates operational booking data from policy document embeddings. This improves data consistency and keeps vector search independent from transactional booking logic.