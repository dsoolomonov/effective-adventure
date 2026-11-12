"""
Data refresh module: Sync live API data to Azure SQL.

This module is called by the FastAPI endpoints when REFRESH is clicked.
Instead of (or in addition to) storing in parquet, it writes to Azure SQL.

Functions here are designed to be called from main.py endpoints.
"""

import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

import pandas as pd

from db.connection import (
    is_db_enabled, execute_sql, write_df, read_sql,
    AZURE_SQL_SCHEMA as SCHEMA, get_cursor
)

log = logging.getLogger("crude_oil_analytics.db.refresh")


# ===================================================================
# Genscape US refresh
# ===================================================================
def refresh_genscape_us(records: List[Dict]) -> int:
    """Upsert Genscape US daily records into COA.genscape_us.

    Args:
        records: List of dicts with keys matching the Genscape API response
                 (unitId, facilityName, unitName, unitCapacity, measurementDate,
                  unitOnline, outageType, region, processingClass, unitCategory,
                  facilityId, alternativeCategory)

    Returns:
        Number of rows upserted.
    """
    if not is_db_enabled() or not records:
        return 0

    df = pd.DataFrame(records)
    col_map = {
        "unitId": "unit_id", "facilityId": "facility_id",
        "facilityName": "facility_name", "unitName": "unit_name",
        "unitCapacity": "unit_capacity", "measurementDate": "measurement_date",
        "unitOnline": "unit_online", "outageType": "outage_type",
        "region": "region", "processingClass": "processing_class",
        "unitCategory": "unit_category", "alternativeCategory": "alternative_category",
    }
    df = df.rename(columns=col_map)

    # Only keep columns that exist
    valid_cols = [c for c in col_map.values() if c in df.columns]
    df = df[valid_cols]

    if "measurement_date" in df.columns:
        df["measurement_date"] = pd.to_datetime(df["measurement_date"]).dt.date
    if "unit_online" in df.columns:
        df["unit_online"] = df["unit_online"].astype(bool)

    # Upsert via MERGE
    count = 0
    with get_cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(f"""
                MERGE {SCHEMA}.genscape_us AS target
                USING (SELECT ? AS unit_id, ? AS measurement_date) AS source
                ON target.unit_id = source.unit_id AND target.measurement_date = source.measurement_date
                WHEN MATCHED THEN
                    UPDATE SET unit_online = ?, outage_type = ?, unit_capacity = ?
                WHEN NOT MATCHED THEN
                    INSERT (unit_id, facility_id, facility_name, unit_name, unit_capacity,
                            measurement_date, unit_online, outage_type, region,
                            processing_class, unit_category, alternative_category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                row.get("unit_id"), row.get("measurement_date"),
                # UPDATE values
                row.get("unit_online"), row.get("outage_type"), row.get("unit_capacity"),
                # INSERT values
                row.get("unit_id"), row.get("facility_id"), row.get("facility_name"),
                row.get("unit_name"), row.get("unit_capacity"), row.get("measurement_date"),
                row.get("unit_online"), row.get("outage_type"), row.get("region"),
                row.get("processing_class"), row.get("unit_category"),
                row.get("alternative_category"),
            ))
            count += 1

    log.info(f"Upserted {count} Genscape US records")
    return count


# ===================================================================
# Genscape Europe refresh
# ===================================================================
def refresh_genscape_eu(records: List[Dict]) -> int:
    """Upsert Genscape Europe daily records into COA.genscape_eu."""
    if not is_db_enabled() or not records:
        return 0

    df = pd.DataFrame(records)
    col_map = {
        "unitId": "unit_id", "facilityId": "facility_id",
        "facilityName": "facility_name", "unitName": "unit_name",
        "unitCapacity": "unit_capacity", "measurementDate": "measurement_date",
        "unitOnline": "unit_online", "outageType": "outage_type",
        "region": "region", "processingClass": "processing_class",
        "unitCategory": "unit_category", "alternativeCategory": "alternative_category",
    }
    df = df.rename(columns=col_map)
    valid_cols = [c for c in col_map.values() if c in df.columns]
    df = df[valid_cols]

    if "measurement_date" in df.columns:
        df["measurement_date"] = pd.to_datetime(df["measurement_date"]).dt.date
    if "unit_online" in df.columns:
        df["unit_online"] = df["unit_online"].astype(bool)

    count = 0
    with get_cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(f"""
                MERGE {SCHEMA}.genscape_eu AS target
                USING (SELECT ? AS unit_id, ? AS measurement_date) AS source
                ON target.unit_id = source.unit_id AND target.measurement_date = source.measurement_date
                WHEN MATCHED THEN
                    UPDATE SET unit_online = ?, outage_type = ?, unit_capacity = ?
                WHEN NOT MATCHED THEN
                    INSERT (unit_id, facility_id, facility_name, unit_name, unit_capacity,
                            measurement_date, unit_online, outage_type, region,
                            processing_class, unit_category, alternative_category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                row.get("unit_id"), row.get("measurement_date"),
                row.get("unit_online"), row.get("outage_type"), row.get("unit_capacity"),
                row.get("unit_id"), row.get("facility_id"), row.get("facility_name"),
                row.get("unit_name"), row.get("unit_capacity"), row.get("measurement_date"),
                row.get("unit_online"), row.get("outage_type"), row.get("region"),
                row.get("processing_class"), row.get("unit_category"),
                row.get("alternative_category"),
            ))
            count += 1

    log.info(f"Upserted {count} Genscape EU records")
    return count


