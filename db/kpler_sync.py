"""
Kpler → Azure SQL Sync Module

Pulls data from Kpler SDK and writes to Azure SQL tables (dbo.Kpler_*).
Called from the platform's /api/kpler/sync_sql endpoint.

Requirements:
  - Kpler SDK credentials: KPLER_USERNAME, KPLER_PASSWORD
  - Azure SQL credentials: AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD
  - USE_AZURE_SQL=1
"""

import os
import logging
import traceback
from datetime import date, timedelta, datetime
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger("crude_oil_analytics.kpler_sync")


# ---------------------------------------------------------------------------
# Kpler SDK helpers
# ---------------------------------------------------------------------------
_kpler_config = None


def _get_kpler_config():
    global _kpler_config
    if _kpler_config is None:
        from kpler.sdk import Platform
        from kpler.sdk.configuration import Configuration
        _kpler_config = Configuration(
            Platform.Liquids,
            os.environ.get("KPLER_USERNAME", ""),
            os.environ.get("KPLER_PASSWORD", ""),
        )
    return _kpler_config


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
def _get_sql_conn():
    """Get pyodbc connection using env-var credentials."""
    import pyodbc

    server = os.environ.get("AZURE_SQL_SERVER", "")
    database = os.environ.get("AZURE_SQL_DATABASE", "")
    username = os.environ.get("AZURE_SQL_USERNAME", "")
    password = os.environ.get("AZURE_SQL_PASSWORD", "")
    driver = os.environ.get("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def _truncate_and_insert(conn, table_name: str, df: pd.DataFrame, columns: list):
    """Truncate table and bulk-insert DataFrame rows."""
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM dbo.[{table_name}]")
    deleted = cursor.rowcount

    if df is None or len(df) == 0:
        conn.commit()
        return 0

    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join([f"[{c}]" for c in columns])
    sql = f"INSERT INTO dbo.[{table_name}] ({col_names}) VALUES ({placeholders})"

    rows_inserted = 0
    batch_size = 500
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start:start + batch_size]
        data = []
        for _, row in batch.iterrows():
            vals = []
            for c in columns:
                v = row.get(c)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    vals.append(None)
                else:
                    vals.append(v)
            data.append(tuple(vals))
        cursor.executemany(sql, data)
        rows_inserted += len(data)

    conn.commit()
    return rows_inserted


