"""
Azure SQL Database connection module.

All credentials are read from environment variables:
  AZURE_SQL_SERVER   - e.g. sql-d-ss001.database.windows.net
  AZURE_SQL_DATABASE - e.g. SQL-D-sd027-Analytical-Data
  AZURE_SQL_USERNAME - SQL login username
  AZURE_SQL_PASSWORD - SQL login password

Optional:
  AZURE_SQL_DRIVER   - ODBC driver name (default: ODBC Driver 18 for SQL Server)
  AZURE_SQL_SCHEMA   - Schema name (default: COA)
  USE_AZURE_SQL      - Set to "1" to enable DB mode (default: file-based)
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("crude_oil_analytics.db")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
AZURE_SQL_SERVER = os.getenv("AZURE_SQL_SERVER", "")
AZURE_SQL_DATABASE = os.getenv("AZURE_SQL_DATABASE", "")
AZURE_SQL_USERNAME = os.getenv("AZURE_SQL_USERNAME", "")
AZURE_SQL_PASSWORD = os.getenv("AZURE_SQL_PASSWORD", "")
AZURE_SQL_DRIVER = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
AZURE_SQL_SCHEMA = os.getenv("AZURE_SQL_SCHEMA", "COA")
USE_AZURE_SQL = os.getenv("USE_AZURE_SQL", "0") == "1"


def is_db_enabled() -> bool:
    """Check if Azure SQL is configured and enabled."""
    return (
        USE_AZURE_SQL
        and bool(AZURE_SQL_SERVER)
        and bool(AZURE_SQL_DATABASE)
        and bool(AZURE_SQL_USERNAME)
        and bool(AZURE_SQL_PASSWORD)
    )


def get_connection_string() -> str:
    """Build pyodbc connection string for Azure SQL."""
    return (
        f"DRIVER={{{AZURE_SQL_DRIVER}}};"
        f"SERVER={AZURE_SQL_SERVER};"
        f"DATABASE={AZURE_SQL_DATABASE};"
        f"UID={AZURE_SQL_USERNAME};"
        f"PWD={AZURE_SQL_PASSWORD};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )


def get_sqlalchemy_url() -> str:
    """Build SQLAlchemy connection URL for Azure SQL."""
    from urllib.parse import quote_plus
    conn_str = get_connection_string()
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
_engine = None


def get_engine():
    """Get or create a SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        _engine = create_engine(
            get_sqlalchemy_url(),
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            echo=False,
        )
    return _engine


@contextmanager
def get_connection():
    """Context manager for a raw pyodbc connection."""
    import pyodbc
    conn = pyodbc.connect(get_connection_string())
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor():
    """Context manager for a pyodbc cursor with auto-commit."""
    import pyodbc
    conn = pyodbc.connect(get_connection_string(), autocommit=False)
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def test_connection() -> dict:
    """Test the database connection and return status info."""
    if not is_db_enabled():
        return {"status": "disabled", "message": "USE_AZURE_SQL is not set to 1 or credentials missing"}

    try:
        with get_cursor() as cur:
            cur.execute("SELECT @@VERSION AS version, DB_NAME() AS db_name, SCHEMA_NAME() AS default_schema")
            row = cur.fetchone()
            return {
                "status": "connected",
                "server": AZURE_SQL_SERVER,
                "database": AZURE_SQL_DATABASE,
                "schema": AZURE_SQL_SCHEMA,
                "sql_version": str(row.version)[:80] if row else "unknown",
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Pandas helpers
# ---------------------------------------------------------------------------
def read_sql(query: str, params: Optional[tuple] = None):
    """Execute a SQL query and return a pandas DataFrame."""
    import pandas as pd
    engine = get_engine()
    return pd.read_sql(query, engine, params=params)


def write_df(df, table_name: str, if_exists: str = "append", schema: str = None):
    """Write a pandas DataFrame to an Azure SQL table."""
    import pandas as pd
    engine = get_engine()
    schema = schema or AZURE_SQL_SCHEMA
    df.to_sql(
        table_name,
        engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
        method="multi",
        chunksize=1000,
    )


def execute_sql(query: str, params: Optional[tuple] = None) -> int:
    """Execute a SQL statement (INSERT/UPDATE/DELETE) and return rows affected."""
    with get_cursor() as cur:
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur.rowcount
