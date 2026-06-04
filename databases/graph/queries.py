"""
Neo4j Graph Database Query Functions
=====================================
Module: databases/graph/queries.py

Purpose: Implement 6 query functions for querying Neo4j graph data

Functions:
  1. query_station_connections() - Query all connections of a station
  2. query_delay_ripple() - Query the impact range of a delay
  3. query_shortest_route() - Query shortest path (core feature)
  4. query_alternative_routes() - Query alternative routes
  5. query_interchange_path() - Query cross-system interchange routes
  6. query_cheapest_route() - Query cheapest route
"""

from neo4j import GraphDatabase
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:8001")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow2026")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


# ============================================================================
# 1. query_station_connections() - Query all connections of a station
# ============================================================================

def query_station_connections(station_id: str) -> Dict:
    """
    Query all connections of a given station.

    Args:
        station_id: Station ID (e.g. "MS01")

    Returns:
        {
            "station_id": "MS01",
            "station_name": "Central Square",
            "connections": [
                {
                    "to_station_id": "MS02",
                    "to_station_name": "Station 2",
                    "line": "M1",
                    "travel_time_min": 3,
                    "type": "metro"
                }
            ],
            "total_connections": 1
        }
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (s)-[r]->(connected)
                WHERE s.station_id = $station_id
                RETURN 
                    s.station_id as station_id,
                    s.name as station_name,
                    connected.station_id as to_station_id,
                    connected.name as to_station_name,
                    r.line as line,
                    r.travel_time_min as travel_time_min,
                    type(r) as relationship_type
            """, station_id=station_id)

            records = list(result)

            if not records:
                return {
                    "station_id": station_id,
                    "station_name": "Unknown",
                    "connections": [],
                    "total_connections": 0,
                    "error": "Station not found"
                }

            station_data = records[0]
            connections = []

            for record in records:
                relationship_type = record.get("relationship_type")
                if relationship_type == "METRO_LINK":
                    conn_type = "metro"
                elif relationship_type == "RAIL_LINK":
                    conn_type = "rail"
                elif relationship_type == "INTERCHANGE_TO":
                    conn_type = "interchange"
                else:
                    conn_type = "unknown"

                connections.append({
                    "to_station_id": record.get("to_station_id"),
                    "to_station_name": record.get("to_station_name"),
                    "line": record.get("line", "N/A"),
                    "travel_time_min": record.get("travel_time_min", 0),
                    "type": conn_type
                })

            return {
                "station_id": station_data.get("station_id"),
                "station_name": station_data.get("station_name"),
                "connections": connections,
                "total_connections": len(connections)
            }

    except Exception as e:
        return {
            "station_id": station_id,
            "error": f"Query failed: {str(e)}"
        }


# ============================================================================
# 2. query_delay_ripple() - Query the impact range of a delay
# ============================================================================

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> List[Dict]:
    """
    Query which stations are affected when a given station is delayed.
    Uses APOC subgraphNodes to expand outward from the delayed station.

    Args:
        delayed_station_id: ID of the delayed station (e.g. "MS05")
        hops: Number of hops to propagate the delay (default 2)
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (center {station_id: $delayed_station})
                CALL apoc.path.subgraphNodes(center, {
                    maxLevel: $hops,
                    relationshipFilter: 'METRO_LINK|RAIL_LINK'
                })
                YIELD node
                WITH node
                WHERE node.station_id <> $delayed_station
                RETURN
                    node.station_id as station_id,
                    node.name as station_name,
                    node.lines as lines
                ORDER BY station_id
            """, delayed_station=delayed_station_id, hops=hops)

            records = list(result)
            affected_stations = []

            for record in records:
                affected_stations.append({
                    "station_id": record.get("station_id"),
                    "station_name": record.get("station_name"),
                    "affected_lines": record.get("lines", [])
                })

            return affected_stations

    except Exception as e:
        return [{"error": f"Query failed: {str(e)}"}]


# ============================================================================
# 3. query_shortest_route() - Query shortest path by travel time
# ============================================================================

