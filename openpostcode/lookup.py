"""Query lookup.sqlite by postcode."""

import sqlite3
from pathlib import Path

from openpostcode.names import normalise_postcode

FIELDS = (
    "kind",
    "unnamed",
    "classification",
    "local_type",
    "populated_place",
    "district_borough",
    "county_unitary",
    "country",
)


def open_db(sqlite_path):
    path = Path(sqlite_path)
    if not path.is_file():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def postcode_exists(conn, postcode):
    row = conn.execute(
        "SELECT 1 FROM postcode WHERE postcode = ?",
        (postcode,),
    ).fetchone()
    return row is not None


def locations_for(conn, postcode):
    return list(
        conn.execute(
            """
            SELECT f.name, l.distance_m, f.kind, f.unnamed, f.classification,
                   f.local_type, f.populated_place, f.district_borough,
                   f.county_unitary, f.country
            FROM location AS l
            JOIN feature AS f ON f.id = l.feature_id
            WHERE l.postcode = ?
            ORDER BY l.rank
            """,
            (postcode,),
        )
    )


def format_null(value):
    if value is None:
        return "null"
    return str(value)


def render_locations(rows):
    blocks = []
    for row in rows:
        lines = [
            f"{row['kind']}: {row['name']}",
            f"weighted_distance: {row['distance_m']}",
        ]
        for key in FIELDS:
            lines.append(f"{key}: {format_null(row[key])}")
        lines.append("-------")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def lookup(sqlite_path, tokens):
    postcode = normalise_postcode(" ".join(tokens))
    conn = open_db(sqlite_path)
    if conn is None:
        return 1, "", "sqlite not found; run build or import"
    try:
        if not postcode_exists(conn, postcode):
            return 1, "", "postcode not found"
        rows = locations_for(conn, postcode)
        if not rows:
            return 0, "", ""
        return 0, render_locations(rows) + "\n", ""
    finally:
        conn.close()
