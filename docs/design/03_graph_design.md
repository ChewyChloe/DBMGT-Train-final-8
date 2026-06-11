# 3. Graph Database Design Rationale

## 3.1 Why Neo4j

TransitFlow uses Neo4j to model route connectivity because station-to-station travel naturally forms a graph. Graph traversal is better suited than relational joins for shortest routes, alternative paths, delay ripple analysis, and interchange routing.

## 3.2 Node Labels

The graph uses two main node labels:

- `MetroStation`
- `NationalRailStation`

Each station node stores station identifiers, station names, lines, and network-related metadata.

## 3.3 Relationship Types

The graph uses three main relationship types:

- `METRO_LINK`
- `RAIL_LINK`
- `INTERCHANGE_TO`

`METRO_LINK` represents metro station connectivity.  
`RAIL_LINK` represents national rail connectivity.  
`INTERCHANGE_TO` represents walking transfers between metro and national rail stations.

## 3.4 Query Functions

The implemented graph functions include:

- `query_station_connections`
- `query_delay_ripple`
- `query_shortest_route`
- `query_cheapest_route`
- `query_alternative_routes`
- `query_interchange_path`

## 3.5 Task 6 Extension

For Task 6, `INTERCHANGE_TO` relationships include:

- `transfer_wait_time_min`
- `crowd_penalty`

The function `query_route_with_transfer_penalty` calculates an adjusted route score using travel time, transfer waiting penalty, and crowding penalty.