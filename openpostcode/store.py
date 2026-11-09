"""Sqlite lookup store and table-CSV zip export."""

import csv
import io
import zipfile
from pathlib import Path

from tqdm import tqdm

from openpostcode.names import text_or_none
from openpostcode.paths import OUTPUT_ZIP_NAME
from openpostcode.tables import (
    TABLE_COLUMNS,
    TABLE_ORDER,
    TABLE_ORDER_BY,
    connect,
    csv_cells,
)
from openpostcode.tables import import_zip as import_zip_tables
from openpostcode.tables import table_rows

LOAD_ZIP_URL = (
    "https://raw.githubusercontent.com/hellwig-uk/openpostcode-uk"
    "/main/etl/load/openpostcode_uk.zip"
)
SOURCES_URL = (
    "https://raw.githubusercontent.com/hellwig-uk/openpostcode-uk"
    "/main/etl/sources.json"
)


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
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in TABLE_ORDER:
            columns, rows = table_rows(conn, table)
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
                writer.writerow(csv_cells(row))
            archive.writestr(f"{table}.csv", buf.getvalue())
    return zip_path


def import_zip(zip_path, sqlite_path, progress=False):
    def progress_iter(records, table):
        if not progress:
            return records
        return tqdm(
            records,
            desc=f"load {table}.csv",
            unit="row",
            dynamic_ncols=True,
        )

    return import_zip_tables(zip_path, sqlite_path, progress_iter=progress_iter)
