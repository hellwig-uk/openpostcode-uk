"""Sqlite lookup store and dated zip export."""

import csv
import io
import sqlite3
import zipfile
from datetime import date
from pathlib import Path

from tqdm import tqdm

from opennames.names import text_or_none

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


def output_zip_name(when=None):
    day = when or date.today()
    return f"openpostcode_uk_{day:%Y}{day:%j}.zip"


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


def export_zip(conn, zip_path, progress=False):
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    postcodes_buf = io.StringIO()
    features_buf = io.StringIO()
    post_writer = csv.writer(postcodes_buf)
    feat_writer = csv.writer(features_buf)
    post_writer.writerow(["postcode", "x", "y", "rank", "feature_id", "distance_m"])
    feat_writer.writerow(
        [
            "feature_id",
            "kind",
            "name",
            "unnamed",
            "classification",
            "local_type",
            "populated_place",
            "district_borough",
            "county_unitary",
            "country",
        ]
    )
    n_loc = conn.execute("SELECT COUNT(*) FROM location").fetchone()[0]
    loc_rows = conn.execute("""
        SELECT p.postcode, p.x, p.y, l.rank, l.feature_id, l.distance_m
        FROM postcode AS p
        JOIN location AS l ON l.postcode = p.postcode
        ORDER BY p.postcode, l.rank
        """)
    for row in tqdm(
        loc_rows,
        total=n_loc,
        desc="write postcodes.csv",
        unit="row",
        disable=not progress,
        dynamic_ncols=True,
    ):
        post_writer.writerow(row)
    n_feat = conn.execute("SELECT COUNT(*) FROM feature").fetchone()[0]
    feat_rows = conn.execute("""
        SELECT id, kind, name, unnamed, classification, local_type,
               populated_place, district_borough, county_unitary, country
        FROM feature
        ORDER BY id
        """)
    for row in tqdm(
        feat_rows,
        total=n_feat,
        desc="write features.csv",
        unit="row",
        disable=not progress,
        dynamic_ncols=True,
    ):
        feat_writer.writerow(row)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("postcodes.csv", postcodes_buf.getvalue())
        archive.writestr("features.csv", features_buf.getvalue())
    return zip_path