def _log_sync(conn, table_name, start_time, rows, status, error=None):
    """Write a row to Kpler_SyncLog."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO dbo.[Kpler_SyncLog] ([table_name],[sync_start],[sync_end],[rows_inserted],[status],[error_message]) "
        "VALUES (?,?,?,?,?,?)",
        (table_name, start_time, datetime.utcnow(), rows, status, error[:4000] if error else None),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Individual table sync functions
# ---------------------------------------------------------------------------

def sync_flows(conn, days_back=90):
    """Sync Kpler Flows → dbo.Kpler_Flows (unpivoted wide → long)."""
    from kpler.sdk.resources.flows import Flows
    from kpler.sdk import FlowsSplit, FlowsDirection, FlowsPeriod, FlowsMeasurementUnit

    config = _get_kpler_config()
    fl = Flows(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    products = ["Crude/Co", "Gasoline", "Naphtha", "Gasoil/Diesel"]
    regions = ["United States", "Mediterranean", "India", "China", "Russia", "Latin America"]
    directions = [FlowsDirection.Export, FlowsDirection.Import]

    all_rows = []
    for prod in products:
        for region in regions:
            for direction in directions:
                try:
                    df = fl.get(
                        from_zones=[region] if direction == FlowsDirection.Export else None,
                        to_zones=[region] if direction == FlowsDirection.Import else None,
                        products=[prod],
                        flow_direction=[direction],
                        granularity=[FlowsPeriod.Weekly],
                        split=[FlowsSplit.OriginCountries] if direction == FlowsDirection.Import else [FlowsSplit.DestinationCountries],
                        unit=[FlowsMeasurementUnit.KBD],
                        start_date=start,
                        end_date=today,
                        with_intra_region=False,
                    )
                    if df is None or len(df) == 0:
                        continue

                    dir_str = "Export" if direction == FlowsDirection.Export else "Import"
                    meta_cols = {"Date", "Period End Date"}
                    country_cols = [c for c in df.columns if c not in meta_cols]

                    for _, row in df.iterrows():
                        for country in country_cols:
                            vol = row.get(country)
                            if vol is not None and not (isinstance(vol, float) and np.isnan(vol)) and vol != 0:
                                all_rows.append({
                                    "flow_date": str(row.get("Date", "")),
                                    "period_end_date": str(row.get("Period End Date", "")),
                                    "product": prod,
                                    "region": region,
                                    "direction": dir_str,
                                    "counterpart_country": country,
                                    "volume_kbd": float(vol) if vol else None,
                                    "unit": "kbd",
                                })
                except Exception:
                    continue

    result_df = pd.DataFrame(all_rows)
    cols = ["flow_date", "period_end_date", "product", "region", "direction", "counterpart_country", "volume_kbd", "unit"]
    return _truncate_and_insert(conn, "Kpler_Flows", result_df, cols)


def sync_trades(conn, days_back=90):
    """Sync Kpler Trades → dbo.Kpler_Trades."""
    from kpler.sdk.resources.trades import Trades

    config = _get_kpler_config()
    tr = Trades(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    products = ["Crude/Co", "Gasoline", "Naphtha", "Gasoil/Diesel"]
    regions = ["United States", "Mediterranean", "India", "China", "Russia"]

    all_dfs = []
    for prod in products:
        for region in regions:
            try:
                df = tr.get(
                    from_zones=[region],
                    products=[prod],
                    start_date=start,
                    end_date=today,
                    size=500,
                    columns=["all"],
                )
                if df is not None and len(df) > 0:
                    df["query_product"] = prod
                    df["query_region"] = region
                    all_dfs.append(df)
            except Exception:
                continue

    if not all_dfs:
        return 0

    big = pd.concat(all_dfs, ignore_index=True)

    # Map API columns → SQL columns
    col_map = {
        "trade_id": "trade_id",
        "vessel_name": "vessel_name",
        "vessel_imo": "vessel_imo",
        "vessel_type": "vessel_type",
        "vessel_capacity_cubic_meters": "vessel_capacity_cubic_meters",
        "origin_country_name": "origin_country_name",
        "zone_origin_name": "zone_origin_name",
        "installation_origin_name": "installation_origin_name",
        "continent_origin_name": "continent_origin_name",
        "destination_country_name": "destination_country_name",
        "zone_destination_name": "zone_destination_name",
        "installation_destination_name": "installation_destination_name",
        "continent_destination_name": "continent_destination_name",
        "closest_ancestor_family": "product_family",
        "closest_ancestor_group": "product_group",
        "closest_ancestor_product": "product",
        "closest_ancestor_grade": "product_grade",
        "cargo_origin_barrels_split_by_product": "cargo_volume_barrels",
        "cargo_origin_tons_split_by_product": "cargo_volume_tons",
        "status": "trade_status",
        "start": "start_date",
        "end": "end_date",
        "origin_start": "origin_start",
        "origin_end": "origin_end",
        "destination_start": "destination_start",
        "destination_end": "destination_end",
        "destination_eta": "destination_eta",
        "initial_seller_name": "initial_seller_name",
        "final_buyer_name": "final_buyer_name",
        "charterer_name": "charterer_name",
        "mileage_nautical_miles": "mileage_nautical_miles",
        "ton_miles": "ton_miles",
        "import_price": "import_price",
        "export_price": "export_price",
        "closest_ancestor_grade_api": "grade_api",
        "closest_ancestor_grade_sulfur": "grade_sulfur",
        "is_sts": "is_sts",
        "bill_of_lading_origin": "bill_of_lading",
        "voyage_id": "voyage_id",
        "query_product": "query_product",
        "query_region": "query_region",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        if src in big.columns:
            mapped[dest] = big[src]
        else:
            mapped[dest] = None

    # Convert types
    for c in ["trade_id", "vessel_imo", "vessel_capacity_cubic_meters", "cargo_volume_barrels", "voyage_id"]:
        if c in mapped.columns:
            mapped[c] = pd.to_numeric(mapped[c], errors="coerce")

    # Deduplicate by trade_id
    mapped = mapped.drop_duplicates(subset=["trade_id"], keep="last")

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_Trades", mapped, sql_cols)


def sync_inventories(conn, days_back=180):
    """Sync Kpler Inventories → dbo.Kpler_Inventories."""
    from kpler.sdk.resources.inventories import Inventories
    from kpler.sdk import InventoriesPeriod, InventoriesSplit

    config = _get_kpler_config()
    inv = Inventories(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    zones = ["United States", "China", "ARA", "Japan", "India", "South Korea", "Singapore", "Fujairah"]
    all_dfs = []
    for zone in zones:
        try:
            df = inv.get(
                zones=[zone],
                period=InventoriesPeriod.Weekly,
                split=InventoriesSplit.Total,
                start_date=start,
                end_date=today,
                columns=["all"],
            )
            if df is not None and len(df) > 0:
                df["query_zone"] = zone
                all_dfs.append(df)
        except Exception:
            continue

    if not all_dfs:
        return 0

    big = pd.concat(all_dfs, ignore_index=True)

    col_map = {
        "Date": "inventory_date",
        "Zone": "zone",
        "Installation": "installation",
        "Level (kb)": "level_kb",
        "Capacity (kb)": "capacity_kb",
        "Relative Fill Level": "relative_fill_level",
        "Local Supply (kbd)": "local_supply_kbd",
        "Local Demand (kbd)": "local_demand_kbd",
        "Cargoes (kbd)": "cargoes_kbd",
        "Country": "country",
        "Continent": "continent",
        "Revisit Rate": "revisit_rate",
        "Last Image": "last_image",
        "EIA adjustment level (kb)": "eia_adjustment_level_kb",
        "EIA adjustment capacity (kb)": "eia_adjustment_cap_kb",
        "Delta level (kb)": "delta_level_kb",
        "query_zone": "query_zone",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = big[src] if src in big.columns else None

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_Inventories", mapped, sql_cols)


def sync_fleet_metrics(conn, days_back=90):
    """Sync Kpler FleetMetrics → dbo.Kpler_FleetMetrics."""
    from kpler.sdk.resources.fleet_metrics import FleetMetrics
    from kpler.sdk import FleetMetricsAlgo, FleetMetricsPeriod, FleetMetricsSplit

    config = _get_kpler_config()
    fm = FleetMetrics(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    zones = ["United States", "China", "India", "Singapore", "ARA", "Japan"]
    all_rows = []
    for zone in zones:
        for metric in [FleetMetricsAlgo.FloatingStorage, FleetMetricsAlgo.LoadedVessels]:
            try:
                kwargs = dict(
                    zones=[zone],
                    metric=metric,
                    period=FleetMetricsPeriod.Weekly,
                    split=FleetMetricsSplit.Total,
                    start_date=start,
                    end_date=today,
                )
                if metric == FleetMetricsAlgo.FloatingStorage:
                    kwargs["floating_storage_duration_min"] = "7"
                    kwargs["floating_storage_duration_max"] = "Inf"
                df = fm.get(**kwargs)
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        all_rows.append({
                            "metric_date": str(row.get("Date", "")),
                            "zone": zone,
                            "metric_type": metric.name,
                            "value": float(row.get("Total", 0)),
                        })
            except Exception:
                continue

    result_df = pd.DataFrame(all_rows)
    cols = ["metric_date", "zone", "metric_type", "value"]
    return _truncate_and_insert(conn, "Kpler_FleetMetrics", result_df, cols)


def sync_port_calls(conn, days_back=90):
    """Sync Kpler PortCalls → dbo.Kpler_PortCalls."""
    from kpler.sdk.resources.port_calls import PortCalls

    config = _get_kpler_config()
    pc = PortCalls(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    zones = ["Houston", "Fujairah", "Singapore", "ARA"]
    all_dfs = []
    for zone in zones:
        try:
            df = pc.get(zones=[zone], start_date=start, end_date=today, size=500, columns=["all"])
            if df is not None and len(df) > 0:
                df["query_zone"] = zone
                all_dfs.append(df)
        except Exception:
            continue

    if not all_dfs:
        return 0

    big = pd.concat(all_dfs, ignore_index=True)
    col_map = {
        "port_call_id": "port_call_id", "is_forecasted": "is_forecasted", "confidence": "confidence",
        "vessel_name": "vessel_name", "vessel_imo": "vessel_imo", "vessel_mmsi": "vessel_mmsi",
        "vessel_type": "vessel_type", "vessel_capacity_cubic_meters": "vessel_capacity_cubic_meters",
        "vessel_cargo_type": "vessel_cargo_type", "location_name": "location_name",
        "installation_name": "installation_name", "zone_name": "zone_name", "country_name": "country_name",
        "sub_continent_name": "sub_continent_name", "continent_name": "continent_name",
        "eta": "eta", "start": "start_date", "end": "end_date",
        "closest_ancestor_family": "product_family", "closest_ancestor_group": "product_group",
        "closest_ancestor_product": "product", "closest_ancestor_grade": "product_grade",
        "closest_ancestor_grade_api": "grade_api", "closest_ancestor_grade_sulfur": "grade_sulfur",
        "cargo_origin_barrels_split_by_product": "cargo_volume_barrels",
        "cargo_origin_tons_split_by_product": "cargo_volume_tons",
        "chartererName": "charterer_name", "is_reexport": "is_reexport",
        "is_partial_cargo": "is_partial_cargo", "is_sts": "is_sts",
        "voyage_id": "voyage_id", "query_zone": "query_zone",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = big[src] if src in big.columns else None

    mapped = mapped.drop_duplicates(subset=["port_call_id"], keep="last")
    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_PortCalls", mapped, sql_cols)


def sync_congestion(conn, days_back=90):
    """Sync Kpler CongestionSeries → dbo.Kpler_CongestionSeries."""
    from kpler.sdk.resources.congestion_series import CongestionSeries
    from kpler.sdk import CongestionSeriesMetric, CongestionSeriesPeriod, CongestionSeriesSplit

    config = _get_kpler_config()
    cs = CongestionSeries(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    zones = ["Houston", "Fujairah", "Singapore"]
    metrics = [CongestionSeriesMetric.Count, CongestionSeriesMetric.DeadWeight,
               CongestionSeriesMetric.Duration, CongestionSeriesMetric.Capacity]

    all_rows = []
    for zone in zones:
        for metric in metrics:
            try:
                df = cs.get(
                    zones=[zone], metric=metric,
                    period=CongestionSeriesPeriod.Weekly, split=CongestionSeriesSplit.Total,
                    start_date=start, end_date=today,
                )
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        all_rows.append({
                            "metric_date": str(row.get("Date", "")),
                            "zone": zone,
                            "metric_type": metric.name,
                            "value": float(row.get("Total", 0)),
                        })
            except Exception:
                continue

    result_df = pd.DataFrame(all_rows)
    cols = ["metric_date", "zone", "metric_type", "value"]
    return _truncate_and_insert(conn, "Kpler_CongestionSeries", result_df, cols)


def sync_congestion_vessels(conn, days_back=90):
    """Sync Kpler CongestionVessels → dbo.Kpler_CongestionVessels."""
    from kpler.sdk.resources.congestion_vessels import CongestionVessels

    config = _get_kpler_config()
    cv = CongestionVessels(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    all_dfs = []
    for zone in ["Houston", "Fujairah", "Singapore"]:
        try:
            df = cv.get(zones=[zone], start_date=start, end_date=today, size=500)
            if df is not None and len(df) > 0:
                all_dfs.append(df)
        except Exception:
            continue

    if not all_dfs:
        return 0

    big = pd.concat(all_dfs, ignore_index=True)
    col_map = {
        "date": "report_date", "vessel_imo": "vessel_imo", "vessel": "vessel_name",
        "vessel_dwt_tons": "vessel_dwt_tons", "cargo_tons": "cargo_tons",
        "product_family": "product_family", "product_group": "product_group", "product": "product",
        "installation": "installation", "port": "port", "country": "country", "zone": "zone",
        "congestion_start_date": "congestion_start_date", "congestion_end_date": "congestion_end_date",
        "congestion_duration_hrs": "congestion_duration_hrs", "congestion_status": "congestion_status",
        "vessel_type": "vessel_type", "vessel_operation": "vessel_operation",
        "port_call_id": "port_call_id", "destination_start_date": "destination_start_date",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = big[src] if src in big.columns else None

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_CongestionVessels", mapped, sql_cols)


def sync_fixtures(conn):
    """Sync Kpler Fixtures → dbo.Kpler_Fixtures."""
    from kpler.sdk.resources.fixtures import Fixtures

    config = _get_kpler_config()
    fx = Fixtures(config)

    try:
        df = fx.get(size=1000, columns=["all"])
    except Exception:
        return 0

    if df is None or len(df) == 0:
        return 0

    col_map = {
        "Reported date": "reported_date", "Vessel": "vessel", "IMO": "imo",
        "Quantity (t)": "quantity_tons", "Deadweight (t)": "deadweight_tons",
        "Product": "product", "Charterer": "charterer", "Vessel owner": "vessel_owner",
        "Laycan start": "laycan_start", "Laycan end": "laycan_end",
        "Origin": "origin", "Destination": "destination",
        "Rates ($ price)": "rate_usd", "Status": "fixture_status",
        "Vessel Type CPP": "vessel_type_cpp", "Vessel Type Oil": "vessel_type_oil",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = df[src] if src in df.columns else None

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_Fixtures", mapped, sql_cols)


def sync_sts(conn, days_back=90):
    """Sync Kpler STS → dbo.Kpler_STS."""
    from kpler.sdk.resources.ship_to_ships import ShipToShips

    config = _get_kpler_config()
    sts = ShipToShips(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    try:
        df = sts.get(start_date=start, end_date=today, size=500, columns=["all"])
    except Exception:
        return 0

    if df is None or len(df) == 0:
        return 0

    col_map = {
        "ship_to_ship_id": "ship_to_ship_id",
        "load_vessel_name": "load_vessel_name", "load_vessel_imo": "load_vessel_imo",
        "load_vessel_type": "load_vessel_type", "load_vessel_capacity": "load_vessel_capacity",
        "discharge_vessel_name": "discharge_vessel_name", "discharge_vessel_imo": "discharge_vessel_imo",
        "discharge_vessel_type": "discharge_vessel_type", "discharge_vessel_capacity": "discharge_vessel_capacity",
        "closest_ancestor_family": "product_family", "closest_ancestor_group": "product_group",
        "closest_ancestor_product": "product", "closest_ancestor_grade": "product_grade",
        "closest_ancestor_grade_api": "grade_api", "closest_ancestor_grade_sulfur": "grade_sulfur",
        "cargo_origin_barrels_split_by_product": "cargo_volume_barrels",
        "cargo_origin_tons_split_by_product": "cargo_volume_tons",
        "zone_name": "zone_name", "country_name": "country_name",
        "start": "start_date", "end": "end_date",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = df[src] if src in df.columns else None

    mapped = mapped.drop_duplicates(subset=["ship_to_ship_id"], keep="last")
    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_STS", mapped, sql_cols)


def sync_cushing_drone(conn, days_back=180):
    """Sync Kpler CushingDrone → dbo.Kpler_CushingDrone."""
    from kpler.sdk.resources.inventories_cushing_drone import InventoriesCushingDrone

    config = _get_kpler_config()
    cd = InventoriesCushingDrone(config)
    today = date.today()
    start = today - timedelta(days=days_back)

    try:
        df = cd.get(start_date=start, end_date=today)
    except Exception:
        return 0

    if df is None or len(df) == 0:
        return 0

    col_map = {
        "Date": "survey_date",
        "Level (kb)": "level_kb",
        "Capacity (kb)": "capacity_kb",
        "capacity_utilization": "capacity_utilization",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = df[src] if src in df.columns else None

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_CushingDrone", mapped, sql_cols)


def sync_tank_levels(conn):
    """Sync Kpler TankLevels → dbo.Kpler_TankLevels (last 30 days - API limit)."""
    from kpler.sdk.resources.inventories_tank_levels import InventoriesTankLevels

    config = _get_kpler_config()
    tl = InventoriesTankLevels(config)
    today = date.today()
    start = today - timedelta(days=30)

    try:
        df = tl.get(zones=["United States"], start_date=start, end_date=today)
    except Exception:
        return 0

    if df is None or len(df) == 0:
        return 0

    col_map = {
        "Country": "country", "Installation": "installation", "Tank": "tank",
        "Date": "observation_date", "Level": "level", "Capacity": "capacity",
        "Capacity Utilization": "capacity_utilization", "Tank Type": "tank_type",
    }

    mapped = pd.DataFrame()
    for src, dest in col_map.items():
        mapped[dest] = df[src] if src in df.columns else None

    sql_cols = list(col_map.values())
    return _truncate_and_insert(conn, "Kpler_TankLevels", mapped, sql_cols)


def sync_reference_data(conn):
    """Sync reference tables: Zones, Products, Vessels, Players."""
    from kpler.sdk.resources.zones import Zones
    from kpler.sdk.resources.products import Products
    from kpler.sdk.resources.vessels import Vessels
    from kpler.sdk.resources.players import Players

    config = _get_kpler_config()
    total = 0

    # Zones
    zo = Zones(config)
    all_zones = []
    for q in ["United States", "Europe", "Asia", "Middle East", "Africa", "Latin America",
              "Russia", "India", "China", "Japan", "Korea", "Singapore", "PADD",
              "Houston", "Fujairah", "ARA", "Mediterranean", "Baltic", "Black Sea",
              "North Sea", "Persian Gulf", "Red Sea", "Cushing"]:
        try:
            df = zo.search(q=q)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    all_zones.append({"zone_name": str(row.iloc[0]), "search_category": q})
        except Exception:
            pass
    if all_zones:
        total += _truncate_and_insert(conn, "Kpler_Zones", pd.DataFrame(all_zones), ["zone_name", "search_category"])

    # Products
    pr = Products(config)
    all_prods = []
    for q in ["Crude", "Gasoline", "Naphtha", "Diesel", "Gasoil", "Jet", "Fuel Oil",
              "Kerosene", "Condensate", "VLSFO", "HSFO"]:
        try:
            df = pr.search(q=q)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    all_prods.append({"product_name": str(row.iloc[0]), "search_category": q})
        except Exception:
            pass
    if all_prods:
        total += _truncate_and_insert(conn, "Kpler_Products", pd.DataFrame(all_prods), ["product_name", "search_category"])

    # Vessels
    ve = Vessels(config)
    all_v = []
    for q in ["VLCC", "Suezmax", "Aframax", "Panamax", "MR", "LR1", "LR2"]:
        try:
            df = ve.search(q=q)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    all_v.append({"vessel_name": str(row.iloc[0]), "search_category": q})
        except Exception:
            pass
    if all_v:
        total += _truncate_and_insert(conn, "Kpler_Vessels", pd.DataFrame(all_v), ["vessel_name", "search_category"])

    # Players
    pl = Players(config)
    all_pl = []
    for q in ["Vitol", "Trafigura", "Glencore", "Shell", "BP", "TotalEnergies",
              "ExxonMobil", "Chevron", "Socar", "Reliance", "ADNOC", "Aramco",
              "Lukoil", "Rosneft", "Sinopec", "PetroChina", "Gunvor", "Litasco", "Mercuria"]:
        try:
            df = pl.search(q=q)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    all_pl.append({"player_name": str(row.iloc[0]), "search_category": q})
        except Exception:
            pass
    if all_pl:
        total += _truncate_and_insert(conn, "Kpler_Players", pd.DataFrame(all_pl), ["player_name", "search_category"])

    return total


# ---------------------------------------------------------------------------
# Main sync orchestrator
# ---------------------------------------------------------------------------

SYNC_FUNCTIONS = {
    "Kpler_Flows": sync_flows,
    "Kpler_Trades": sync_trades,
    "Kpler_Inventories": sync_inventories,
    "Kpler_FleetMetrics": sync_fleet_metrics,
    "Kpler_PortCalls": sync_port_calls,
    "Kpler_CongestionSeries": sync_congestion,
    "Kpler_CongestionVessels": sync_congestion_vessels,
    "Kpler_Fixtures": sync_fixtures,
    "Kpler_STS": sync_sts,
    "Kpler_CushingDrone": sync_cushing_drone,
    "Kpler_TankLevels": sync_tank_levels,
    "Kpler_Ref": sync_reference_data,
}


def sync_all(tables: Optional[list] = None) -> dict:
    """
    Run the full Kpler → Azure SQL sync.

    Args:
        tables: Optional list of table names to sync. If None, syncs all.

    Returns:
        dict with per-table results and overall status.
    """
    conn = _get_sql_conn()
    results = {}
    overall_status = "success"

    targets = tables or list(SYNC_FUNCTIONS.keys())
    for table_name in targets:
        func = SYNC_FUNCTIONS.get(table_name)
        if not func:
            results[table_name] = {"status": "skipped", "reason": "unknown table"}
            continue

        start_time = datetime.utcnow()
        try:
            rows = func(conn)
            _log_sync(conn, table_name, start_time, rows, "success")
            results[table_name] = {"status": "success", "rows": rows}
            logger.info(f"Synced {table_name}: {rows} rows")
        except Exception as e:
            tb = traceback.format_exc()
            _log_sync(conn, table_name, start_time, 0, "error", str(e))
            results[table_name] = {"status": "error", "error": str(e)[:200]}
            overall_status = "partial"
            logger.error(f"Error syncing {table_name}: {e}\n{tb}")

    conn.close()
    return {"status": overall_status, "tables": results, "synced_at": datetime.utcnow().isoformat()}
