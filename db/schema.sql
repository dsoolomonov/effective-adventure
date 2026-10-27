-- ============================================================
-- Crude Oil Analytics Platform - Azure SQL Schema
-- Schema: COA
-- Target: SQL-D-sd027-Analytical-Data (Dev)
--         DB_PRD_AnalyticalData (Prod)
-- ============================================================

-- Create schema if not exists
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'COA')
    EXEC('CREATE SCHEMA COA');
GO

-- ============================================================
-- 1. GENSCAPE US - Daily refinery unit status
-- Source: Genscape API (North America) + historical parquet
-- ~970K rows, daily granularity per unit
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'genscape_us' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.genscape_us (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    unit_id             NVARCHAR(20)   NOT NULL,
    facility_id         NVARCHAR(20),
    facility_name       NVARCHAR(200)  NOT NULL,
    unit_name           NVARCHAR(200),
    unit_capacity       FLOAT,
    measurement_date    DATE           NOT NULL,
    unit_online         BIT            NOT NULL DEFAULT 1,
    outage_type         NVARCHAR(50),          -- Planned, Unplanned, Unknown, NULL
    region              NVARCHAR(50),           -- PADD1..PADD5, Canada
    processing_class    NVARCHAR(100),
    unit_category       NVARCHAR(200),
    alternative_category NVARCHAR(20),          -- CDU, FCC, HCU, VDU, etc.
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_genscape_us UNIQUE (unit_id, measurement_date)
);
GO

CREATE NONCLUSTERED INDEX IX_genscape_us_date
    ON COA.genscape_us (measurement_date)
    INCLUDE (facility_name, unit_online, unit_capacity, region, alternative_category);
GO

CREATE NONCLUSTERED INDEX IX_genscape_us_facility
    ON COA.genscape_us (facility_name, measurement_date);
GO

-- ============================================================
-- 2. GENSCAPE EUROPE - Daily refinery unit status (EU + UK)
-- Source: Genscape API (European regions)
-- ~300K rows
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'genscape_eu' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.genscape_eu (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    unit_id             NVARCHAR(20)   NOT NULL,
    facility_id         NVARCHAR(20),
    facility_name       NVARCHAR(200)  NOT NULL,
    unit_name           NVARCHAR(200),
    unit_capacity       FLOAT,
    measurement_date    DATE           NOT NULL,
    unit_online         BIT            NOT NULL DEFAULT 1,
    outage_type         NVARCHAR(50),
    region              NVARCHAR(50),           -- Europe, United Kingdom
    processing_class    NVARCHAR(100),
    unit_category       NVARCHAR(200),
    alternative_category NVARCHAR(20),
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_genscape_eu UNIQUE (unit_id, measurement_date)
);
GO

CREATE NONCLUSTERED INDEX IX_genscape_eu_date
    ON COA.genscape_eu (measurement_date)
    INCLUDE (facility_name, unit_online, unit_capacity, region, alternative_category);
GO

-- ============================================================
-- 3. GENSCAPE MONTHLY - Monthly aggregated offline values
-- Source: Genscape API monthly endpoint
-- ~210K rows (US + history)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'genscape_monthly' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.genscape_monthly (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    unit_id             NVARCHAR(20)   NOT NULL,
    facility_id         NVARCHAR(20),
    facility_name       NVARCHAR(200),
    unit_name           NVARCHAR(200),
    region              NVARCHAR(50),
    processing_class    NVARCHAR(100),
    unit_category       NVARCHAR(200),
    alternative_category NVARCHAR(20),
    offline_value       FLOAT,
    unit_capacity       FLOAT,
    month_date          DATE           NOT NULL,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_genscape_monthly UNIQUE (unit_id, month_date)
);
GO

