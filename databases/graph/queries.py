"""
Neo4j Graph Database Query Functions
=====================================
Module: databases/graph/queries.py

Purpose: 实现 6 个查询函数，用来查询 Neo4j 中的图形数据

Functions:
  1. query_station_connections() - 查询某个站的所有连接
  2. query_delay_ripple() - 查询延误的影响范围
  3. query_shortest_route() - 查询最短路径（核心功能）
  4. query_alternative_routes() - 查询替代路线
  5. query_interchange_path() - 查询跨系统转乘路线
  6. query_cheapest_route() - 查询最便宜路线

Note: 这是第一版本，可运行，之后可根据需要改进
"""

from neo4j import GraphDatabase
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 读取配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:8001")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow2026")

# 创建 driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


# ============================================================================
# 1️⃣ query_station_connections() - 查询某个站的所有连接
# ============================================================================

def query_station_connections(station_id: str) -> Dict:
    """
    查询某个车站的所有连接
    
    Args:
        station_id: 车站 ID（例如 "MS01"）
    
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
            # 查询该站的所有连接
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
            
            # 解析结果
            station_data = records[0]
            connections = []
            
            for record in records:
                # 判断连接类型
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
# 2️⃣ query_delay_ripple() - 查询延误影响范围
# ============================================================================

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> List[Dict]:
    """
    查询某个车站延误时，影响周围多少个车站
    使用 APOC subgraphNodes 从延误站向外扩散
    
    Args:
        delayed_station_id: 延误的车站 ID（例如 "MS05"）
        hops: 延误传播的跳数（默认 2）
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
# 3️⃣ query_shortest_route() - 查询最短路径（最重要）
# ============================================================================

def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> Dict:
    """
    查询两个车站之间时间最短的路径（使用 Dijkstra 演算法）
    
    Args:
        origin_id: 起始站 ID（例如 "MS01"）
        destination_id: 目标站 ID（例如 "MS10"）
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
# 4️⃣ query_alternative_routes() - 查询替代路线
# ============================================================================

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3
) -> List[Dict]:
    """
    查询替代路线（当某个站关闭时）
    使用 Dijkstra 演算法，排除指定车站后找最短时间路线
    
    Args:
        origin_id: 起始站
        destination_id: 目标站
        avoid_station_id: 要避开的站
        max_routes: 最多返回几条路线
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
# 5️⃣ query_interchange_path() - 查询跨系统转乘路线（最复杂）
# ============================================================================

def query_interchange_path(origin_id: str, destination_id: str) -> Dict:
    """
    查询跨系统转乘路线（Metro ↔ National Rail）
    使用 Dijkstra 演算法，以 travel_time_min 为权重
    
    Args:
        origin_id: 起始站（可以是任何类型）
        destination_id: 目标站（可以是任何类型）
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

            # 找到轉乘點，分割 metro 和 rail 兩段
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

                # 檢查前一條關係是不是 INTERCHANGE_TO
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
# 6️⃣ query_cheapest_route() - 查询最便宜路线
# ============================================================================

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard"
) -> Dict:
    """
    查询最便宜路线
    使用 Dijkstra 演算法，以 per_stop_rate_usd 為權重找最低費用路線
    
    Args:
        origin_id: 起始站
        destination_id: 目标站
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
# 测试函数（可选）
# ============================================================================

def test_queries():
    """
    测试所有查询函数
    运行这个函数来验证查询是否正常工作
    """
    print("=" * 60)
    print("Testing Neo4j Query Functions")
    print("=" * 60)
    
    # 测试 1：查询连接
    print("\n1. Testing query_station_connections()...")
    result = query_station_connections("MS01")
    print(f"   Connections: {result.get('total_connections')}")
    
    # 测试 2：延误影响
    print("\n2. Testing query_delay_ripple()...")
    result = query_delay_ripple("MS05", hops=2)
    print(f"   Affected stations: {len(result)}")
    
    # 测试 3：最短路径
    print("\n3. Testing query_shortest_route()...")
    result = query_shortest_route("MS01", "MS10")
    print(f"   Route found: {result.get('num_stops')} stops, {result.get('total_time_min')} min")
    
    # 测试 4：替代路线
    print("\n4. Testing query_alternative_routes()...")
    result = query_alternative_routes("MS01", "MS10", "MS05")
    print(f"   Alternative routes found: {len(result)}")
    
    # 测试 5：跨系统转乘
    print("\n5. Testing query_interchange_path()...")
    result = query_interchange_path("MS01", "NR05")
    print(f"   Interchange path: {result.get('total_stops')} stops")
    
    # 测试 6：最便宜路线
    print("\n6. Testing query_cheapest_route()...")
    result = query_cheapest_route("MS01", "MS10")
    print(f"   Cheapest route: ${result.get('total_cost_usd')}")
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    # 如果直接运行这个脚本，就执行测试
    test_queries()