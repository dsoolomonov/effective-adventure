-- ============================================================
-- Kpler Data Tables - Azure SQL Schema
-- Target: SQL-D-sd027-Analytical-Data (Dev)
-- Server: sql-d-ss001.database.windows.net
-- Schema: dbo (matches existing tables)
-- 
-- INSTRUCTIONS:
--   1. Open SSMS, connect to sql-d-ss001.database.windows.net
--   2. Select database: SQL-D-sd027-Analytical-Data
--   3. Click "New Query"
--   4. Paste this entire script
--   5. Click "Execute" (or press F5)
--   6. All tables will be created with Kpler_ prefix
--
-- NOTE: This script is safe to re-run. It only creates tables
--       if they don't already exist (IF NOT EXISTS checks).
-- ============================================================

-- ============================================================
-- 1. KPLER FLOWS - Weekly product flows by country pair
-- Source: Kpler SDK Flows.get() 
-- Unpivoted: one row per date/product/region/direction/country
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Flows' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Flows (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    flow_date           NVARCHAR(20)   NOT NULL,       -- e.g. '2026-W09' (ISO week)
    period_end_date     NVARCHAR(20),                   -- e.g. '2026-W09'
    product             NVARCHAR(100)  NOT NULL,        -- Crude/Co, Gasoline, Naphtha, etc.
    region              NVARCHAR(100)  NOT NULL,        -- United States, Mediterranean, etc.
    direction           NVARCHAR(10)   NOT NULL,        -- Export / Import
    counterpart_country NVARCHAR(200)  NOT NULL,        -- Destination (export) or Origin (import)
    volume_kbd          FLOAT,                          -- Volume in thousand barrels per day
    unit                NVARCHAR(10)   DEFAULT 'kbd',
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_Flows UNIQUE (flow_date, product, region, direction, counterpart_country)
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_Flows_date ON dbo.Kpler_Flows (flow_date) INCLUDE (product, region, direction, volume_kbd);
GO
CREATE NONCLUSTERED INDEX IX_Kpler_Flows_product ON dbo.Kpler_Flows (product, region, direction) INCLUDE (flow_date, counterpart_country, volume_kbd);
GO

-- ============================================================
-- 2. KPLER TRADES - Individual cargo movements (vessel-level)
-- Source: Kpler SDK Trades.get() - key columns from 164 total
-- One row per trade (vessel cargo movement)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Trades' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Trades (
    id                              BIGINT IDENTITY(1,1) PRIMARY KEY,
    trade_id                        BIGINT         NOT NULL,
    vessel_name                     NVARCHAR(200),
    vessel_imo                      BIGINT,
    vessel_type                     NVARCHAR(50),
    vessel_capacity_cubic_meters    BIGINT,
    origin_country_name             NVARCHAR(200),
    zone_origin_name                NVARCHAR(200),
    installation_origin_name        NVARCHAR(300),
    continent_origin_name           NVARCHAR(100),
    destination_country_name        NVARCHAR(200),
    zone_destination_name           NVARCHAR(200),
    installation_destination_name   NVARCHAR(300),
    continent_destination_name      NVARCHAR(100),
    product_family                  NVARCHAR(100),
    product_group                   NVARCHAR(100),
    product                         NVARCHAR(200),
    product_grade                   NVARCHAR(200),
    cargo_volume_barrels            BIGINT,
    cargo_volume_tons               FLOAT,
    trade_status                    NVARCHAR(50),          -- Loading, In Transit, Completed, etc.
    start_date                      NVARCHAR(50),
    end_date                        NVARCHAR(50),
    origin_start                    NVARCHAR(50),
    origin_end                      NVARCHAR(50),
    destination_start               NVARCHAR(50),
    destination_end                 NVARCHAR(50),
    destination_eta                 NVARCHAR(50),
    initial_seller_name             NVARCHAR(1000),
    final_buyer_name                NVARCHAR(1000),
    charterer_name                  NVARCHAR(1000),
    mileage_nautical_miles          FLOAT,
    ton_miles                       FLOAT,
    import_price                    FLOAT,
    export_price                    FLOAT,
    grade_api                       FLOAT,
    grade_sulfur                    FLOAT,
    is_sts                          BIT,
    bill_of_lading                  NVARCHAR(200),
    voyage_id                       BIGINT,
    query_product                   NVARCHAR(100),
    query_region                    NVARCHAR(100),
    created_at                      DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_Trades UNIQUE (trade_id)
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_Trades_origin ON dbo.Kpler_Trades (origin_country_name) INCLUDE (product, destination_country_name, cargo_volume_barrels, trade_status);
GO
CREATE NONCLUSTERED INDEX IX_Kpler_Trades_product ON dbo.Kpler_Trades (product) INCLUDE (origin_country_name, destination_country_name, cargo_volume_barrels);
GO
CREATE NONCLUSTERED INDEX IX_Kpler_Trades_vessel ON dbo.Kpler_Trades (vessel_name, vessel_imo);
GO

