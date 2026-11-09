"""Public lookup API."""

from openpostcode.lookup import locations_for, open_db, postcode_exists
from openpostcode.names import normalise_postcode
from openpostcodeuk.load import ensure_sqlite

FEATURE_KEYS = (
    "weighted_distance",
    "unnamed",
    "classification",
    "local_type",
    "populated_place",
    "district_borough",
    "county_unitary",
    "country",
)


def _row_dict(row):
    item = {row["kind"]: row["name"]}
    item["weighted_distance"] = int(row["distance_m"])
    item["unnamed"] = int(row["unnamed"])
    for key in FEATURE_KEYS[2:]:
        item[key] = row[key]
    return item


def get(postcode):
    normalised = normalise_postcode(postcode)
    conn = open_db(ensure_sqlite())
    if conn is None:
        raise FileNotFoundError("sqlite not found; run export or import")
    try:
        if not postcode_exists(conn, normalised):
            return None
        rows = locations_for(conn, normalised)
        return [normalised, *(_row_dict(row) for row in rows)]
    finally:
        conn.close()
