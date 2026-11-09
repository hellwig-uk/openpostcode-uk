"""Sqlite schema and table-CSV zip IO (stdlib only)."""

import csv
import io
import sqlite3
import zipfile
from pathlib import Path

SCHEMA = """
CREATE TABLE postcode (
  postcode TEXT PRIMARY KEY,
  x REAL,
  y REAL
);
CREATE TABLE feature (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  unnamed INTEGER NOT NULL,
  classification TEXT,
  local_type TEXT,
  populated_place TEXT,
  district_borough TEXT,
  county_unitary TEXT,
  country TEXT
);
CREATE TABLE location (
  postcode TEXT NOT NULL,
  rank INTEGER NOT NULL,
  feature_id INTEGER NOT NULL,
  distance_m INTEGER NOT NULL,
  PRIMARY KEY (postcode, rank)
);
"""

TABLE_ORDER = ("postcode", "feature", "location")
TABLE_COLUMNS = {
    "postcode": ("postcode", "x", "y"),
    "feature": (
        "id",
        "kind",
        "name",
        "unnamed",
        "classification",
        "local_type",
        "populated_place",
        "district_borough",
        "county_unitary",
        "country",
    ),
    "location": ("postcode", "rank", "feature_id", "distance_m"),
}
TABLE_ORDER_BY = {
    "postcode": "postcode",
    "feature": "id",
    "location": "postcode, rank",
}
INTEGER_COLUMNS = frozenset({"id", "unnamed", "rank", "feature_id", "distance_m"})
REAL_COLUMNS = frozenset({"x", "y"})


def csv_cells(row):
    return ["" if value is None else value for value in row]


def parse_cell(column, value):
    if value == "":
        return None
    if column in INTEGER_COLUMNS:
        return int(value)
    if column in REAL_COLUMNS:
        return float(value)
    return value


def connect(sqlite_path):
    path = Path(sqlite_path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.executescript(SCHEMA)
    return conn


def table_rows(conn, table):
    columns = TABLE_COLUMNS[table]
    sql = (
        f"SELECT {', '.join(columns)} FROM {table} " f"ORDER BY {TABLE_ORDER_BY[table]}"
    )
    return columns, conn.execute(sql)


def import_zip(zip_path, sqlite_path, progress_iter=None):
    zip_path = Path(zip_path)
    conn = connect(sqlite_path)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            for table in TABLE_ORDER:
                filename = f"{table}.csv"
                if filename not in names:
                    raise ValueError(f"missing {filename}")
                columns = TABLE_COLUMNS[table]
                with archive.open(filename) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                    reader = csv.reader(text)
                    header = tuple(next(reader))
                    if header != columns:
                        raise ValueError(f"bad header in {filename}")
                    records = [
                        tuple(
                            parse_cell(column, value)
                            for column, value in zip(columns, line)
                        )
                        for line in reader
                    ]
                placeholders = ", ".join("?" * len(columns))
                col_sql = ", ".join(columns)
                iterable = records
                if progress_iter is not None:
                    iterable = progress_iter(records, table)
                conn.executemany(
                    f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                    iterable,
                )
        conn.commit()
    finally:
        conn.close()
    return sqlite_path
