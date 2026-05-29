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
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

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
    
    Args:
        delayed_station_id: 延误的车站 ID（例如 "MS05"）
        hops: 延误传播的跳数（默认 2）
    
    Returns:
        [
            {
                "station_id": "MS04",
                "station_name": "Adjacent Station",
                "hops_from_delay": 1,
                "affected_lines": ["M1", "M2"]
            }
        ]
    """
    try:
        with driver.session() as session:
            # 查询延误影响的范围
            result = session.run(f"""
                MATCH (center)-[*1..{hops}]-(affected)
                WHERE center.station_id = $delayed_station
                AND affected.station_id <> $delayed_station
                RETURN 
                    affected.station_id as station_id,
                    affected.name as station_name,
                    affected.lines as lines,
                    length(shortestPath((center)-[*]-(affected))) as hop_count
                ORDER BY hop_count
            """, delayed_station=delayed_station_id)
            
            records = list(result)
            affected_stations = []
            
            for record in records:
                affected_stations.append({
                    "station_id": record.get("station_id"),
                    "station_name": record.get("station_name"),
                    "hops_from_delay": record.get("hop_count"),
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
    查询两个车站之间的最短路径
    
    Args:
        origin_id: 起始站 ID（例如 "MS01"）
        destination_id: 目标站 ID（例如 "MS10"）
        network: "auto" / "metro" / "rail"
    
    Returns:
        {
            "origin": {"station_id": "MS01", "station_name": "..."},
            "destination": {"station_id": "MS10", "station_name": "..."},
            "route": [
                {"station_id": "MS01", "station_name": "...", "line": "M1"}
            ],
            "total_time_min": 15,
            "num_stops": 5,
            "transfers": 0,
            "lines_used": ["M1"]
        }
    """
    try:
        with driver.session() as session:
            # 查询最短路径
            result = session.run("""
                MATCH path = shortestPath(
                    (origin)-[*]-(destination)
                )
                WHERE origin.station_id = $origin_id 
                AND destination.station_id = $destination_id
                RETURN path,
                    reduce(total=0, r IN relationships(path) | total + r.travel_time_min) as total_time
                LIMIT 1
            """, origin_id=origin_id, destination_id=destination_id)
            
            record = record = next(result, None)
            
            if not record:
                return {
                    "origin": {"station_id": origin_id},
                    "destination": {"station_id": destination_id},
                    "route": [],
                    "error": "No path found"
                }
            
            path = record.get("path")
            total_time = record.get("total_time", 0)
            
            # 解析路径中的节点
            nodes = path.nodes
            route = []
            lines_used = set()
            
            for node in nodes:
                route.append({
                    "station_id": node.get("station_id"),
                    "station_name": node.get("name"),
                    "lines": node.get("lines", [])
                })
            
            # 获取所有关系中的 line
            relationships = path.relationships
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
                "total_time_min": total_time if total_time else 0,
                "num_stops": len(nodes),
                "transfers": 0,  # 简化版本，之后可改进
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
    
    Args:
        origin_id: 起始站
        destination_id: 目标站
        avoid_station_id: 要避开的站
        max_routes: 最多返回几条路线
    
    Returns:
        [
            {
                "route": [...],
                "total_time_min": 15,
                "num_stops": 5,
                "rank": 1
            }
        ]
    """
    try:
        with driver.session() as session:
            # 查询不经过 avoid_station 的路线
            result = session.run(f"""
                MATCH path = (origin)-[*]-(destination)
                WHERE origin.station_id = $origin_id 
                AND destination.station_id = $destination_id
                AND NOT any(n IN nodes(path) WHERE n.station_id = $avoid_station)
                WITH path, 
                    reduce(total=0, r IN relationships(path) | total + r.travel_time_min) as total_time
                ORDER BY total_time, length(path)
                LIMIT {max_routes}
                RETURN path, total_time
            """, origin_id=origin_id, destination_id=destination_id, avoid_station=avoid_station_id)
            
            records = list(result)
            alternatives = []
            
            for rank, record in enumerate(records, 1):
                path = record.get("path")
                total_time = record.get("total_time", 0)
                nodes = path.nodes
                
                route = []
                for node in nodes:
                    route.append({
                        "station_id": node.get("station_id"),
                        "station_name": node.get("name")
                    })
                
                alternatives.append({
                    "route": route,
                    "total_time_min": total_time if total_time else 0,
                    "num_stops": len(nodes),
                    "rank": rank
                })
            
            return alternatives if alternatives else [{"error": "No alternative route found"}]
    
    except Exception as e:
        return [{"error": f"Query failed: {str(e)}"}]


# ============================================================================
# 5️⃣ query_interchange_path() - 查询跨系统转乘路线（最复杂）
# ============================================================================

def query_interchange_path(origin_id: str, destination_id: str) -> Dict:
    """
    查询跨系统转乘路线（Metro ↔ National Rail）
    
    Args:
        origin_id: 起始站（可以是任何类型）
        destination_id: 目标站（可以是任何类型）
    
    Returns:
        {
            "origin": {"station_id": "MS01", ...},
            "destination": {"station_id": "NR05", ...},
            "metro_part": [...],
            "interchange": {"from": ..., "to": ..., "walk_time_min": 5},
            "rail_part": [...],
            "total_time_min": 30,
            "total_stops": 8,
            "transfers": 1
        }
    """
    try:
        with driver.session() as session:
            # 查询包含转乘的路线
            result = session.run("""
                MATCH path = shortestPath(
                    (origin)-[*]-(destination)
                )
                WHERE origin.station_id = $origin_id 
                AND destination.station_id = $destination_id
                AND any(rel in relationships(path) WHERE type(rel) = "INTERCHANGE_TO")
                RETURN path,
                    reduce(total=0, r IN relationships(path) | total + r.travel_time_min) as total_time
                LIMIT 1
            """, origin_id=origin_id, destination_id=destination_id)
            
            record = next(result, None)
            
            if not record:
                return {
                    "origin": {"station_id": origin_id},
                    "destination": {"station_id": destination_id},
                    "error": "No interchange path found"
                }
            
            path = record.get("path")
            total_time = record.get("total_time", 0)
            nodes = path.nodes
            relationships = path.relationships
            
            # 找到转乘点
            interchange_info = None
            metro_part = []
            rail_part = []
            current_part = "metro"
            
            for i, node in enumerate(nodes):
                station = {
                    "station_id": node.get("station_id"),
                    "station_name": node.get("name"),
                    "lines": node.get("lines", [])
                }
                
                # 检查是否经过转乘点
                if i > 0 and i < len(relationships):
                    rel = relationships[i - 1]
                    if rel.type == "INTERCHANGE_TO":
                        current_part = "rail"
                        # 记录转乘信息
                        if not interchange_info:
                            interchange_info = {
                                "from_station_id": nodes[i-1].get("station_id"),
                                "from_station_name": nodes[i-1].get("name"),
                                "to_station_id": node.get("station_id"),
                                "to_station_name": node.get("name"),
                                "walk_time_min": rel.get("travel_time_min", 5)
                            }
                
                if current_part == "metro":
                    metro_part.append(station)
                else:
                    rail_part.append(station)
            
            return {
                "origin": {
                    "station_id": nodes[0].get("station_id"),
                    "station_name": nodes[0].get("name"),
                    "type": "metro" if nodes[0].labels and "MetroStation" in nodes[0].labels else "rail"
                },
                "destination": {
                    "station_id": nodes[-1].get("station_id"),
                    "station_name": nodes[-1].get("name"),
                    "type": "metro" if nodes[-1].labels and "MetroStation" in nodes[-1].labels else "rail"
                },
                "metro_part": metro_part if metro_part else [],
                "interchange": interchange_info if interchange_info else {},
                "rail_part": rail_part if rail_part else [],
                "total_time_min": total_time if total_time else 0,
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
    
    Note: 现在的数据没有票价信息，所以先用最短路径代替
    之后可以加上真实的票价逻辑
    
    Args:
        origin_id: 起始站
        destination_id: 目标站
        fare_class: "standard" / "express"
    
    Returns:
        {
            "route": [...],
            "total_cost_usd": 2.50,
            "total_time_min": 20,
            "fare_class": "standard"
        }
    """
    try:
        # 现在用最短路径，之后可改进
        shortest = query_shortest_route(origin_id, destination_id, network)
        
        if "error" in shortest:
            return {
                "origin": {"station_id": origin_id},
                "destination": {"station_id": destination_id},
                "error": shortest.get("error")
            }
        
        # 简单的票价计算：基础票价 + 站点数 * 0.50
        num_stops = shortest.get("num_stops", 0)
        base_fare = 1.5
        per_stop_fare = 0.5
        total_cost = base_fare + (num_stops - 1) * per_stop_fare
        
        return {
            "route": shortest.get("route", []),
            "total_cost_usd": round(total_cost, 2),
            "total_time_min": shortest.get("total_time_min", 0),
            "num_stops": num_stops,
            "fare_class": fare_class
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