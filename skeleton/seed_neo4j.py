"""
Neo4j Graph Database Seeder for TransitFlow
============================================================
Author: Chen Yuti
Date: 2026-05-28

Complies with: AI_SESSION_CONTEXT.md Chapter 6 "Agreed Neo4j Graph Schema"

Key corrections:
- Node Label: Station -> MetroStation / NationalRailStation
- Node Property: id -> station_id
- Relationship Type: CONNECTS -> METRO_LINK / RAIL_LINK / INTERCHANGE_TO
- Edge Property: travel_time_minutes -> travel_time_min, line_id -> line
- INTERCHANGE_TO created bidirectionally
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
    """Neo4j connection configuration"""

    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:8001")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow")

    # Mock data paths
    DATA_DIR = Path(__file__).parent.parent / "train-mock-data"
    METRO_STATIONS_FILE = DATA_DIR / "metro_stations.json"
    NATIONAL_STATIONS_FILE = DATA_DIR / "national_rail_stations.json"

    # Clear database before seeding
    CLEAR_DB = True


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class StationData:
    """
    Station data model.

    - Uses station_id to match PostgreSQL
    - Line type distinguished by Node Label (MetroStation vs NationalRailStation)
    """
    station_id: str
    name: str
    lines: List[str]

@dataclass
class ConnectionData:
    """
    Connection data model for Metro, Rail, and Interchange relationships.

    - Uses line and travel_time_min to match schema
    - connection_type distinguishes metro / rail / interchange
    """
    from_station: str
    to_station: str
    line: str
    travel_time_min: int
    connection_type: str
    service_type: str = "normal"
    per_stop_rate_usd: float = 1.50

# ============================================================================
# Data Loader
# ============================================================================

class DataLoader:
    """Loads mock data from JSON files"""

    @staticmethod
    def load_all_stations() -> Dict[str, StationData]:
        """
        Load Metro and National Rail stations from JSON files.

        Returns a unified dict {station_id: StationData}.
        Station type is determined by ID prefix (MS = Metro, NR = National Rail).
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
                    station_id=item['station_id'],
                    name=item['name'],
                    lines=item['lines']
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
                    station_id=item['station_id'],
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
        Load connections from adjacent_stations and national_rail_schedules.

        Returns a dict with keys: 'metro', 'rail', 'interchange'.
        Rail connections load real service_type and per_stop_rate_usd from schedules JSON.
        """
        print("🔗 Loading connections from adjacent_stations and schedules...")

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
                        line=adjacent['line'],
                        travel_time_min=adjacent['travel_time_min'],
                        connection_type='metro'
                    )
                    metro_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {Config.METRO_STATIONS_FILE}")

        # National Rail connections - load real service_type and fare rate from schedules
        NR_SCHEDULES_FILE = Config.DATA_DIR / "national_rail_schedules.json"
        try:
            with open(NR_SCHEDULES_FILE, 'r', encoding='utf-8') as f:
                schedules_data = json.load(f)

            for schedule in schedules_data:
                service_type = schedule.get('service_type', 'normal')
                stops = schedule.get('stops_in_order', [])
                per_stop_rate_standard = schedule.get('fare_classes', {}).get(
                    'standard', {}
                ).get('per_stop_rate_usd', 1.50)
                per_stop_rate_first = schedule.get('fare_classes', {}).get(
                    'first', {}
                ).get('per_stop_rate_usd', 2.50)


                times = schedule.get('travel_time_from_origin_min', {})
                for i in range(len(stops) - 1):
                    from_s = stops[i]
                    to_s = stops[i + 1]
                    time = times.get(to_s, 0) - times.get(from_s, 0)

                    conn = ConnectionData(
                        from_station=from_s,
                        to_station=to_s,
                        line=schedule.get('line', ''),
                        travel_time_min=max(time, 1),
                        connection_type='rail',
                        service_type=service_type,
                        per_stop_rate_usd=per_stop_rate_standard
                    )
                    rail_connections.append(conn)
        except FileNotFoundError:
            print(f"❌ File not found: {NR_SCHEDULES_FILE}")

        # Interchange connections (extracted from is_interchange_national_rail)
        try:
            with open(Config.METRO_STATIONS_FILE, 'r', encoding='utf-8') as f:
                metro_data = json.load(f)

            for station in metro_data:
                if station.get('is_interchange_national_rail') and station.get('interchange_national_rail_station_id'):
                    conn = ConnectionData(
                        from_station=station['station_id'],
                        to_station=station['interchange_national_rail_station_id'],
                        line='INTERCHANGE',
                        travel_time_min=5,
                        connection_type='interchange'
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
# Neo4j Operations
# ============================================================================

class Neo4jSeeder:
    """Neo4j data import tool"""

    def __init__(self):
        """Initialize Neo4j connection"""
        try:
            self.driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
            )
            with self.driver.session() as session:
                session.run("RETURN 1")
            print("✓ Connected to Neo4j")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise

    def close(self):
        """Close Neo4j connection"""
        self.driver.close()
        print("✓ Disconnected from Neo4j")

    def clear_database(self):
        """Delete all nodes and relationships"""
        print("\n🗑️  Clearing database...")
        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")
        except Exception as e:
            print(f"❌ Error clearing database: {e}")

    def create_indexes(self):
        """
        Create indexes for MetroStation and NationalRailStation on station_id.
        """
        print("\n📑 Creating indexes...")
        queries = [
            "CREATE INDEX metro_station_id IF NOT EXISTS FOR (s:MetroStation) ON (s.station_id)",
            "CREATE INDEX metro_station_name IF NOT EXISTS FOR (s:MetroStation) ON (s.name)",
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
        Import Metro stations with label MetroStation.
        Only imports stations with IDs starting with 'MS'.
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
        Import National Rail stations with label NationalRailStation.
        Only imports stations with IDs starting with 'NR'.
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
        Import Metro internal connections as METRO_LINK relationships.
        Uses MERGE to avoid duplicate edges on re-run.
        """
        print("\n🔗 Seeding Metro connections...")

        query = """
        MATCH (s1:MetroStation {station_id: $from_id}), 
            (s2:MetroStation {station_id: $to_id})
        MERGE (s1)-[r:METRO_LINK {line: $line}]->(s2)
        SET r.travel_time_min = $travel_time_min,
            r.per_stop_rate_usd = 0.5
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
        Import National Rail connections as RAIL_LINK relationships.
        Includes service_type and per_stop_rate_usd from schedules data.
        Uses MERGE to avoid duplicate edges on re-run.
        """
        print("\n🔗 Seeding Rail connections...")

        query = """
        MATCH (s1:NationalRailStation {station_id: $from_id}), 
            (s2:NationalRailStation {station_id: $to_id})
        MERGE (s1)-[r:RAIL_LINK {line: $line, service_type: $service_type}]->(s2)
        SET r.travel_time_min = $travel_time_min,
            r.per_stop_rate_usd = $per_stop_rate_usd,
            r.per_stop_rate_usd_first = $per_stop_rate_usd_first
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
                        per_stop_rate_usd=conn.per_stop_rate_usd,
                        per_stop_rate_usd_first=round(conn.per_stop_rate_usd * 5 / 3, 2)
                    )
                    count += 1
                except Exception as e:
                    print(f"⚠️  Error creating connection {conn.from_station} -> {conn.to_station}: {e}")

        print(f"✓ Seeded {count} Rail connections")

    def seed_interchanges(self, interchange_connections: List[ConnectionData]):
        """
        Import interchange connections as INTERCHANGE_TO relationships.
        Created bidirectionally: MetroStation <-> NationalRailStation.
        travel_time_min represents walking time between systems.
        """
        print("\n🔄 Seeding interchange relationships...")

        # TASK 6 EXTENSION: Central Station (MS01/NR01) is the busiest
        # interchange — give it a higher crowd_penalty to model real-world
        # congestion.  Other interchanges get a lower baseline penalty.
        CROWDED_STATIONS = {"MS01", "NR01"}          # Central Station / Central Square
        CROWD_PENALTY_HIGH = 1.5                     # busy hub
        CROWD_PENALTY_LOW  = 0.5                     # smaller interchange
        TRANSFER_WAIT_TIME_MIN = 4                   # fixed walking + waiting buffer

        # Metro -> National Rail
        # TASK 6 EXTENSION: added transfer_wait_time_min, crowd_penalty
        query1 = """
        MATCH (ms:MetroStation {station_id: $from_id}), 
            (nr:NationalRailStation {station_id: $to_id})
        MERGE (ms)-[r:INTERCHANGE_TO {travel_time_min: $travel_time_min}]->(nr)
        SET r.per_stop_rate_usd = 0.0,
            r.transfer_wait_time_min = $transfer_wait,
            r.crowd_penalty = $crowd_penalty
        """

        # National Rail -> Metro (reverse direction)
        # TASK 6 EXTENSION: added transfer_wait_time_min, crowd_penalty
        query2 = """
        MATCH (nr:NationalRailStation {station_id: $from_id}), 
            (ms:MetroStation {station_id: $to_id})
        MERGE (nr)-[r:INTERCHANGE_TO {travel_time_min: $travel_time_min}]->(ms)
        SET r.per_stop_rate_usd = 0.5,
            r.transfer_wait_time_min = $transfer_wait,
            r.crowd_penalty = $crowd_penalty
        """

        count = 0
        with self.driver.session() as session:
            for conn in interchange_connections:
                try:
                    # TASK 6 EXTENSION: determine crowd penalty per station pair
                    is_crowded = (
                        conn.from_station in CROWDED_STATIONS
                        or conn.to_station in CROWDED_STATIONS
                    )
                    cp = CROWD_PENALTY_HIGH if is_crowded else CROWD_PENALTY_LOW

                    session.run(
                        query1,
                        from_id=conn.from_station,
                        to_id=conn.to_station,
                        travel_time_min=conn.travel_time_min,
                        transfer_wait=TRANSFER_WAIT_TIME_MIN,
                        crowd_penalty=cp,
                    )
                    session.run(
                        query2,
                        from_id=conn.to_station,
                        to_id=conn.from_station,
                        travel_time_min=conn.travel_time_min,
                        transfer_wait=TRANSFER_WAIT_TIME_MIN,
                        crowd_penalty=cp,
                    )
                    count += 1
                except Exception as e:
                    print(f"⚠️  Error creating interchange: {e}")

        print(f"✓ Seeded {count} interchange connections (bidirectional)")

    def get_stats(self):
        """
        Print database statistics:
        counts of MetroStation, NationalRailStation,
        METRO_LINK, RAIL_LINK, and INTERCHANGE_TO.
        """
        print("\n📊 Database Statistics:")

        try:
            with self.driver.session() as session:
                metro_stations = session.run(
                    "MATCH (s:MetroStation) RETURN count(s) as count"
                ).single()[0]
                national_stations = session.run(
                    "MATCH (s:NationalRailStation) RETURN count(s) as count"
                ).single()[0]
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
    """Main execution flow"""
    print("=" * 60)
    print("TransitFlow Neo4j Graph Database Seeder")
    print("=" * 60)

    seeder = None

    try:
        seeder = Neo4jSeeder()

        if Config.CLEAR_DB:
            seeder.clear_database()

        seeder.create_indexes()

        print("\n📂 Loading data...")
        stations = DataLoader.load_all_stations()
        connections_dict = DataLoader.load_all_connections()

        if not stations:
            print("❌ No stations loaded. Exiting.")
            return

        seeder.seed_metro_stations(stations)
        seeder.seed_national_rail_stations(stations)
        seeder.seed_metro_connections(connections_dict['metro'])
        seeder.seed_rail_connections(connections_dict['rail'])
        seeder.seed_interchanges(connections_dict['interchange'])

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