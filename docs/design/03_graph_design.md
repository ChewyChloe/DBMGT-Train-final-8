# 3. Graph Database Design Rationale

## 3.1 Why Neo4j

TransitFlow uses Neo4j to model route connectivity because station-to-station travel naturally forms a graph. Graph traversal is better suited than relational joins for shortest routes, alternative paths, delay ripple analysis, and interchange routing. Neo4j's native support for APOC procedures also enables efficient Dijkstra pathfinding and subgraph expansion without complex application-level logic.

## 3.2 Node Labels

The graph uses two node labels:

**`MetroStation`**
Represents city metro stations. Properties:
- `station_id` (String, unique) — e.g. `MS01`
- `name` (String) — station display name
- `lines` (List[String]) — metro lines serving this station

**`NationalRailStation`**
Represents national rail stations. Properties:
- `station_id` (String, unique) — e.g. `NR01`
- `name` (String) — station display name
- `lines` (List[String]) — rail lines serving this station

## 3.3 Relationship Types

**`METRO_LINK`** — `MetroStation → MetroStation`
Represents direct connections between adjacent metro stations.
Properties:
- `line` (String) — metro line identifier
- `travel_time_min` (Integer) — travel time in minutes
- `per_stop_rate_usd` (Float) — fixed fare rate of `0.5` per stop

**`RAIL_LINK`** — `NationalRailStation → NationalRailStation`
Represents direct connections between adjacent national rail stations.
Properties:
- `line` (String) — rail line identifier
- `service_type` (String) — e.g. `express` or `normal`
- `travel_time_min` (Integer) — travel time in minutes
- `per_stop_rate_usd` (Float) — standard fare rate per stop
- `per_stop_rate_usd_first` (Float) — first class fare rate (standard × 5/3)

**`INTERCHANGE_TO`** — `MetroStation ↔ NationalRailStation`
Represents walking transfers between metro and national rail stations. Created bidirectionally.
Properties:
- `travel_time_min` (Integer) — walking time between systems
- `per_stop_rate_usd` (Float) — `0.0` (no fare charged for interchange)
- `transfer_wait_time_min` (Integer) — waiting buffer at interchange (Task 6)
- `crowd_penalty` (Float) — congestion penalty at busy interchanges (Task 6)

## 3.4 Query Functions

| Function | Algorithm | Description |
|----------|-----------|-------------|
| `query_station_connections` | Direct match | Returns all direct neighbours of a given station with line and travel time |
| `query_delay_ripple` | APOC `subgraphNodes` | Returns all stations within N hops of a delayed station, including hop distance |
| `query_shortest_route` | APOC Dijkstra (`travel_time_min`) | Finds the time-optimal path between two stations across both networks |
| `query_cheapest_route` | APOC Dijkstra (`per_stop_rate_usd`) | Finds the lowest-fare path, with support for standard and first class |
| `query_alternative_routes` | Path expansion | Finds up to N paths avoiding a specified closed or disrupted station |
| `query_interchange_path` | APOC Dijkstra (`travel_time_min`) | Finds cross-network routes that cross the metro–rail boundary via `INTERCHANGE_TO` |

## 3.5 Task 6 Extension

For Task 6, `INTERCHANGE_TO` relationships were extended with two additional properties: `transfer_wait_time_min` and `crowd_penalty`. These are seeded during graph initialisation with the following fixed values:

| Station | Station IDs | `crowd_penalty` |
|---------|-------------|-----------------|
| Central Station (primary hub) | `MS01` / `NR01` | 1.5 min |
| Other interchange stations | e.g. `MS07` / `NR03`, `MS15` / `NR07` | 0.5 min |

A fixed `transfer_wait_time_min` of **4 minutes** is applied to all interchange relationships to account for platform walking overhead and service latency between the City Metro and National Rail networks.

The function `query_route_with_transfer_penalty` builds on the standard Dijkstra shortest path and applies transfer penalties on the Python side. The adjusted score is calculated as:

```
adjusted_score = base_time_min + transfer_wait_penalty_min + crowd_penalty
```

This design keeps the core routing queries unchanged while allowing Task 6 penalty logic to be layered on top without modifying the graph schema.
