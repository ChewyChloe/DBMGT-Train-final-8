"""
Neo4j Graph Database Seeder for TransitFlow - Fixed Version
============================================================
Author: Yuti Chen (Based on Claude framework + Professor's schema guidelines)
Date: 2026-05-28

Complies with: AI_SESSION_CONTEXT.md Chapter 6 "Agreed Neo4j Graph Schema"

Key Fixes:
✅ Node Label: Station → MetroStation / NationalRailStation
✅ Node Property: id → station_id
✅ Relationship Type: CONNECTS → METRO_LINK / RAIL_LINK / INTERCHANGE_TO
✅ Edge Property: travel_time_minutes → travel_time_min, line_id → line
✅ INTERCHANGE_TO created bidirectionally
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
    """Neo4j Connection Configuration"""
    
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:8001")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow2026")
    
    # Test data paths
    DATA_DIR = Path(__file__).parent.parent / "train-mock-data"
    METRO_STATIONS_FILE = DATA_DIR / "metro_stations.json"
    NATIONAL_STATIONS_FILE = DATA_DIR / "national_rail_stations.json"
    
    # Clear database before starting
    CLEAR_DB = True


# ============================================================================
# Data Models - Fixed Version
# ============================================================================

@dataclass
class StationData:
    """
    Station data model
    
    Fix details:
    - ✅ Use station_id (corresponding to PostgreSQL)
    - ✅ Remove line_type (distinguished by Label: MetroStation vs NationalRailStation)
    - ✅ Remove is_active (not required in Neo4j schema)
    - ✅ Retain name and lines
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
    service_type: str = "normal"
    per_stop_rate_usd: float = 1.50


# ============================================================================
# Data Loader - Fixed Version
# ============================================================================