def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> Dict:
    """
    Query the time-shortest path between two stations using Dijkstra algorithm.

    Args:
        origin_id: Origin station ID (e.g. "MS01")
        destination_id: Destination station ID (e.g. "MS10")
        network: "auto" / "metro" / "rail"
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (origin {station_id: $origin_id})
                MATCH (destination {station_id: $destination_id})
                CALL apoc.algo.dijkstra(origin, destination, 
                    'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 
                    'travel_time_min')
                YIELD path, weight
                RETURN path, weight
            """, origin_id=origin_id, destination_id=destination_id)

            record = next(result, None)

            if not record:
                return {
                    "origin": {"station_id": origin_id},
                    "destination": {"station_id": destination_id},
                    "route": [],
                    "error": "No path found"
                }

            path = record.get("path")
            total_time = record.get("weight", 0)
            nodes = list(path.nodes)
            relationships = list(path.relationships)

            route = []
            lines_used = set()

            for node in nodes:
                route.append({
                    "station_id": node.get("station_id"),
                    "station_name": node.get("name"),
                    "lines": node.get("lines", [])
                })

            for rel in relationships:
                if rel.get("line"):
                    lines_used.add(rel.get("line"))

            return {
                "origin": {
                    "station_id": nodes[0].get("station_id"),
                    "station_name": nodes[0].get("name")
                },
                "destination": {
                    "station_id": nodes[-1].get("station_id"),
                    "station_name": nodes[-1].get("name")
                },
                "route": route,
                "total_time_min": int(total_time),
                "num_stops": len(nodes),
                "transfers": sum(1 for r in relationships if r.type == "INTERCHANGE_TO"),
                "lines_used": list(lines_used)
            }

    except Exception as e:
        return {
            "origin": {"station_id": origin_id},
            "destination": {"station_id": destination_id},
            "error": f"Query failed: {str(e)}"
        }


# ============================================================================
# 4. query_alternative_routes() - Query alternative routes avoiding a station
# ============================================================================

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3
) -> List[Dict]:
    """
    Query alternative routes when a station is closed.
    Uses Dijkstra algorithm excluding the specified station.

    Args:
        origin_id: Origin station ID
        destination_id: Destination station ID
        avoid_station_id: Station ID to avoid
        max_routes: Maximum number of routes to return
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (origin {station_id: $origin_id})
                MATCH (destination {station_id: $destination_id})
                MATCH (avoid {station_id: $avoid_station_id})
                CALL apoc.algo.dijkstra(origin, destination,
                    'METRO_LINK|RAIL_LINK|INTERCHANGE_TO',
                    'travel_time_min')
                YIELD path, weight
                WHERE none(n IN nodes(path) WHERE n.station_id = $avoid_station_id)
                RETURN path, weight
                LIMIT $max_routes
            """,
            origin_id=origin_id,
            destination_id=destination_id,
            avoid_station_id=avoid_station_id,
            max_routes=max_routes)

            records = list(result)

            if not records:
                return [{"error": f"No alternative route found avoiding {avoid_station_id}"}]

            alternatives = []

            for rank, record in enumerate(records, 1):
                path = record.get("path")
                total_time = record.get("weight", 0)
                nodes = list(path.nodes)
                relationships = list(path.relationships)

                route = []
                lines_used = set()

                for node in nodes:
                    route.append({
                        "station_id": node.get("station_id"),
                        "station_name": node.get("name")
                    })

                for rel in relationships:
                    if rel.get("line"):
                        lines_used.add(rel.get("line"))

                alternatives.append({
                    "rank": rank,
                    "route": route,
                    "total_time_min": int(total_time),
                    "num_stops": len(nodes),
                    "lines_used": list(lines_used),
                    "avoided_station": avoid_station_id
                })

            return alternatives

    except Exception as e:
        return [{"error": f"Query failed: {str(e)}"}]


# ============================================================================
# 5. query_interchange_path() - Query cross-system interchange route
# ============================================================================

