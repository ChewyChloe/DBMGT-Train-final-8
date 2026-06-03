// Deprecated: seeding is now done via skeleton/seed_neo4j.py
// which loads data directly from train-mock-data/ JSON files.
//
// If you prefer Cypher-file seeding, implement your graph schema here.
// Run with: python skeleton/seed_neo4j.py (or via the Neo4j Browser)

-- Neo4j Graph Schema Definition
-- ============================================================
-- Created: 2026-05-29
-- Purpose: Define schema constraints and documentation
--
-- Note: Data seeding and index creation are handled by seed_neo4j.py
-- ============================================================

-- ============================================================
-- Unique Constraints
-- ============================================================

CREATE CONSTRAINT unique_metro_station_id IF NOT EXISTS 
  ON (s:MetroStation) ASSERT s.station_id IS UNIQUE;

CREATE CONSTRAINT unique_rail_station_id IF NOT EXISTS 
  ON (s:NationalRailStation) ASSERT s.station_id IS UNIQUE;

-- ============================================================
-- Schema Documentation
-- ============================================================
--
-- MetroStation Node
--   Properties:
--     - station_id (String, Unique)
--     - name (String)
--     - lines (List[String])
--
-- NationalRailStation Node
--   Properties:
--     - station_id (String, Unique)
--     - name (String)
--     - lines (List[String])
--
-- Relationships:
--   - METRO_LINK: MetroStation -> MetroStation
--     Properties: travel_time_min (Integer), line (String)
--
--   - RAIL_LINK: NationalRailStation -> NationalRailStation
--     Properties: travel_time_min (Integer), line (String)
--
--   - INTERCHANGE_TO: MetroStation <-> NationalRailStation (Bidirectional)
--     Properties: travel_time_min (Integer)
--
-- ============================================================