# ===================================================================
# IIR Events refresh
# ===================================================================
def refresh_iir_events(events: List[Dict], status: str, country: str = "") -> int:
    """Upsert IIR turnaround events into COA.iir_events.

    Args:
        events: List of IIR API event dicts (already deduplicated)
        status: 'Ongoing', 'Future', or 'Past'
        country: Country filter used
    """
    if not is_db_enabled() or not events:
        return 0

    count = 0
    with get_cursor() as cur:
        for e in events:
            plant = e.get("plantName", "")
            unit_type = e.get("unitTypeDesc", "")
            start = (e.get("eventStartDate") or "")[:10]
            end = (e.get("eventEndDate") or "")[:10]
            cap = e.get("offlineCapacity", {}).get("capacityOffline", 0) or 0
            unit_cap = e.get("offlineCapacity", {}).get("unitCapacity", 0) or 0
            state = e.get("plantPhysicalAddress", {}).get("stateName", "")
            cntry = e.get("plantPhysicalAddress", {}).get("countryName", country)

            cur.execute(f"""
                MERGE {SCHEMA}.iir_events AS target
                USING (SELECT ? AS plant_name, ? AS unit_type_desc,
                              ? AS event_start_date, ? AS event_end_date) AS source
                ON target.plant_name = source.plant_name
                   AND target.unit_type_desc = source.unit_type_desc
                   AND target.event_start_date = source.event_start_date
                   AND target.event_end_date = source.event_end_date
                WHEN MATCHED THEN
                    UPDATE SET event_status = ?, capacity_offline = ?, fetched_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (event_id, plant_name, plant_state, plant_country,
                            unit_name, unit_type_desc, capacity_offline, unit_capacity,
                            event_start_date, event_end_date, event_status,
                            event_type, event_kind, confirmation_status,
                            event_duration, event_comments)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                # MERGE keys
                plant, unit_type, start or None, end or None,
                # UPDATE
                status, cap,
                # INSERT
                e.get("eventId"), plant, state, cntry,
                e.get("unitName", ""), unit_type, cap, unit_cap,
                start or None, end or None, status,
                e.get("eventType", ""), e.get("eventKind", "T"),
                e.get("eventConfirmationStatus", ""),
                e.get("eventDuration", 0), e.get("eventComments", ""),
            ))
            count += 1

    log.info(f"Upserted {count} IIR {status} events for {country or 'all'}")
    return count


# ===================================================================
# Read helpers (for endpoints to read from SQL instead of files)
# ===================================================================
def get_genscape_us_data(days: int = 14, region: str = None) -> Optional[pd.DataFrame]:
    """Read recent Genscape US data from SQL."""
    if not is_db_enabled():
        return None
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        query = f"""
            SELECT * FROM {SCHEMA}.genscape_us
            WHERE measurement_date >= ?
        """
        params = (cutoff,)
        if region:
            query += " AND region = ?"
            params = (cutoff, region)
        query += " ORDER BY measurement_date DESC"
        return read_sql(query, params)
    except Exception as e:
        log.error(f"Failed to read genscape_us: {e}")
        return None


def get_genscape_eu_data(days: int = 14, region: str = None) -> Optional[pd.DataFrame]:
    """Read recent Genscape Europe data from SQL."""
    if not is_db_enabled():
        return None
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        query = f"""
            SELECT * FROM {SCHEMA}.genscape_eu
            WHERE measurement_date >= ?
        """
        params = (cutoff,)
        if region:
            query += " AND region = ?"
            params = (cutoff, region)
        query += " ORDER BY measurement_date DESC"
        return read_sql(query, params)
    except Exception as e:
        log.error(f"Failed to read genscape_eu: {e}")
        return None


def get_iir_events(status: str = "Ongoing", country: str = None) -> Optional[List[Dict]]:
    """Read IIR events from SQL, returning list of dicts matching API format."""
    if not is_db_enabled():
        return None
    try:
        query = f"SELECT * FROM {SCHEMA}.iir_events WHERE event_status = ?"
        params = (status,)
        if country:
            query += " AND plant_country = ?"
            params = (status, country)
        query += " ORDER BY capacity_offline DESC"
        df = read_sql(query, params)
        if df.empty:
            return []
        # Convert back to API-like format
        events = []
        for _, r in df.iterrows():
            events.append({
                "eventId": r.get("event_id"),
                "plantName": r.get("plant_name"),
                "unitName": r.get("unit_name"),
                "unitTypeDesc": r.get("unit_type_desc"),
                "eventStartDate": str(r.get("event_start_date", "")),
                "eventEndDate": str(r.get("event_end_date", "")),
                "eventType": r.get("event_type"),
                "eventKind": r.get("event_kind"),
                "eventConfirmationStatus": r.get("confirmation_status"),
                "eventDuration": r.get("event_duration"),
                "eventComments": r.get("event_comments"),
                "eventStatusDesc": r.get("event_status"),
                "offlineCapacity": {
                    "capacityOffline": r.get("capacity_offline", 0),
                    "unitCapacity": r.get("unit_capacity", 0),
                },
                "plantPhysicalAddress": {
                    "stateName": r.get("plant_state", ""),
                    "countryName": r.get("plant_country", ""),
                },
            })
        return events
    except Exception as e:
        log.error(f"Failed to read iir_events: {e}")
        return None


def get_cot_data(commodity: str = "Brent") -> Optional[pd.DataFrame]:
    """Read COT data for a specific commodity from SQL."""
    if not is_db_enabled():
        return None
    try:
        query = f"""
            SELECT * FROM {SCHEMA}.cot_data
            WHERE commodity = ?
            ORDER BY report_date DESC
        """
        return read_sql(query, (commodity,))
    except Exception as e:
        log.error(f"Failed to read cot_data: {e}")
        return None


def get_refresh_log(source: str = None, limit: int = 20) -> Optional[pd.DataFrame]:
    """Read recent data refresh log entries."""
    if not is_db_enabled():
        return None
    try:
        query = f"SELECT TOP {limit} * FROM {SCHEMA}.data_refresh_log"
        params = None
        if source:
            query += " WHERE source = ?"
            params = (source,)
        query += " ORDER BY created_at DESC"
        return read_sql(query, params)
    except Exception as e:
        log.error(f"Failed to read refresh log: {e}")
        return None
