# Crude Oil Analytics Platform — Azure SQL Setup Guide

## Overview

This guide explains how to connect the Crude Oil Analytics Platform to Azure SQL Database so that all API data (Genscape, IIR, COT, etc.) is stored in a central database instead of flat files.

**Architecture:**
```
┌──────────────────┐     ┌────────────────────┐     ┌──────────────┐
│  External APIs   │────>│  Platform (FastAPI) │────>│  Azure SQL   │
│  - Genscape      │     │  - Parses data      │     │  Schema: COA │
│  - IIR           │     │  - Deduplicates     │     │              │
│  - Energy Aspects│     │  - Writes to DB     │     │  11 tables   │
└──────────────────┘     └────────────────────┘     │  4 views     │
                                                     └──────────────┘
```

---

## 1. Prerequisites

### Azure SQL Database
- **Dev:** `SQL-D-sd027-Analytical-Data` on `sql-d-ss001.database.windows.net`
- **Prod:** `DB_PRD_AnalyticalData` on `ssql-p-ss001.database.windows.net`
- Schema: `COA`

### SQL User Setup
Create a dedicated SQL user for the platform:

```sql
-- Run on the target database (Dev or Prod)
CREATE USER [svc_crude_analytics] WITH PASSWORD = '<STRONG_PASSWORD>';
ALTER ROLE db_datareader ADD MEMBER [svc_crude_analytics];
ALTER ROLE db_datawriter ADD MEMBER [svc_crude_analytics];
GRANT CREATE TABLE TO [svc_crude_analytics];
GRANT ALTER ON SCHEMA::COA TO [svc_crude_analytics];
GRANT EXECUTE ON SCHEMA::COA TO [svc_crude_analytics];
```

### ODBC Driver
The platform uses `ODBC Driver 18 for SQL Server`. Install on the hosting machine:

**Ubuntu/Debian:**
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
```

**Docker (add to Dockerfile):**
```dockerfile
RUN curl https://packages.microsoft.com/keys/microsoft.asc | tee /etc/apt/trusted.gpg.d/microsoft.asc \
    && curl https://packages.microsoft.com/config/debian/12/prod.list | tee /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
```

### Python Dependencies
```bash
pip install pyodbc sqlalchemy
```

---

## 2. Environment Variables

Set these on your App Service / Container / VM:

| Variable | Description | Example |
|----------|-------------|---------|
| `USE_AZURE_SQL` | Enable DB mode | `1` |
| `AZURE_SQL_SERVER` | Server hostname | `sql-d-ss001.database.windows.net` |
| `AZURE_SQL_DATABASE` | Database name | `SQL-D-sd027-Analytical-Data` |
| `AZURE_SQL_USERNAME` | SQL login | `svc_crude_analytics` |
| `AZURE_SQL_PASSWORD` | SQL password | `<YOUR_PASSWORD>` |
| `AZURE_SQL_SCHEMA` | Schema name (optional) | `COA` (default) |
| `AZURE_SQL_DRIVER` | ODBC driver (optional) | `ODBC Driver 18 for SQL Server` (default) |

**Azure App Service:**
```bash
az webapp config appsettings set --name <app-name> --resource-group <rg> --settings \
  USE_AZURE_SQL=1 \
  AZURE_SQL_SERVER=sql-d-ss001.database.windows.net \
  AZURE_SQL_DATABASE=SQL-D-sd027-Analytical-Data \
  AZURE_SQL_USERNAME=svc_crude_analytics \
  AZURE_SQL_PASSWORD=<YOUR_PASSWORD>
```

**Docker Compose:**
```yaml
environment:
  - USE_AZURE_SQL=1
  - AZURE_SQL_SERVER=sql-d-ss001.database.windows.net
  - AZURE_SQL_DATABASE=SQL-D-sd027-Analytical-Data
  - AZURE_SQL_USERNAME=svc_crude_analytics
  - AZURE_SQL_PASSWORD=${AZURE_SQL_PASSWORD}
```

---

## 3. Database Schema Setup

### Option A: Run the schema script directly in SSMS / Azure Data Studio
Open `db/schema.sql` and execute it against the target database. It creates:

**Tables (11):**
| Table | Description | Est. Rows |
|-------|-------------|-----------|
| `COA.genscape_us` | US refinery unit status (daily) | ~970K |
| `COA.genscape_eu` | Europe/UK refinery unit status (daily) | ~300K |
| `COA.genscape_monthly` | Monthly offline aggregations | ~210K |
| `COA.iir_events` | IIR turnaround events (deduplicated) | ~5K |
| `COA.cot_data` | COT positioning (Brent/WTI/Gasoil) | ~2.5K |
| `COA.cot_legacy` | Legacy OIES COT data | ~520 |
| `COA.ea_forward_margins` | Energy Aspects refining margins | ~10K |
| `COA.ea_crude_balance` | NWE/MED crude balance | ~5K |
| `COA.jodi_gasoline` | JODI gasoline data | ~338K |
| `COA.gasoline_balances` | PADD gasoline S&D | ~5K |
| `COA.data_refresh_log` | Audit log of data refreshes | grows |

**Views (4):**
- `COA.vw_genscape_us_current_offline` — Currently offline US units
- `COA.vw_genscape_eu_current_offline` — Currently offline EU units
- `COA.vw_iir_ongoing` — Ongoing IIR turnarounds
- `COA.vw_cot_latest` — Latest COT positioning per commodity

### Option B: Run from the platform (requires Python + DB access)
```bash
cd /path/to/crude-oil-original
python -m db.migrate --schema-only
```

---

## 4. Initial Data Migration

Load all existing flat files into the database:

```bash
# Set env vars first
export USE_AZURE_SQL=1
export AZURE_SQL_SERVER=sql-d-ss001.database.windows.net
export AZURE_SQL_DATABASE=SQL-D-sd027-Analytical-Data
export AZURE_SQL_USERNAME=svc_crude_analytics
export AZURE_SQL_PASSWORD=<YOUR_PASSWORD>

