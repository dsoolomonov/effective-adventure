"""
Migration script: Load existing flat files (parquet/xlsx/csv) into Azure SQL tables.

Usage:
    python -m db.migrate --all          # Migrate all data sources
    python -m db.migrate --source genscape_us   # Migrate specific source
    python -m db.migrate --source iir           # Migrate IIR events
    python -m db.migrate --schema-only          # Only create tables (run schema.sql)

Environment variables required:
    AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD
    USE_AZURE_SQL=1
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import (
    is_db_enabled, get_cursor, write_df, execute_sql,
    AZURE_SQL_SCHEMA as SCHEMA, get_connection
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate")

DATA_DIR = PROJECT_ROOT / "data"


# ===================================================================
# Schema creation
# ===================================================================
def run_schema():
    """Execute schema.sql to create all tables."""
    schema_file = Path(__file__).parent / "schema.sql"
    if not schema_file.exists():
        log.error(f"schema.sql not found at {schema_file}")
        return False

    sql = schema_file.read_text()
    # Split on GO statements (T-SQL batch separator)
    batches = [b.strip() for b in sql.split("\nGO\n") if b.strip()]

    with get_connection() as conn:
        cursor = conn.cursor()
        for i, batch in enumerate(batches):
            if not batch or batch.startswith("--"):
                continue
            try:
                cursor.execute(batch)
                conn.commit()
            except Exception as e:
                log.warning(f"Batch {i+1} warning: {e}")
                conn.commit()
        cursor.close()

    log.info("Schema created/updated successfully")
    return True


# ===================================================================
# Migration helpers
# ===================================================================
def _log_refresh(source: str, refresh_type: str, inserted: int, updated: int,
                 status: str, error: str = None, started: datetime = None):
    """Log a data refresh event."""
    try:
        execute_sql(
            f"""INSERT INTO {SCHEMA}.data_refresh_log
                (source, refresh_type, rows_inserted, rows_updated, status, error_message, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, GETUTCDATE())""",
            (source, refresh_type, inserted, updated, status, error, started or datetime.utcnow())
        )
    except Exception as e:
        log.warning(f"Could not log refresh: {e}")


def _truncate_table(table: str):
    """Truncate a table before full reload."""
    try:
        execute_sql(f"TRUNCATE TABLE {SCHEMA}.{table}")
        log.info(f"Truncated {SCHEMA}.{table}")
    except Exception as e:
        log.warning(f"Truncate failed (table may not exist): {e}")


# ===================================================================
# 1. Genscape US migration
# ===================================================================
def migrate_genscape_us():
    """Migrate all US Genscape parquet files to COA.genscape_us."""
    log.info("=== Migrating Genscape US ===")
    started = datetime.utcnow()

    # Load main status file
    main_file = DATA_DIR / "genscape" / "runs_status.parquet"
    if not main_file.exists():
        log.error(f"File not found: {main_file}")
        return

    df = pd.read_parquet(main_file)
    log.info(f"Loaded {len(df)} rows from runs_status.parquet")

    # Rename columns to match SQL schema
    col_map = {
        "unitId": "unit_id",
        "facilityId": "facility_id",
        "facilityName": "facility_name",
        "unitName": "unit_name",
        "unitCapacity": "unit_capacity",
        "measurementDate": "measurement_date",
        "unitOnline": "unit_online",
        "outageType": "outage_type",
        "region": "region",
        "processingClass": "processing_class",
        "unitCategory": "unit_category",
        "alternativeCategory": "alternative_category",
    }
    df = df.rename(columns=col_map)
    df["measurement_date"] = pd.to_datetime(df["measurement_date"]).dt.date
    df["unit_online"] = df["unit_online"].astype(bool)

    # Keep only columns that exist in schema
    schema_cols = list(col_map.values())
    df = df[[c for c in schema_cols if c in df.columns]]

    _truncate_table("genscape_us")
    write_df(df, "genscape_us")
    log.info(f"Inserted {len(df)} rows into COA.genscape_us")
    _log_refresh("genscape_us", "full", len(df), 0, "success", started=started)


# ===================================================================
# 2. Genscape Europe migration
# ===================================================================
def migrate_genscape_eu():
    """Migrate European Genscape parquet to COA.genscape_eu."""
    log.info("=== Migrating Genscape Europe ===")
    started = datetime.utcnow()

    eu_file = DATA_DIR / "genscape" / "runs_status_europe.parquet"
    if not eu_file.exists():
        log.error(f"File not found: {eu_file}")
        return

    df = pd.read_parquet(eu_file)
    log.info(f"Loaded {len(df)} rows from runs_status_europe.parquet")

    col_map = {
        "unitId": "unit_id",
        "facilityId": "facility_id",
        "facilityName": "facility_name",
        "unitName": "unit_name",
        "unitCapacity": "unit_capacity",
        "measurementDate": "measurement_date",
        "unitOnline": "unit_online",
        "outageType": "outage_type",
        "region": "region",
        "processingClass": "processing_class",
        "unitCategory": "unit_category",
        "alternativeCategory": "alternative_category",
    }
    df = df.rename(columns=col_map)
    df["measurement_date"] = pd.to_datetime(df["measurement_date"]).dt.date
    df["unit_online"] = df["unit_online"].astype(bool)
    schema_cols = list(col_map.values())
    df = df[[c for c in schema_cols if c in df.columns]]

    _truncate_table("genscape_eu")
    write_df(df, "genscape_eu")
    log.info(f"Inserted {len(df)} rows into COA.genscape_eu")
    _log_refresh("genscape_eu", "full", len(df), 0, "success", started=started)


# ===================================================================
# 3. Genscape Monthly migration
# ===================================================================
def migrate_genscape_monthly():
    """Migrate monthly parquet files to COA.genscape_monthly."""
    log.info("=== Migrating Genscape Monthly ===")
    started = datetime.utcnow()
    total = 0

    _truncate_table("genscape_monthly")

    for fname in ["runs_status_monthly.parquet", "runs_monthly_history.parquet"]:
        fpath = DATA_DIR / "genscape" / fname
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath)
        col_map = {
            "unitId": "unit_id", "facilityId": "facility_id",
            "facilityName": "facility_name", "unitName": "unit_name",
            "region": "region", "processingClass": "processing_class",
            "unitCategory": "unit_category", "alternativeCategory": "alternative_category",
            "offlineValue": "offline_value", "unitCapacity": "unit_capacity",
            "monthDate": "month_date",
        }
        df = df.rename(columns=col_map)
        df["month_date"] = pd.to_datetime(df["month_date"]).dt.date
        schema_cols = list(col_map.values())
        df = df[[c for c in schema_cols if c in df.columns]]
        # Dedup before insert
        df = df.drop_duplicates(subset=["unit_id", "month_date"], keep="last")
        write_df(df, "genscape_monthly")
        total += len(df)
        log.info(f"  {fname}: {len(df)} rows")

    log.info(f"Inserted {total} rows into COA.genscape_monthly")
    _log_refresh("genscape_monthly", "full", total, 0, "success", started=started)


# ===================================================================
# 4. IIR Events migration (from live API cache)
# ===================================================================
def migrate_iir():
    """Fetch current IIR data via the platform's API and store in SQL.
    This requires the platform to be running locally or uses cached data."""
    log.info("=== Migrating IIR Events ===")
    log.info("IIR events are populated via the /api/iir/dashboard endpoint.")
    log.info("Run the platform and call /api/iir/refresh to populate, then use")
    log.info("the db.refresh module to sync API results to SQL.")
    log.info("Skipping for now - IIR migration happens via live API refresh.")


# ===================================================================
# 5. COT Data migration
# ===================================================================
def migrate_cot():
    """Migrate multi-commodity COT Excel files to COA.cot_data."""
    log.info("=== Migrating COT Data ===")
    started = datetime.utcnow()
    total = 0

    _truncate_table("cot_data")

    commodity_files = {
        "Brent": "brentCOT.xlsx",
        "WTI": "wticot.xlsx",
        "Gasoil": "gasoilcot.xlsx",
    }

    for commodity, fname in commodity_files.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            log.warning(f"  {fname} not found, skipping")
            continue

        # Read with multi-level header
        df_raw = pd.read_excel(fpath, header=[0, 1])

        # The first column is the date
        rows = []
        for _, row in df_raw.iterrows():
            date_val = row.iloc[0]
            if pd.isna(date_val):
                continue
            try:
                if isinstance(date_val, str):
                    date_val = pd.to_datetime(date_val).date()
                else:
                    date_val = pd.Timestamp(date_val).date()
            except Exception:
                continue

            # Extract values by position (COT files have consistent structure)
            def safe_float(idx):
                try:
                    v = row.iloc[idx]
                    return float(v) if pd.notna(v) else None
                except (IndexError, ValueError, TypeError):
                    return None

            rows.append({
                "commodity": commodity,
                "report_date": date_val,
                "mm_long": safe_float(1),
                "mm_short": safe_float(2),
                "mm_spreading": safe_float(3),
                "mm_net": safe_float(4),
                "or_long": safe_float(5),
                "or_short": safe_float(6),
                "or_spreading": safe_float(7),
                "or_net": safe_float(8),
                "total_long": safe_float(9),
                "total_short": safe_float(10),
                "prod_long": safe_float(13),
                "prod_short": safe_float(14),
                "prod_spreading": safe_float(15),
                "prod_net": safe_float(16),
                "swap_long": safe_float(17),
                "swap_short": safe_float(18),
                "swap_spreading": safe_float(19),
                "swap_net": safe_float(20),
                "open_interest": safe_float(11) if safe_float(11) else safe_float(12),
                "price": safe_float(35) if df_raw.shape[1] > 35 else None,
            })

        if rows:
            df = pd.DataFrame(rows)
            df = df.drop_duplicates(subset=["commodity", "report_date"], keep="last")
            write_df(df, "cot_data")
            total += len(df)
            log.info(f"  {commodity}: {len(df)} rows")

    # Also migrate legacy COT
    cot_legacy_file = DATA_DIR / "COTnew.xlsx"
    if cot_legacy_file.exists():
        _truncate_table("cot_legacy")
        df = pd.read_excel(cot_legacy_file)
        if "Date" in df.columns:
            df = df.rename(columns={"Date": "report_date", "Long": "long_pos", "Short": "short_pos", "Net": "net_pos"})
            df["report_date"] = pd.to_datetime(df["report_date"]).dt.date
            df = df[["report_date", "long_pos", "short_pos", "net_pos"]].dropna(subset=["report_date"])
            df = df.drop_duplicates(subset=["report_date"], keep="last")
            write_df(df, "cot_legacy")
            log.info(f"  COT legacy: {len(df)} rows")
            total += len(df)

    log.info(f"Inserted {total} total COT rows")
    _log_refresh("cot_data", "full", total, 0, "success", started=started)


# ===================================================================
# 6. JODI Gasoline migration
# ===================================================================
def migrate_jodi():
    """Migrate JODI gasoline CSV to COA.jodi_gasoline."""
    log.info("=== Migrating JODI Gasoline ===")
    started = datetime.utcnow()

    fpath = DATA_DIR / "jodi_gasoline.csv"
    if not fpath.exists():
        log.error(f"File not found: {fpath}")
        return

    df = pd.read_csv(fpath)
    log.info(f"Loaded {len(df)} rows")
    df = df.drop_duplicates(subset=["country", "flow", "period"], keep="last")

    _truncate_table("jodi_gasoline")
    write_df(df, "jodi_gasoline")
    log.info(f"Inserted {len(df)} rows into COA.jodi_gasoline")
    _log_refresh("jodi_gasoline", "full", len(df), 0, "success", started=started)


# ===================================================================
# 7. EA Forward Margins migration
# ===================================================================
def migrate_ea_margins():
    """Migrate Energy Aspects forward margins to COA.ea_forward_margins."""
    log.info("=== Migrating EA Forward Margins ===")
    started = datetime.utcnow()

    fpath = DATA_DIR / "ea_forward_margins.xlsx"
    if not fpath.exists():
        log.error(f"File not found: {fpath}")
        return

    df_raw = pd.read_excel(fpath)
    # This file has metadata rows then date rows
    # First column is dataset_id / dates, remaining columns are region-specific values
    # We need to unpivot this into (date, region, value) format

    # Get region mapping from first rows
    regions = {}
    for col in df_raw.columns[1:]:
        # region info is in the "region" row
        region_row = df_raw[df_raw["dataset_id"] == "region"]
        if not region_row.empty:
            region_val = region_row.iloc[0].get(col)
            if pd.notna(region_val):
                regions[col] = str(region_val)

    # Find data rows (where dataset_id looks like a date)
    rows = []
    for _, r in df_raw.iterrows():
        date_val = r["dataset_id"]
        try:
            if isinstance(date_val, (int, float)):
                date_val = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(date_val))
            date_val = pd.to_datetime(date_val).date()
        except Exception:
            continue

        for col, region in regions.items():
            val = r.get(col)
            if pd.notna(val):
                try:
                    rows.append({
                        "report_date": date_val,
                        "region": region,
                        "margin_value": float(val),
                    })
                except (ValueError, TypeError):
                    pass

    if rows:
        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["report_date", "region"], keep="last")
        _truncate_table("ea_forward_margins")
        write_df(df, "ea_forward_margins")
        log.info(f"Inserted {len(df)} rows into COA.ea_forward_margins")
        _log_refresh("ea_margins", "full", len(df), 0, "success", started=started)
    else:
        log.warning("No margin data rows found")


# ===================================================================
# 8. EA Crude Balance migration
# ===================================================================
def migrate_ea_balance():
    """Migrate Energy Aspects crude balance to COA.ea_crude_balance."""
    log.info("=== Migrating EA Crude Balance ===")
    started = datetime.utcnow()

    fpath = DATA_DIR / "ea_crude_balance.xlsx"
    if not fpath.exists():
        log.error(f"File not found: {fpath}")
        return

    df_raw = pd.read_excel(fpath)

    # Extract metadata: region, category from initial rows
    meta = {}
    meta_fields = ["country", "region", "category", "sub_category", "frequency", "unit"]
    for _, r in df_raw.iterrows():
        key = str(r.get("dataset_id", ""))
        if key in meta_fields:
            for col in df_raw.columns[1:]:
                if col not in meta:
                    meta[col] = {}
                meta[col][key] = r.get(col)

    # Extract data rows
    rows = []
    for _, r in df_raw.iterrows():
        date_val = r["dataset_id"]
        try:
            if isinstance(date_val, (int, float)):
                date_val = pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(date_val))
            date_val = pd.to_datetime(date_val).date()
        except Exception:
            continue

        for col in df_raw.columns[1:]:
            val = r.get(col)
            if pd.isna(val):
                continue
            col_meta = meta.get(col, {})
            region = col_meta.get("region", col_meta.get("country", ""))
            category = col_meta.get("category", "")
            sub_cat = col_meta.get("sub_category", "")
            try:
                rows.append({
                    "report_date": date_val,
                    "region": str(region) if pd.notna(region) else "",
                    "category": str(category) if pd.notna(category) else "",
                    "sub_category": str(sub_cat) if pd.notna(sub_cat) else "",
                    "value_kbd": float(val),
                })
            except (ValueError, TypeError):
                pass

    if rows:
        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["report_date", "region", "category", "sub_category"], keep="last")
        _truncate_table("ea_crude_balance")
        write_df(df, "ea_crude_balance")
        log.info(f"Inserted {len(df)} rows into COA.ea_crude_balance")
        _log_refresh("ea_balance", "full", len(df), 0, "success", started=started)
    else:
        log.warning("No balance data rows found")


# ===================================================================
# Main
# ===================================================================
SOURCES = {
    "genscape_us": migrate_genscape_us,
    "genscape_eu": migrate_genscape_eu,
    "genscape_monthly": migrate_genscape_monthly,
    "iir": migrate_iir,
    "cot": migrate_cot,
    "jodi": migrate_jodi,
    "ea_margins": migrate_ea_margins,
    "ea_balance": migrate_ea_balance,
}


def main():
    parser = argparse.ArgumentParser(description="Migrate flat files to Azure SQL")
    parser.add_argument("--all", action="store_true", help="Migrate all sources")
    parser.add_argument("--source", type=str, help=f"Migrate specific source: {', '.join(SOURCES.keys())}")
    parser.add_argument("--schema-only", action="store_true", help="Only create tables")
    args = parser.parse_args()

    if not is_db_enabled():
        log.error("Azure SQL is not configured. Set environment variables:")
        log.error("  AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD")
        log.error("  USE_AZURE_SQL=1")
        sys.exit(1)

    # Always run schema first
    log.info("Creating/updating schema...")
    run_schema()

    if args.schema_only:
        log.info("Schema-only mode. Done.")
        return

    if args.all:
        for name, func in SOURCES.items():
            try:
                func()
            except Exception as e:
                log.error(f"Failed to migrate {name}: {e}")
    elif args.source:
        if args.source not in SOURCES:
            log.error(f"Unknown source: {args.source}. Available: {', '.join(SOURCES.keys())}")
            sys.exit(1)
        SOURCES[args.source]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