def query_interchange_path(origin_id: str, destination_id: str) -> Dict:
    """
    Query cross-system interchange route (Metro <-> National Rail).
    Uses Dijkstra algorithm weighted by travel_time_min.

    Args:
        origin_id: Origin station ID (any type)
        destination_id: Destination station ID (any type)
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (origin {station_id: $origin_id})
                MATCH (destination {station_id: $destination_id})
                CALL apoc.algo.dijkstra(origin, destination,
                    'METRO_LINK|RAIL_LINK|INTERCHANGE_TO',
                    'travel_time_min')
                YIELD path, weight
                RETURN path, weight
            """, origin_id=origin_id, destination_id=destination_id)

            record = next(result, None)

            if not record:
                return {
                    "origin": {"station_id": origin_id},
                    "destination": {"station_id": destination_id},
                    "error": "No interchange path found"
                }

            path = record.get("path")
            total_time = record.get("weight", 0)
            nodes = list(path.nodes)
            relationships = list(path.relationships)

            metro_part = []
            rail_part = []
            interchange_info = None
            current_part = "metro"

            for i, node in enumerate(nodes):
                station = {
                    "station_id": node.get("station_id"),
                    "station_name": node.get("name"),
                    "lines": node.get("lines", [])
                }

                if i > 0 and relationships[i - 1].type == "INTERCHANGE_TO":
                    current_part = "rail"
                    interchange_info = {
                        "from_station_id": nodes[i - 1].get("station_id"),
                        "from_station_name": nodes[i - 1].get("name"),
                        "to_station_id": node.get("station_id"),
                        "to_station_name": node.get("name"),
                        "walk_time_min": int(relationships[i - 1].get("travel_time_min", 5))
                    }

                if current_part == "metro":
                    metro_part.append(station)
                else:
                    rail_part.append(station)

            return {
                "origin": {
                    "station_id": nodes[0].get("station_id"),
                    "station_name": nodes[0].get("name")
                },
                "destination": {
                    "station_id": nodes[-1].get("station_id"),
                    "station_name": nodes[-1].get("name")
                },
                "metro_part": metro_part,
                "interchange": interchange_info if interchange_info else {},
                "rail_part": rail_part,
                "total_time_min": int(total_time),
                "total_stops": len(nodes),
                "transfers": 1 if interchange_info else 0
            }

    except Exception as e:
        return {
            "origin": {"station_id": origin_id},
            "destination": {"station_id": destination_id},
            "error": f"Query failed: {str(e)}"
        }


# ============================================================================
# 6. query_cheapest_route() - Query cheapest route by fare
# ============================================================================

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard"
) -> Dict:
    """
    Query the cheapest route using Dijkstra algorithm weighted by per_stop_rate_usd.

    Args:
        origin_id: Origin station ID
        destination_id: Destination station ID
        fare_class: "standard" / "first"
    """
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (origin {station_id: $origin_id})
                MATCH (destination {station_id: $destination_id})
                CALL apoc.algo.dijkstra(origin, destination,
                    'METRO_LINK|RAIL_LINK|INTERCHANGE_TO',
                    'per_stop_rate_usd')
                YIELD path, weight
                RETURN path, weight
            """, origin_id=origin_id, destination_id=destination_id)

            record = next(result, None)

            if not record:
                return {
                    "origin": {"station_id": origin_id},
                    "destination": {"station_id": destination_id},
                    "error": "No route found"
                }

            path = record.get("path")
            total_cost = record.get("weight", 0)
            nodes = list(path.nodes)
            relationships = list(path.relationships)

            route = []
            lines_used = set()

            for node in nodes:
                route.append({
                    "station_id": node.get("station_id"),
                    "station_name": node.get("name")
                })

            for rel in relationships:
                if rel.get("line"):
                    lines_used.add(rel.get("line"))

            return {
                "origin": {
                    "station_id": nodes[0].get("station_id"),
                    "station_name": nodes[0].get("name")
                },
                "destination": {
                    "station_id": nodes[-1].get("station_id"),
                    "station_name": nodes[-1].get("name")
                },
                "route": route,
                "total_cost_usd": round(float(total_cost), 2),
                "total_time_min": None,
                "num_stops": len(nodes),
                "fare_class": fare_class,
                "lines_used": list(lines_used)
            }

    except Exception as e:
        return {
            "origin": {"station_id": origin_id},
            "destination": {"station_id": destination_id},
            "error": f"Query failed: {str(e)}"
        }


# ============================================================================
# Test function (optional)
# ============================================================================

def test_queries():
    """
    Test all query functions.
    Run this function to verify queries are working correctly.
    """
    print("=" * 60)
    print("Testing Neo4j Query Functions")
    print("=" * 60)

    print("\n1. Testing query_station_connections()...")
    result = query_station_connections("MS01")
    print(f"   Connections: {result.get('total_connections')}")

    print("\n2. Testing query_delay_ripple()...")
    result = query_delay_ripple("MS05", hops=2)
    print(f"   Affected stations: {len(result)}")

    print("\n3. Testing query_shortest_route()...")
    result = query_shortest_route("MS01", "MS10")
    print(f"   Route found: {result.get('num_stops')} stops, {result.get('total_time_min')} min")

    print("\n4. Testing query_alternative_routes()...")
    result = query_alternative_routes("MS01", "MS10", "MS05")
    print(f"   Alternative routes found: {len(result)}")

    print("\n5. Testing query_interchange_path()...")
    result = query_interchange_path("MS01", "NR05")
    print(f"   Interchange path: {result.get('total_stops')} stops")

    print("\n6. Testing query_cheapest_route()...")
    result = query_cheapest_route("MS01", "MS10")
    print(f"   Cheapest route: ${result.get('total_cost_usd')}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    test_queries()