-- ============================================================
-- 4. IIR EVENTS - Industrial Info turnaround events
-- Source: IIR IDB API (/offlineevents/summary)
-- Deduplicated by plant+unit+dates
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'iir_events' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.iir_events (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    event_id            NVARCHAR(50),
    plant_name          NVARCHAR(300)  NOT NULL,
    plant_state         NVARCHAR(100),
    plant_country       NVARCHAR(100),
    unit_name           NVARCHAR(300),
    unit_type_desc      NVARCHAR(200),
    capacity_offline    FLOAT,                  -- b/d
    unit_capacity       FLOAT,                  -- b/d
    event_start_date    DATE,
    event_end_date      DATE,
    event_status        NVARCHAR(50),           -- Ongoing, Future, Past
    event_type          NVARCHAR(50),           -- Planned, Unplanned
    event_kind          NVARCHAR(10),           -- T (Turnaround)
    confirmation_status NVARCHAR(50),
    event_duration      INT,                    -- days
    event_comments      NVARCHAR(MAX),
    fetched_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_iir_events UNIQUE (plant_name, unit_type_desc, event_start_date, event_end_date)
);
GO

CREATE NONCLUSTERED INDEX IX_iir_events_status
    ON COA.iir_events (event_status, plant_country)
    INCLUDE (plant_name, unit_type_desc, capacity_offline, event_start_date, event_end_date);
GO

CREATE NONCLUSTERED INDEX IX_iir_events_dates
    ON COA.iir_events (event_start_date, event_end_date);
GO

-- ============================================================
-- 5. COT DATA - Commitment of Traders (multi-commodity)
-- Source: Uploaded Excel files (Brent, WTI, Gasoil)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cot_data' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.cot_data (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    commodity           NVARCHAR(50)   NOT NULL,  -- Brent, WTI, Gasoil
    report_date         DATE           NOT NULL,
    price               FLOAT,
    -- Managed Money
    mm_long             FLOAT,
    mm_short            FLOAT,
    mm_spreading        FLOAT,
    mm_net              FLOAT,
    -- Other Reportables
    or_long             FLOAT,
    or_short            FLOAT,
    or_spreading        FLOAT,
    or_net              FLOAT,
    -- Commercial / Producers
    prod_long           FLOAT,
    prod_short          FLOAT,
    prod_spreading      FLOAT,
    prod_net            FLOAT,
    -- Swap Dealers
    swap_long           FLOAT,
    swap_short          FLOAT,
    swap_spreading      FLOAT,
    swap_net            FLOAT,
    -- Totals
    total_long          FLOAT,
    total_short         FLOAT,
    open_interest       FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_cot_data UNIQUE (commodity, report_date)
);
GO

CREATE NONCLUSTERED INDEX IX_cot_commodity_date
    ON COA.cot_data (commodity, report_date DESC);
GO

-- ============================================================
-- 6. COT LEGACY - Original OIES COT data (Long/Short/Net)
-- Source: COTnew.xlsx
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cot_legacy' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.cot_legacy (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    report_date         DATE           NOT NULL,
    long_pos            FLOAT,
    short_pos           FLOAT,
    net_pos             FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_cot_legacy UNIQUE (report_date)
);
GO

-- ============================================================
-- 7. EA FORWARD MARGINS - Energy Aspects refining margins
-- Source: energyaspects_daily-crude-oil-forward-margins.xlsx
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ea_forward_margins' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.ea_forward_margins (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    report_date         DATE           NOT NULL,
    region              NVARCHAR(50)   NOT NULL,  -- Singapore, MED, NWE, USAC, USGC, USMW, USWC
    margin_value        FLOAT,                    -- $/bbl
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_ea_margins UNIQUE (report_date, region)
);
GO

CREATE NONCLUSTERED INDEX IX_ea_margins_region
    ON COA.ea_forward_margins (region, report_date DESC);
GO

-- ============================================================
-- 8. EA CRUDE BALANCE - Energy Aspects NWE/MED crude balance
-- Source: energyaspects_nwe_med-crude-balance.xlsx
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ea_crude_balance' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.ea_crude_balance (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    report_date         DATE           NOT NULL,
    region              NVARCHAR(50)   NOT NULL,  -- NWE, MED
    category            NVARCHAR(100)  NOT NULL,  -- Demand, Exports, Imports, Production, etc.
    sub_category        NVARCHAR(200),             -- specific flow name
    value_kbd           FLOAT,                    -- kb/d
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_ea_balance UNIQUE (report_date, region, category, sub_category)
);
GO