-- ============================================================
-- 3. KPLER INVENTORIES - Satellite-tracked crude oil storage
-- Source: Kpler SDK Inventories.get()
-- Weekly data by zone (US, China, ARA, Japan, India, etc.)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Inventories' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Inventories (
    id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
    inventory_date          DATE           NOT NULL,
    zone                    NVARCHAR(200),
    installation            NVARCHAR(300),
    level_kb                FLOAT,                  -- Stock level (thousand barrels)
    capacity_kb             FLOAT,                  -- Total capacity (thousand barrels)
    relative_fill_level     FLOAT,                  -- Fill percentage
    local_supply_kbd        FLOAT,
    local_demand_kbd        FLOAT,
    cargoes_kbd             FLOAT,
    country                 NVARCHAR(200),
    continent               NVARCHAR(100),
    revisit_rate            FLOAT,
    last_image              NVARCHAR(50),
    eia_adjustment_level_kb FLOAT,
    eia_adjustment_cap_kb   FLOAT,
    delta_level_kb          FLOAT,
    query_zone              NVARCHAR(100),
    created_at              DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_Inventories UNIQUE (inventory_date, zone, query_zone)
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_Inventories_date ON dbo.Kpler_Inventories (inventory_date) INCLUDE (zone, level_kb, capacity_kb);
GO
CREATE NONCLUSTERED INDEX IX_Kpler_Inventories_zone ON dbo.Kpler_Inventories (query_zone, inventory_date) INCLUDE (level_kb, capacity_kb);
GO

-- ============================================================
-- 4. KPLER FLEET METRICS - Floating storage & loaded vessels
-- Source: Kpler SDK FleetMetrics.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_FleetMetrics' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_FleetMetrics (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         NVARCHAR(30)   NOT NULL,
    zone                NVARCHAR(200)  NOT NULL,
    metric_type         NVARCHAR(50)   NOT NULL,     -- FloatingStorage / LoadedVessels
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_FleetMetrics UNIQUE (metric_date, zone, metric_type)
);
GO

-- ============================================================
-- 5. KPLER PORT CALLS - Vessel arrivals/departures
-- Source: Kpler SDK PortCalls.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_PortCalls' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_PortCalls (
    id                              BIGINT IDENTITY(1,1) PRIMARY KEY,
    port_call_id                    BIGINT         NOT NULL,
    is_forecasted                   BIT,
    confidence                      FLOAT,
    vessel_name                     NVARCHAR(200),
    vessel_imo                      BIGINT,
    vessel_mmsi                     BIGINT,
    vessel_type                     NVARCHAR(50),
    vessel_capacity_cubic_meters    BIGINT,
    vessel_cargo_type               NVARCHAR(50),
    location_name                   NVARCHAR(300),
    installation_name               NVARCHAR(300),
    zone_name                       NVARCHAR(200),
    country_name                    NVARCHAR(200),
    sub_continent_name              NVARCHAR(200),
    continent_name                  NVARCHAR(100),
    eta                             NVARCHAR(50),
    start_date                      NVARCHAR(50),
    end_date                        NVARCHAR(50),
    product_family                  NVARCHAR(100),
    product_group                   NVARCHAR(100),
    product                         NVARCHAR(200),
    product_grade                   NVARCHAR(200),
    grade_api                       FLOAT,
    grade_sulfur                    FLOAT,
    cargo_volume_barrels            FLOAT,
    cargo_volume_tons               FLOAT,
    charterer_name                  NVARCHAR(300),
    is_reexport                     BIT,
    is_partial_cargo                BIT,
    is_sts                          BIT,
    voyage_id                       BIGINT,
    query_zone                      NVARCHAR(100),
    created_at                      DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_PortCalls UNIQUE (port_call_id)
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_PortCalls_zone ON dbo.Kpler_PortCalls (query_zone, eta);
GO