# Run full migration
cd /path/to/crude-oil-original
python -m db.migrate --all
```

Or migrate individual sources:
```bash
python -m db.migrate --source genscape_us    # ~970K rows, ~5 min
python -m db.migrate --source genscape_eu    # ~300K rows, ~2 min
python -m db.migrate --source cot            # ~2.5K rows, ~10 sec
python -m db.migrate --source jodi           # ~338K rows, ~3 min
python -m db.migrate --source ea_margins     # ~10K rows, ~30 sec
python -m db.migrate --source ea_balance     # ~5K rows, ~30 sec
```

---

## 5. How It Works

### Dual-Mode Operation
The platform operates in **dual mode**:
- **`USE_AZURE_SQL=0` (default):** Reads/writes flat files (parquet, Excel). Current behavior.
- **`USE_AZURE_SQL=1`:** On every API refresh (REFRESH button), data is written to **both** flat files AND Azure SQL. Read operations still use flat files for speed, but DB is kept in sync.

### Data Flow
```
User clicks REFRESH
  → Platform calls external API (Genscape/IIR)
  → Parses, deduplicates, transforms data
  → Writes to parquet file (existing behavior)
  → IF USE_AZURE_SQL=1: Also MERGE/UPSERT into Azure SQL tables
  → Returns response to frontend
```

### API Endpoints for DB Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/db/status` | GET | Check DB connection status |
| `/api/db/refresh_log` | GET | View data refresh audit log |
| `/api/db/sync_iir` | POST | Manually sync IIR data to DB |

---

## 6. Firewall Rules

The platform needs **outbound** access to:

| Destination | Port | Purpose |
|-------------|------|---------|
| `sql-d-ss001.database.windows.net` | 1433 | Azure SQL (Dev) |
| `ssql-p-ss001.database.windows.net` | 1433 | Azure SQL (Prod) |
| `api.industrialinfo.com` | 443 | IIR turnaround data |
| `api.genscape.com` | 443 | Genscape refinery status |

Azure SQL also requires the platform's **outbound IP** to be whitelisted in the database firewall:
```bash
az sql server firewall-rule create \
  --server sql-d-ss001 \
  --resource-group <rg> \
  --name "CrudeOilPlatform" \
  --start-ip-address <PLATFORM_IP> \
  --end-ip-address <PLATFORM_IP>
```

---

## 7. Monitoring & Maintenance

### Check connection health
```bash
curl https://<platform-url>/api/db/status
# Returns: {"status": "connected", "server": "...", "database": "...", ...}
```

### View recent refreshes
```bash
curl https://<platform-url>/api/db/refresh_log?limit=10
```

### Table sizes (run in SSMS)
```sql
SELECT
    t.name AS TableName,
    SUM(p.rows) AS RowCount,
    SUM(a.total_pages) * 8 / 1024 AS SizeMB
FROM sys.tables t
JOIN sys.indexes i ON t.object_id = i.object_id
JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE t.schema_id = SCHEMA_ID('COA')
GROUP BY t.name
ORDER BY SizeMB DESC;
```

---

## 8. Switching to Production

1. Test everything on Dev (`sql-d-ss001`)
2. Run schema on Prod: execute `db/schema.sql` against `DB_PRD_AnalyticalData`
3. Run migration on Prod: `python -m db.migrate --all` (with Prod env vars)
4. Update env vars to point to Prod server
5. Verify: `curl /api/db/status`

---

## 9. Troubleshooting

| Issue | Solution |
|-------|----------|
| "Login failed for user" | Check username/password. Ensure user exists on the DB. |
| "Cannot open server" | Check firewall rules. Whitelist platform IP. |
| "ODBC Driver not found" | Install msodbcsql18 (see Prerequisites). |
| "SSL connection required" | Driver 18 uses encryption by default — this is correct. |
| DB operations slow | Check index health. The schema includes indexes on key columns. |
| "Permission denied on COA" | Grant ALTER ON SCHEMA::COA to the SQL user. |