-- ============================================================
-- 9. JODI GASOLINE - Joint Organisations Data Initiative
-- Source: jodi_gasoline.csv (~338K rows)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'jodi_gasoline' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.jodi_gasoline (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    country             NVARCHAR(100)  NOT NULL,
    flow                NVARCHAR(100)  NOT NULL,   -- Production, Imports, Exports, etc.
    unit                NVARCHAR(20),
    period              NVARCHAR(20)   NOT NULL,    -- YYYY-MM format
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_jodi UNIQUE (country, flow, period)
);
GO

CREATE NONCLUSTERED INDEX IX_jodi_country
    ON COA.jodi_gasoline (country, period DESC);
GO

-- ============================================================
-- 10. GASOLINE BALANCES - PADD-level gasoline S&D
-- Source: gasoline_balances.xlsx
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'gasoline_balances' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.gasoline_balances (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    padd_region         NVARCHAR(50)   NOT NULL,
    metric              NVARCHAR(200)  NOT NULL,   -- Net Production, Imports, Exports, etc.
    report_date         DATE           NOT NULL,
    value               FLOAT,
    created_at          DATETIME2      DEFAULT GETUTCDATE(),

    CONSTRAINT UQ_gasoline_bal UNIQUE (padd_region, metric, report_date)
);
GO

-- ============================================================
-- 11. DATA REFRESH LOG - Track API pulls and data updates
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'data_refresh_log' AND schema_id = SCHEMA_ID('COA'))
CREATE TABLE COA.data_refresh_log (
    id                  BIGINT IDENTITY(1,1) PRIMARY KEY,
    source              NVARCHAR(50)   NOT NULL,   -- genscape_us, genscape_eu, iir, cot, etc.
    refresh_type        NVARCHAR(20)   NOT NULL,   -- full, incremental, manual
    rows_inserted       INT            DEFAULT 0,
    rows_updated        INT            DEFAULT 0,
    status              NVARCHAR(20)   NOT NULL,   -- success, failed, partial
    error_message       NVARCHAR(MAX),
    started_at          DATETIME2      NOT NULL,
    completed_at        DATETIME2,
    created_at          DATETIME2      DEFAULT GETUTCDATE()
);
GO

-- ============================================================
-- Summary views for quick dashboard queries
-- ============================================================

-- Current Genscape US offline units
CREATE OR ALTER VIEW COA.vw_genscape_us_current_offline AS
SELECT
    g.facility_name,
    g.unit_name,
    g.unit_capacity,
    g.region,
    g.alternative_category,
    g.outage_type,
    g.measurement_date
FROM COA.genscape_us g
WHERE g.measurement_date = (SELECT MAX(measurement_date) FROM COA.genscape_us)
  AND g.unit_online = 0;
GO

-- Current Genscape EU offline units
CREATE OR ALTER VIEW COA.vw_genscape_eu_current_offline AS
SELECT
    g.facility_name,
    g.unit_name,
    g.unit_capacity,
    g.region,
    g.alternative_category,
    g.outage_type,
    g.measurement_date
FROM COA.genscape_eu g
WHERE g.measurement_date = (SELECT MAX(measurement_date) FROM COA.genscape_eu)
  AND g.unit_online = 0;
GO

-- IIR ongoing turnarounds
CREATE OR ALTER VIEW COA.vw_iir_ongoing AS
SELECT
    plant_name,
    plant_state,
    plant_country,
    unit_name,
    unit_type_desc,
    capacity_offline,
    event_start_date,
    event_end_date,
    event_type,
    confirmation_status,
    event_comments,
    DATEDIFF(day, event_start_date, event_end_date) AS duration_days
FROM COA.iir_events
WHERE event_status = 'Ongoing';
GO

-- Latest COT positioning
CREATE OR ALTER VIEW COA.vw_cot_latest AS
SELECT
    c.commodity,
    c.report_date,
    c.price,
    c.mm_net,
    c.prod_net,
    c.swap_net,
    c.or_net,
    c.open_interest,
    CASE WHEN c.open_interest > 0 THEN c.mm_net * 100.0 / c.open_interest ELSE 0 END AS mm_pct_oi
FROM COA.cot_data c
WHERE c.report_date = (
    SELECT MAX(report_date) FROM COA.cot_data c2 WHERE c2.commodity = c.commodity
);
GO

PRINT 'Schema COA created successfully with all tables, indexes, and views.';
GO