-- ============================================================
-- 6. KPLER CONGESTION SERIES - Vessel waiting metrics
-- Source: Kpler SDK CongestionSeries.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_CongestionSeries' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_CongestionSeries (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         DATE           NOT NULL,
    zone                NVARCHAR(200)  NOT NULL,
    metric_type         NVARCHAR(50)   NOT NULL,     -- Count, DeadWeight, Duration, Capacity
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_CongestionSeries UNIQUE (metric_date, zone, metric_type)
);
GO

-- ============================================================
-- 7. KPLER CONGESTION VESSELS - Individual waiting vessels
-- Source: Kpler SDK CongestionVessels.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_CongestionVessels' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_CongestionVessels (
    id                          BIGINT IDENTITY(1,1) PRIMARY KEY,
    report_date                 NVARCHAR(50),
    vessel_imo                  BIGINT,
    vessel_name                 NVARCHAR(200),
    vessel_dwt_tons             BIGINT,
    cargo_tons                  FLOAT,
    product_family              NVARCHAR(100),
    product_group               NVARCHAR(100),
    product                     NVARCHAR(200),
    installation                NVARCHAR(300),
    port                        NVARCHAR(200),
    country                     NVARCHAR(200),
    zone                        NVARCHAR(200),
    congestion_start_date       NVARCHAR(50),
    congestion_end_date         NVARCHAR(50),
    congestion_duration_hrs     FLOAT,
    congestion_status           NVARCHAR(50),
    vessel_type                 NVARCHAR(50),
    vessel_operation            NVARCHAR(50),
    port_call_id                BIGINT,
    destination_start_date      NVARCHAR(50),
    created_at                  DATETIME2      DEFAULT GETUTCDATE()
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_CongVessels_zone ON dbo.Kpler_CongestionVessels (zone, report_date);
GO

-- ============================================================
-- 8. KPLER FIXTURES - Chartering / freight fixtures
-- Source: Kpler SDK Fixtures.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Fixtures' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Fixtures (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    reported_date       NVARCHAR(50),
    vessel              NVARCHAR(200),
    imo                 BIGINT,
    quantity_tons       FLOAT,
    deadweight_tons     BIGINT,
    product             NVARCHAR(200),
    charterer           NVARCHAR(300),
    vessel_owner        NVARCHAR(300),
    laycan_start        NVARCHAR(50),
    laycan_end          NVARCHAR(50),
    origin              NVARCHAR(300),
    destination         NVARCHAR(300),
    rate_usd            FLOAT,
    fixture_status      NVARCHAR(50),
    vessel_type_cpp     NVARCHAR(50),
    vessel_type_oil     NVARCHAR(50),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_Fixtures_date ON dbo.Kpler_Fixtures (reported_date) INCLUDE (vessel, product, origin, destination);
GO

-- ============================================================
-- 9. KPLER STS - Ship-to-Ship transfer events
-- Source: Kpler SDK ShipToShips.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_STS' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_STS (
    id                              BIGINT IDENTITY(1,1) PRIMARY KEY,
    ship_to_ship_id                 BIGINT         NOT NULL,
    load_vessel_name                NVARCHAR(200),
    load_vessel_imo                 BIGINT,
    load_vessel_type                NVARCHAR(50),
    load_vessel_capacity            BIGINT,
    discharge_vessel_name           NVARCHAR(200),
    discharge_vessel_imo            BIGINT,
    discharge_vessel_type           NVARCHAR(50),
    discharge_vessel_capacity       BIGINT,
    product_family                  NVARCHAR(100),
    product_group                   NVARCHAR(100),
    product                         NVARCHAR(200),
    product_grade                   NVARCHAR(200),
    grade_api                       FLOAT,
    grade_sulfur                    FLOAT,
    cargo_volume_barrels            BIGINT,
    cargo_volume_tons               BIGINT,
    zone_name                       NVARCHAR(200),
    country_name                    NVARCHAR(200),
    start_date                      NVARCHAR(50),
    end_date                        NVARCHAR(50),
    created_at                      DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_STS UNIQUE (ship_to_ship_id)
);
GO

-- ============================================================
-- 10. KPLER CUSHING DRONE - Cushing OK satellite/drone survey
-- Source: Kpler SDK InventoriesCushingDrone.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_CushingDrone' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_CushingDrone (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    survey_date         DATE           NOT NULL,
    level_kb            FLOAT,                  -- Stock level (thousand barrels)
    capacity_kb         FLOAT,                  -- Capacity (thousand barrels)
    capacity_utilization FLOAT,                 -- Fill percentage
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_CushingDrone UNIQUE (survey_date)
);
GO

