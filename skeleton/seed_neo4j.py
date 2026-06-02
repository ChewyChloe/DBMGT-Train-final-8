"""
Neo4j Graph Database Seeder for TransitFlow - 修正版本
============================================================
作者：陳宇緹 (基于 Claude 框架 + 老师 schema 规范)
日期：2026-05-28

符合规范：AI_SESSION_CONTEXT.md 第 6 章「Agreed Neo4j Graph Schema」

关键修正：
✅ Node Label: Station → MetroStation / NationalRailStation
✅ Node Property: id → station_id
✅ Relationship Type: CONNECTS → METRO_LINK / RAIL_LINK / INTERCHANGE_TO
✅ Edge Property: travel_time_minutes → travel_time_min, line_id → line
✅ INTERCHANGE_TO 双向建立
"""

import json
import os
from typing import Dict, List, Optional
from neo4j import GraphDatabase, Session
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Neo4j 连接配置"""
    
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:8001")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow2026")
    
    # 测资路径
    DATA_DIR = Path(__file__).parent.parent / "train-mock-data"
    METRO_STATIONS_FILE = DATA_DIR / "metro_stations.json"
    NATIONAL_STATIONS_FILE = DATA_DIR / "national_rail_stations.json"
    
    # 清空数据库再开始
    CLEAR_DB = True


# ============================================================================
# Data Models - 修正版本
# ============================================================================

@dataclass
class StationData:
    """
    车站数据模型
    
    修正说明：
    - ✅ 改用 station_id（与 PostgreSQL 对应）
    - ✅ 移除 line_type（改由 Label 区分：MetroStation vs NationalRailStation）
    - ✅ 移除 is_active（Neo4j schema 不需要）
    - ✅ 保留 name 和 lines
    """
    station_id: str
    name: str
    lines: List[str]

@dataclass
class ConnectionData:
    from_station: str
    to_station: str
    line: str
    travel_time_min: int
    connection_type: str
    service_type: str = "local"
    per_stop_rate_usd: float = 0.5


# ============================================================================
# Data Loader - 修正版本
# ============================================================================

class DataLoader:
    """从 JSON 檔案讀取測資"""
    
    @staticmethod
    def load_all_stations() -> Dict[str, StationData]:
        """
        讀取 Metro 和 National Rail 車站
        
        修正说明：
        - ✅ 返回统一的字典 {station_id: StationData}
        - ✅ 使用 station_id 作为 key（不是 id）
        - ✅ 不再区分 line_type（改由 ID 前缀判断：MS vs NR）
        """
        print("📍 Loading all stations...")
        
        stations = {}
        
        # 讀取 Metro 車站
        print("  🚇 Loading Metro stations...")
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for item in metro_data:
                station = StationData(
                    station_id=item['station_id'],  # ✅ 改用 station_id
                    name=item['name'],
                    lines=item['lines']
                    # ✅ 移除 line_type（改由 Label 区分）
                )
                stations[station.station_id] = station
            
            metro_count = len([s for s in stations.values() if s.station_id.startswith('MS')])
            print(f"    ✓ Loaded {metro_count} Metro stations")
        except FileNotFoundError:
            print(f"    ❌ File not found: {Config.METRO_STATIONS_FILE}")
            return {}
        
        # 讀取 National Rail 車站
        print("  🚄 Loading National Rail stations...")
        try:
            with open(Config.NATIONAL_STATIONS_FILE, 'r', encoding='utf-8') as f:
                national_data = json.load(f)
            
            for item in national_data:
                station = StationData(
                    station_id=item['station_id'],  # ✅ 改用 station_id
                    name=item['name'],
                    lines=item['lines']
                )
                stations[station.station_id] = station
            
            national_count = len([s for s in stations.values() if s.station_id.startswith('NR')])
            print(f"    ✓ Loaded {national_count} National Rail stations")
        except FileNotFoundError:
            print(f"    ❌ File not found: {Config.NATIONAL_STATIONS_FILE}")
        
        print(f"✓ Total loaded {len(stations)} stations")
        return stations
    
    @staticmethod
    def load_all_connections() -> Dict[str, List[ConnectionData]]:
        """
        從 adjacent_stations 中提取連接
        
        修正说明：
        - ✅ 返回字典，分离 metro/rail/interchange 三类
        - ✅ 属性改用 line 和 travel_time_min
        - ✅ 新增 connection_type 区分三类
        """
        print("🔗 Loading connections from adjacent_stations...")
        
        metro_connections = []
        rail_connections = []
        interchange_connections = []
        
        # Metro 連接
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for station in metro_data:
                for adjacent in station.get('adjacent_stations', []):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=adjacent['station_id'],
                        line=adjacent['line'],  # ✅ 改用 line（不是 line_id）
                        travel_time_min=adjacent['travel_time_min'],  # ✅ 改用 travel_time_min
                        connection_type='metro'  # ✅ 新增
                    )
                    metro_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {Config.METRO_STATIONS_FILE}")
        
        # National Rail 連接
        try:
            with open(Config.NATIONAL_STATIONS_FILE, 'r', encoding='utf-8') as f:
                national_data = json.load(f)
            
            for station in national_data:
                for adjacent in station.get('adjacent_stations', []):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=adjacent['station_id'],
                        line=adjacent['line'],  # ✅ 改用 line
                        travel_time_min=adjacent['travel_time_min'],  # ✅ 改用 travel_time_min
                        connection_type='rail'  # ✅ 新增
                    )
                    rail_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {Config.NATIONAL_STATIONS_FILE}")
        
        # Interchange 轉乘（從 is_interchange_national_rail 提取）
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for station in metro_data:
                if station.get('is_interchange_national_rail') and station.get('interchange_national_rail_station_id'):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=station['interchange_national_rail_station_id'],
                        line='INTERCHANGE',  # ✅ 特殊标记
                        travel_time_min=5,  # ✅ 假設 5 分鐘步行
                        connection_type='interchange'  # ✅ 新增
                    )
                    interchange_connections.append(conn)
        except FileNotFoundError:
            pass
        
        print(f"✓ Loaded {len(metro_connections)} Metro connections")
        print(f"✓ Loaded {len(rail_connections)} Rail connections")
        print(f"✓ Loaded {len(interchange_connections)} interchange connections")
        
        return {
            'metro': metro_connections,
            'rail': rail_connections,
            'interchange': interchange_connections
        }


# ============================================================================
# Neo4j Operations - 修正版本
# ============================================================================

class Neo4jSeeder:
    """Neo4j 数据导入工具"""
    
    def __init__(self):
        """初始化 Neo4j 連接"""
        try:
            self.driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
            )
            # 測試連接
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("✓ Connected to Neo4j")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """關閉連接"""
        self.driver.close()
        print("✓ Disconnected from Neo4j")
    
    def clear_database(self):
        """清空所有數據"""
        print("\n🗑️  Clearing database...")
        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
    
    def create_indexes(self):
        """
        建立索引
        
        修正说明：
        - ✅ 分别为 MetroStation 和 NationalRailStation 建索引
        - ✅ 按 station_id 建索引
        """
        print("\n📑 Creating indexes...")
        queries = [
            # MetroStation 索引
            "CREATE INDEX metro_station_id IF NOT EXISTS FOR (s:MetroStation) ON (s.station_id)",
            "CREATE INDEX metro_station_name IF NOT EXISTS FOR (s:MetroStation) ON (s.name)",
            
            # NationalRailStation 索引
            "CREATE INDEX rail_station_id IF NOT EXISTS FOR (s:NationalRailStation) ON (s.station_id)",
            "CREATE INDEX rail_station_name IF NOT EXISTS FOR (s:NationalRailStation) ON (s.name)",
        ]
        
        with self.driver.session() as session:
            for query in queries:
                try:
                    session.run(query)
                except:
                    pass  # 索引可能已存在
        
        print("✓ Indexes created")
    
    def seed_metro_stations(self, stations: Dict[str, StationData]):
        """
        導入 Metro 車站
        
        修正说明：
        - ✅ Label: MetroStation（不是 Station）
        - ✅ 属性：station_id, name, lines（不是 id, line_type 等）
        - ✅ 只导入 MS 开头的车站
        """
        print("\n📍 Seeding Metro stations...")
        
        query = """
        CREATE (s:MetroStation {
            station_id: $station_id,
            name: $name,
            lines: $lines
        })
        """
        
        count = 0
        with self.driver.session() as session:
            for station in stations.values():
                # ✅ 用 ID 前缀判断（MS = Metro）
                if station.station_id.startswith('MS'):
                    try:
                        session.run(
                            query,
                            station_id=station.station_id,
                            name=station.name,
                            lines=station.lines
                        )
                        count += 1
                    except Exception as e:
                        print(f"❌ Error creating station {station.station_id}: {e}")
        
        print(f"✓ Seeded {count} Metro stations")
    
    def seed_national_rail_stations(self, stations: Dict[str, StationData]):
        """
        導入 National Rail 車站
        
        修正说明：
        - ✅ Label: NationalRailStation（不是 Station）
        - ✅ 只导入 NR 开头的车站
        """
        print("\n📍 Seeding National Rail stations...")
        
        query = """
        CREATE (s:NationalRailStation {
            station_id: $station_id,
            name: $name,
            lines: $lines
        })
        """
        
        count = 0
        with self.driver.session() as session:
            for station in stations.values():
                # ✅ 用 ID 前缀判断（NR = National Rail）
                if station.station_id.startswith('NR'):
                    try:
                        session.run(
                            query,
                            station_id=station.station_id,
                            name=station.name,
                            lines=station.lines
                        )
                        count += 1
                    except Exception as e:
                        print(f"❌ Error creating station {station.station_id}: {e}")
        
        print(f"✓ Seeded {count} National Rail stations")
    
    def seed_metro_connections(self, metro_connections: List[ConnectionData]):
        """
        導入 Metro 內部連接
        
        修正说明：
        - ✅ Relationship: METRO_LINK（不是 CONNECTS）
        - ✅ 属性：travel_time_min, line（不是 travel_time_minutes, line_id）
        """
        print("\n🔗 Seeding Metro connections...")
                
        query = """
        MATCH (s1:MetroStation {station_id: $from_id}), 
            (s2:MetroStation {station_id: $to_id})
        MERGE (s1)-[r:METRO_LINK {line: $line}]->(s2)
        SET r.travel_time_min = $travel_time_min
        """
        
        count = 0
        with self.driver.session() as session:
            for conn in metro_connections:
                try:
                    session.run(
                        query,
                        from_id=conn.from_station,
                        to_id=conn.to_station,
                        travel_time_min=conn.travel_time_min,
                        line=conn.line
                    )
                    count += 1
                except Exception as e:
                    print(f"⚠️  Error creating connection {conn.from_station} -> {conn.to_station}: {e}")
        
        print(f"✓ Seeded {count} Metro connections")
    
    def seed_rail_connections(self, rail_connections: List[ConnectionData]):
        """
        導入 National Rail 內部連接
        
        修正说明：
        - ✅ Relationship: RAIL_LINK（不是 CONNECTS）
        - ✅ 属性：travel_time_min, line
        """
        print("\n🔗 Seeding Rail connections...")
        
        query = """
        MATCH (s1:NationalRailStation {station_id: $from_id}), 
            (s2:NationalRailStation {station_id: $to_id})
        MERGE (s1)-[r:RAIL_LINK {line: $line}]->(s2)
        SET r.travel_time_min = $travel_time_min,
            r.service_type = $service_type,
            r.per_stop_rate_usd = $per_stop_rate_usd
        """
        
        count = 0
        with self.driver.session() as session:
            for conn in rail_connections:
                try:
                    session.run(
                        query,
                        from_id=conn.from_station,
                        to_id=conn.to_station,
                        travel_time_min=conn.travel_time_min,
                        line=conn.line,
                        service_type=conn.service_type,
                        per_stop_rate_usd=conn.per_stop_rate_usd
                    )
                    count += 1
                except Exception as e:
                    print(f"⚠️  Error creating connection {conn.from_station} -> {conn.to_station}: {e}")
        
        print(f"✓ Seeded {count} Rail connections")
    
    def seed_interchanges(self, interchange_connections: List[ConnectionData]):
        """
        導入轉乘連接（雙向）
        
        修正说明：
        - ✅ Relationship: INTERCHANGE_TO（不是 TRANSFER）
        - ✅ 必須雙向建立（metro ↔ rail）
        - ✅ 属性：travel_time_min（表示步行时间）
        """
        print("\n🔄 Seeding interchange relationships...")
        
        # Metro → National Rail
        query1 = """
        MATCH (ms:MetroStation {station_id: $from_id}), 
              (nr:NationalRailStation {station_id: $to_id})
        CREATE (ms)-[r:INTERCHANGE_TO {
            travel_time_min: $travel_time_min
        }]->(nr)
        """
        
        # National Rail → Metro（反向）
        query2 = """
        MATCH (nr:NationalRailStation {station_id: $from_id}), 
              (ms:MetroStation {station_id: $to_id})
        CREATE (nr)-[r:INTERCHANGE_TO {
            travel_time_min: $travel_time_min
        }]->(ms)
        """
        
        count = 0
        with self.driver.session() as session:
            for conn in interchange_connections:
                try:
                    # ✅ 建立兩個方向
                    session.run(
                        query1,
                        from_id=conn.from_station,
                        to_id=conn.to_station,
                        travel_time_min=conn.travel_time_min
                    )
                    session.run(
                        query2,
                        from_id=conn.to_station,
                        to_id=conn.from_station,
                        travel_time_min=conn.travel_time_min
                    )
                    count += 1
                except Exception as e:
                    print(f"⚠️  Error creating interchange: {e}")
        
        print(f"✓ Seeded {count} interchange connections (bidirectional)")
    
    def get_stats(self):
        """
        獲取數據庫統計信息
        
        修正说明：
        - ✅ 分别统计 MetroStation 和 NationalRailStation
        - ✅ 统计三种关系：METRO_LINK, RAIL_LINK, INTERCHANGE_TO
        """
        print("\n📊 Database Statistics:")
        
        try:
            with self.driver.session() as session:
                # 车站统计
                metro_stations = session.run(
                    "MATCH (s:MetroStation) RETURN count(s) as count"
                ).single()[0]
                national_stations = session.run(
                    "MATCH (s:NationalRailStation) RETURN count(s) as count"
                ).single()[0]
                
                # 关系统计
                metro_links = session.run(
                    "MATCH ()-[r:METRO_LINK]->() RETURN count(r) as count"
                ).single()[0]
                rail_links = session.run(
                    "MATCH ()-[r:RAIL_LINK]->() RETURN count(r) as count"
                ).single()[0]
                interchange_to = session.run(
                    "MATCH ()-[r:INTERCHANGE_TO]->() RETURN count(r) as count"
                ).single()[0]
                
                print(f"  📍 MetroStation: {metro_stations}")
                print(f"  📍 NationalRailStation: {national_stations}")
                print(f"  🔗 METRO_LINK: {metro_links}")
                print(f"  🔗 RAIL_LINK: {rail_links}")
                print(f"  🔄 INTERCHANGE_TO: {interchange_to}")
        except Exception as e:
            print(f"  ❌ Error getting stats: {e}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """主程式流程"""
    print("=" * 60)
    print("TransitFlow Neo4j Graph Database Seeder")
    print("=" * 60)
    
    seeder = None
    
    try:
        # 初始化
        seeder = Neo4jSeeder()
        
        # 清空數據庫
        if Config.CLEAR_DB:
            seeder.clear_database()
        
        # 建立索引
        seeder.create_indexes()
        
        # 讀取測資
        print("\n📂 Loading data...")
        stations = DataLoader.load_all_stations()
        connections_dict = DataLoader.load_all_connections()
        
        if not stations:
            print("❌ No stations loaded. Exiting.")
            return
        
        # 導入數據
        seeder.seed_metro_stations(stations)
        seeder.seed_national_rail_stations(stations)
        seeder.seed_metro_connections(connections_dict['metro'])
        seeder.seed_rail_connections(connections_dict['rail'])
        seeder.seed_interchanges(connections_dict['interchange'])
        
        # 顯示統計
        seeder.get_stats()
        
        print("\n" + "=" * 60)
        print("✓ Seeding completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if seeder:
            seeder.close()


if __name__ == "__main__":
    main()
