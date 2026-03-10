"""SQLite utility layer for B2B SaaS data storage."""

import os
import sqlite3

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def get_connection(company: str) -> sqlite3.Connection:
    """Open a connection to data/{company}.db, creating the directory if needed."""
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.path.join(DATA_DIR, f"{company}.db")
    return sqlite3.connect(db_path)


def write_df(df: pd.DataFrame, table: str, company: str, if_exists: str = "replace") -> int:
    """Write a DataFrame to a table in {company}.db. Returns row count."""
    conn = get_connection(company)
    try:
        df.to_sql(table, conn, if_exists=if_exists, index=False)
        return len(df)
    finally:
        conn.close()


def read_df(table: str, company: str) -> pd.DataFrame:
    """Read a table from {company}.db into a DataFrame."""
    conn = get_connection(company)
    try:
        return pd.read_sql(f"SELECT * FROM [{table}]", conn)
    finally:
        conn.close()
