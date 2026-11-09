"""Sqlite lookup store and table-CSV zip export."""

import csv
import io
import sqlite3
import zipfile
from pathlib import Path

from tqdm import tqdm

from openpostcode.names import text_or_none
from openpostcode.paths import OUTPUT_ZIP_NAME

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

LOAD_ZIP_URL = (
    "https://raw.githubusercontent.com/hellwig-uk/openpostcode-uk"
    "/main/etl/load/openpostcode_uk.zip"
)
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


def output_zip_name():
    return OUTPUT_ZIP_NAME


def feature_key(row):
    return (
        row["kind"],
        row["name"],
        int(row["unnamed"]),
        row.get("classification"),
        row.get("local_type"),
        row.get("populated_place"),
        row.get("district_borough"),
        row.get("county_unitary"),
        row.get("country"),
    )


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


def attach_road_admin(feature, postcode_row):
    out = dict(feature)
    if out["kind"] == "road":
        out["populated_place"] = text_or_none(postcode_row.get("populated_place"))
        out["district_borough"] = text_or_none(postcode_row.get("district_borough"))
        out["county_unitary"] = text_or_none(postcode_row.get("county_unitary"))
        out["country"] = text_or_none(postcode_row.get("country"))
    else:
        out["populated_place"] = text_or_none(
            out.get("populated_place")
        ) or text_or_none(postcode_row.get("populated_place"))
        out["district_borough"] = text_or_none(out.get("district_borough"))
        out["county_unitary"] = text_or_none(out.get("county_unitary"))
        out["country"] = text_or_none(out.get("country"))
    out["distance_m"] = int(round(out["distance_m"]))
    return out


def write_rows(conn, postcodes_features, progress=False, keys=None, next_id=1):
    if keys is None:
        keys = {}
    postcode_rows = []
    location_rows = []
    feature_rows = []
    iterable = postcodes_features
    if progress:
        iterable = tqdm(
            postcodes_features,
            desc="write sqlite",
            unit="row",
            dynamic_ncols=True,
        )
    for postcode_row, ranked in iterable:
        postcode = postcode_row["postcode"]
        geom = postcode_row.geometry
        postcode_rows.append((postcode, float(geom.x), float(geom.y)))
        for rank, raw in enumerate(ranked, start=1):
            item = attach_road_admin(raw, postcode_row)
            key = feature_key(item)
            if key not in keys:
                keys[key] = next_id
                feature_rows.append(
                    (
                        next_id,
                        item["kind"],
                        item["name"],
                        int(item["unnamed"]),
                        item.get("classification"),
                        item.get("local_type"),
                        item.get("populated_place"),
                        item.get("district_borough"),
                        item.get("county_unitary"),
                        item.get("country"),
                    )
                )
                next_id += 1
            location_rows.append((postcode, rank, keys[key], item["distance_m"]))
    conn.executemany("INSERT INTO postcode VALUES (?, ?, ?)", postcode_rows)
    conn.executemany(
        "INSERT INTO feature VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        feature_rows,
    )
    conn.executemany("INSERT INTO location VALUES (?, ?, ?, ?)", location_rows)
    conn.commit()
    return keys, next_id


def _csv_cells(row):
    return ["" if value is None else value for value in row]


def _parse_cell(column, value):
    if value == "":
        return None
    if column in INTEGER_COLUMNS:
        return int(value)
    if column in REAL_COLUMNS:
        return float(value)
    return value


def _table_rows(conn, table):
    columns = TABLE_COLUMNS[table]
    sql = (
        f"SELECT {', '.join(columns)} FROM {table} " f"ORDER BY {TABLE_ORDER_BY[table]}"
    )
    return columns, conn.execute(sql)


def export_zip(conn, zip_path, progress=False):
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in TABLE_ORDER:
            columns, rows = _table_rows(conn, table)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for row in tqdm(
                rows,
                total=total,
                desc=f"write {table}.csv",
                unit="row",
                disable=not progress,
                dynamic_ncols=True,
            ):
                writer.writerow(_csv_cells(row))
            archive.writestr(f"{table}.csv", buf.getvalue())
    return zip_path


def import_zip(zip_path, sqlite_path, progress=False):
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
                            _parse_cell(column, value)
                            for column, value in zip(columns, line)
                        )
                        for line in reader
                    ]
                placeholders = ", ".join("?" * len(columns))
                col_sql = ", ".join(columns)
                iterable = records
                if progress:
                    iterable = tqdm(
                        records,
                        desc=f"load {table}.csv",
                        unit="row",
                        dynamic_ncols=True,
                    )
                conn.executemany(
                    f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                    iterable,
                )
        conn.commit()
    finally:
        conn.close()
    return sqlite_path