class DataLoader:
    """Load mock data from JSON files"""
    
    @staticmethod
    def load_all_stations() -> Dict[str, StationData]:
        """
        Load Metro and National Rail stations
        
        Fix details:
        - ✅ Return a unified dictionary {station_id: StationData}
        - ✅ Use station_id as key (not id)
        - ✅ No longer distinguish line_type (determine by ID prefix: MS vs NR)
        """
        print("📍 Loading all stations...")
        
        stations = {}
        
        # Load Metro stations
        print("  🚇 Loading Metro stations...")
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for item in metro_data:
                station = StationData(
                    station_id=item['station_id'],  # ✅ Use station_id
                    name=item['name'],
                    lines=item['lines']
                    # ✅ Remove line_type (distinguished by Label)
                )
                stations[station.station_id] = station
            
            metro_count = len([s for s in stations.values() if s.station_id.startswith('MS')])
            print(f"    ✓ Loaded {metro_count} Metro stations")
        except FileNotFoundError:
            print(f"    ❌ File not found: {Config.METRO_STATIONS_FILE}")
            return {}
        
        # Load National Rail stations
        print("  🚄 Loading National Rail stations...")
        try:
            with open(Config.NATIONAL_STATIONS_FILE, 'r', encoding='utf-8') as f:
                national_data = json.load(f)
            
            for item in national_data:
                station = StationData(
                    station_id=item['station_id'],  # ✅ Use station_id
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
        Extract connections from adjacent_stations
        
        Fix details:
        - ✅ Return dictionary, separate metro/rail/interchange categories
        - ✅ Use line and travel_time_min for attributes
        - ✅ Add connection_type to distinguish the three categories
        """
        print("🔗 Loading connections from adjacent_stations...")
        
        metro_connections = []
        rail_connections = []
        interchange_connections = []
        
        # Metro connections
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for station in metro_data:
                for adjacent in station.get('adjacent_stations', []):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=adjacent['station_id'],
                        line=adjacent['line'],  # ✅ Use line (not line_id)
                        travel_time_min=adjacent['travel_time_min'],  # ✅ Use travel_time_min
                        connection_type='metro'  # ✅ Added
                    )
                    metro_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {Config.METRO_STATIONS_FILE}")
        
        # National Rail connections
        try:
            with open(Config.NATIONAL_STATIONS_FILE, 'r', encoding='utf-8') as f:
                national_data = json.load(f)
            
            for station in national_data:
                for adjacent in station.get('adjacent_stations', []):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=adjacent['station_id'],
                        line=adjacent['line'],  # ✅ Use line
                        travel_time_min=adjacent['travel_time_min'],  # ✅ Use travel_time_min
                        connection_type='rail'  # ✅ Added
                    )
                    rail_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {Config.NATIONAL_STATIONS_FILE}")
        
        # Interchange transfers (extracted from is_interchange_national_rail)
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)
            
            for station in metro_data:
                if station.get('is_interchange_national_rail') and station.get('interchange_national_rail_station_id'):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=station['interchange_national_rail_station_id'],
                        line='INTERCHANGE',  # ✅ Special marker
                        travel_time_min=5,  # ✅ Assuming 5 minutes walk
                        connection_type='interchange'  # ✅ Added
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
# Neo4j Operations - Fixed Version
# ============================================================================

class Neo4jSeeder:
    """Neo4j data seeding tool"""
    
    def __init__(self):
        """Initialize Neo4j connection"""
        try:
            self.driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
            )
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("✓ Connected to Neo4j")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """Close connection"""
        self.driver.close()
        print("✓ Disconnected from Neo4j")
    
    def clear_database(self):
        """Clear all data"""
        print("\n🗑️  Clearing database...")
        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
    
    def create_indexes(self):
        """
        Create indexes
        
        Fix details:
        - ✅ Create indexes separately for MetroStation and NationalRailStation
        - ✅ Create indexes by station_id
        """
        print("\n📑 Creating indexes...")
        queries = [
            # MetroStation indexes
            "CREATE INDEX metro_station_id IF NOT EXISTS FOR (s:MetroStation) ON (s.station_id)",
            "CREATE INDEX metro_station_name IF NOT EXISTS FOR (s:MetroStation) ON (s.name)",
            
            # NationalRailStation indexes
            "CREATE INDEX rail_station_id IF NOT EXISTS FOR (s:NationalRailStation) ON (s.station_id)",
            "CREATE INDEX rail_station_name IF NOT EXISTS FOR (s:NationalRailStation) ON (s.name)",
        ]
        
        with self.driver.session() as session:
            for query in queries:
                try:
                    session.run(query)
                except:
                    pass  # Index may already exist
        
        print("✓ Indexes created")
    
    def seed_metro_stations(self, stations: Dict[str, StationData]):
        """
        Seed Metro stations
        
        Fix details:
        - ✅ Label: MetroStation (not Station)
        - ✅ Attributes: station_id, name, lines (not id, line_type, etc.)
        - ✅ Only seed stations starting with MS
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
                # ✅ Determine by ID prefix (MS = Metro)
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
        Seed National Rail stations
        
        Fix details:
        - ✅ Label: NationalRailStation (not Station)
        - ✅ Only seed stations starting with NR
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
                # ✅ Determine by ID prefix (NR = National Rail)
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
        Seed internal Metro connections
        
        Fix details:
        - ✅ Relationship: METRO_LINK (not CONNECTS)
        - ✅ Attributes: travel_time_min, line (not travel_time_minutes, line_id)
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
        Seed internal National Rail connections
        
        Fix details:
        - ✅ Relationship: RAIL_LINK (not CONNECTS)
        - ✅ Attributes: travel_time_min, line
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
        Seed interchange connections (bidirectional)
        
        Fix details:
        - ✅ Relationship: INTERCHANGE_TO (not TRANSFER)
        - ✅ Must be bidirectional (metro ↔ rail)
        - ✅ Attribute: travel_time_min (represents walk time)
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
        
        # National Rail → Metro (reverse)
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
                    # ✅ Create both directions
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
        Get database statistics
        
        Fix details:
        - ✅ Count MetroStation and NationalRailStation separately
        - ✅ Count three relationships: METRO_LINK, RAIL_LINK, INTERCHANGE_TO
        """
        print("\n📊 Database Statistics:")
        
        try:
            with self.driver.session() as session:
                # Station statistics
                metro_stations = session.run(
                    "MATCH (s:MetroStation) RETURN count(s) as count"
                ).single()[0]
                national_stations = session.run(
                    "MATCH (s:NationalRailStation) RETURN count(s) as count"
                ).single()[0]
                
                # Relationship statistics
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
    """Main program flow"""
    print("=" * 60)
    print("TransitFlow Neo4j Graph Database Seeder")
    print("=" * 60)
    
    seeder = None
    
    try:
        # Initialize
        seeder = Neo4jSeeder()
        
        # Clear database
        if Config.CLEAR_DB:
            seeder.clear_database()
        
        # Create indexes
        seeder.create_indexes()
        
        # Load mock data
        print("\n📂 Loading data...")
        stations = DataLoader.load_all_stations()
        connections_dict = DataLoader.load_all_connections()
        
        if not stations:
            print("❌ No stations loaded. Exiting.")
            return
        
        # Seed data
        seeder.seed_metro_stations(stations)
        seeder.seed_national_rail_stations(stations)
        seeder.seed_metro_connections(connections_dict['metro'])
        seeder.seed_rail_connections(connections_dict['rail'])
        seeder.seed_interchanges(connections_dict['interchange'])
        
        # Display statistics
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
