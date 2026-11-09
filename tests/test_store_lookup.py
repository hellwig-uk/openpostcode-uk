import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpostcode.extract import read_landmarks, read_postcodes, read_roads
from openpostcode.lookup import lookup
from openpostcode.match import features_for_point
from openpostcode.paths import OUTPUT_ZIP_NAME
from openpostcode.store import (
    TABLE_COLUMNS,
    TABLE_ORDER,
    TABLE_ORDER_BY,
    attach_road_admin,
    connect,
    export_zip,
    feature_key,
    import_zip,
    output_zip_name,
    write_rows,
)
from tests.common import sample_names, sample_roads, write_names_gpkg, write_roads_gpkg


def _dump(conn):
    dumped = {}
    for table in TABLE_ORDER:
        columns = TABLE_COLUMNS[table]
        dumped[table] = conn.execute(
            f"SELECT {', '.join(columns)} FROM {table} "
            f"ORDER BY {TABLE_ORDER_BY[table]}"
        ).fetchall()
    return dumped


class StoreLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        self.roads = write_roads_gpkg(self.root / "r.gpkg", sample_roads())

    def tearDown(self):
        self.tmp.cleanup()

    def test_output_zip_name(self):
        self.assertEqual(output_zip_name(), OUTPUT_ZIP_NAME)
        self.assertEqual(output_zip_name(), "openpostcode_uk.zip")

    def test_write_export_and_lookup(self):
        posts = read_postcodes(self.names)
        roads = read_roads(self.roads)
        marks = read_landmarks(self.names)
        collected = []
        for _pos, row in posts.iterrows():
            ranked = features_for_point(row.geometry, roads, marks, cap=5)
            collected.append((row, ranked))
        sqlite = self.root / "lookup.sqlite"
        conn = connect(sqlite)
        write_rows(conn, collected, progress=True)
        before = _dump(conn)
        zpath = export_zip(conn, self.root / "out.zip", progress=True)
        conn.close()
        with zipfile.ZipFile(zpath) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"postcode.csv", "feature.csv", "location.csv"},
            )
            feature_csv = archive.read("feature.csv").decode("utf-8")
            self.assertTrue(feature_csv.startswith("id,kind,name,unnamed,"))
            self.assertIn(",,", feature_csv)
        imported = self.root / "imported.sqlite"
        import_zip(zpath, imported, progress=True)
        conn = sqlite3.connect(imported)
        self.assertEqual(before, _dump(conn))
        conn.close()
        code, out, err = lookup(sqlite, ["sw1a", "1aa"])
        self.assertEqual(code, 0)
        self.assertIn("landmark: The Palace", out)
        self.assertIn("weighted_distance: ", out)
        self.assertIn("kind: landmark", out)
        self.assertIn("populated_place: Nuneaton", out)
        self.assertIn("-------", out)
        code, out, err = lookup(sqlite, ["ZZ99 9ZZ"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "postcode not found")
        code, out, err = lookup(self.root / "missing.sqlite", ["SW1A1AA"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "sqlite not found; run build or import")

        conn = sqlite3.connect(sqlite)
        conn.execute("DELETE FROM location WHERE postcode = 'EMPTY1'")
        conn.commit()
        conn.close()
        code, out, err = lookup(sqlite, ["EMPTY1"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

        connect(sqlite).close()
        self.assertTrue(sqlite.is_file())
        conn = connect(sqlite)
        write_rows(conn, [])
        conn.close()

    def test_feature_key_and_admin(self):
        row = {
            "kind": "road",
            "name": "Mall Road",
            "unnamed": 0,
            "classification": "A Road",
            "local_type": None,
            "distance_m": 10.4,
        }
        post = {
            "populated_place": "Nuneaton",
            "district_borough": "West",
            "county_unitary": "Lon",
            "country": "England",
        }
        attached = attach_road_admin(row, post)
        self.assertEqual(attached["distance_m"], 10)
        self.assertEqual(attached["district_borough"], "West")
        self.assertEqual(attached["populated_place"], "Nuneaton")
        self.assertEqual(len(feature_key(attached)), 9)
        landmark = attach_road_admin(
            {
                "kind": "landmark",
                "name": "Hill",
                "unnamed": 0,
                "classification": None,
                "local_type": "Hill Or Mountain",
                "district_borough": "X",
                "county_unitary": None,
                "country": "Wales",
                "distance_m": 1.2,
            },
            post,
        )
        self.assertEqual(landmark["district_borough"], "X")
        self.assertEqual(landmark["country"], "Wales")
        self.assertEqual(landmark["populated_place"], "Nuneaton")
        own = attach_road_admin(
            {
                "kind": "landmark",
                "name": "Hill",
                "unnamed": 0,
                "classification": None,
                "local_type": "Hill Or Mountain",
                "populated_place": "Own Place",
                "district_borough": "X",
                "county_unitary": None,
                "country": "Wales",
                "distance_m": 1.2,
            },
            post,
        )
        self.assertEqual(own["populated_place"], "Own Place")

    def test_import_zip_requires_tables(self):
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("postcode.csv", "postcode,x,y\n")
        with self.assertRaisesRegex(ValueError, "missing feature.csv"):
            import_zip(bad, self.root / "x.sqlite")

    def test_import_zip_rejects_bad_header(self):
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("postcode.csv", "postcode,x,y\n")
            archive.writestr("feature.csv", "id,kind\n")
            archive.writestr(
                "location.csv",
                "postcode,rank,feature_id,distance_m\n",
            )
        with self.assertRaisesRegex(ValueError, "bad header"):
            import_zip(bad, self.root / "x.sqlite")