-- ============================================================
-- 11. KPLER TANK LEVELS - Individual tank fill levels
-- Source: Kpler SDK InventoriesTankLevels.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_TankLevels' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_TankLevels (
    id                      BIGINT IDENTITY(1,1) PRIMARY KEY,
    country                 NVARCHAR(200),
    installation            NVARCHAR(300),
    tank                    NVARCHAR(300),
    observation_date        DATE           NOT NULL,
    level                   FLOAT,
    capacity                FLOAT,
    capacity_utilization    FLOAT,
    tank_type               NVARCHAR(100),
    created_at              DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_TankLevels UNIQUE (installation, tank, observation_date)
);
GO

CREATE NONCLUSTERED INDEX IX_Kpler_TankLevels_date ON dbo.Kpler_TankLevels (observation_date) INCLUDE (country, installation, level, capacity);
GO

-- ============================================================
-- 12. KPLER FREIGHT METRICS - Ton-miles, speed, distance
-- Source: Kpler SDK FreightMetricsSeries.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_FreightMetrics' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_FreightMetrics (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         DATE           NOT NULL,
    metric_type         NVARCHAR(50)   NOT NULL,     -- TonMiles, TonDays, AvgSpeed, AvgDistance
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_FreightMetrics UNIQUE (metric_date, metric_type)
);
GO

-- ============================================================
-- 13. KPLER FLEET UTILIZATION
-- Source: Kpler SDK FleetUtilizationSeries.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_FleetUtilization' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_FleetUtilization (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         DATE           NOT NULL,
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_FleetUtilization UNIQUE (metric_date)
);
GO

-- ============================================================
-- 14. KPLER FLEET DEVELOPMENT
-- Source: Kpler SDK FleetDevelopmentSeries.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_FleetDevelopment' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_FleetDevelopment (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         DATE           NOT NULL,
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_FleetDevelopment UNIQUE (metric_date)
);
GO

-- ============================================================
-- 15. KPLER BALLAST CAPACITY
-- Source: Kpler SDK BallastCapacitySeries.get()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_BallastCapacity' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_BallastCapacity (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    metric_date         DATE           NOT NULL,
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_Kpler_BallastCapacity UNIQUE (metric_date)
);
GO

-- ============================================================
-- 16. KPLER ZONES - Reference: available trading zones
-- Source: Kpler SDK Zones.search()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Zones' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Zones (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    zone_name           NVARCHAR(300)  NOT NULL,
    search_category     NVARCHAR(200),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

-- ============================================================
-- 17. KPLER PRODUCTS - Reference: available product list
-- Source: Kpler SDK Products.search()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Products' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Products (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    product_name        NVARCHAR(300)  NOT NULL,
    search_category     NVARCHAR(200),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

-- ============================================================
-- 18. KPLER VESSELS - Reference: vessel database
-- Source: Kpler SDK Vessels.search()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Vessels' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Vessels (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    vessel_name         NVARCHAR(300)  NOT NULL,
    search_category     NVARCHAR(200),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

-- ============================================================
-- 19. KPLER PLAYERS - Reference: companies/traders
-- Source: Kpler SDK Players.search()
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_Players' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_Players (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    player_name         NVARCHAR(300)  NOT NULL,
    search_category     NVARCHAR(200),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

-- ============================================================
-- 20. KPLER SYNC LOG - Tracks when data was last refreshed
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Kpler_SyncLog' AND schema_id = SCHEMA_ID('dbo'))
CREATE TABLE dbo.Kpler_SyncLog (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    table_name          NVARCHAR(200)  NOT NULL,
    sync_start          DATETIME2      NOT NULL,
    sync_end            DATETIME2,
    rows_inserted       INT,
    rows_updated        INT,
    status              NVARCHAR(20)   NOT NULL,     -- running, success, error
    error_message       NVARCHAR(MAX),
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

PRINT '=== All 20 Kpler tables created successfully ===';
PRINT 'Tables: Kpler_Flows, Kpler_Trades, Kpler_Inventories, Kpler_FleetMetrics,';
PRINT '        Kpler_PortCalls, Kpler_CongestionSeries, Kpler_CongestionVessels,';
PRINT '        Kpler_Fixtures, Kpler_STS, Kpler_CushingDrone, Kpler_TankLevels,';
PRINT '        Kpler_FreightMetrics, Kpler_FleetUtilization, Kpler_FleetDevelopment,';
PRINT '        Kpler_BallastCapacity, Kpler_Zones, Kpler_Products, Kpler_Vessels,';
PRINT '        Kpler_Players, Kpler_SyncLog';
GO
