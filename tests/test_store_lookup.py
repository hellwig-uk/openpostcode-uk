import sqlite3
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from opennames.extract import read_landmarks, read_postcodes, read_roads
from opennames.lookup import lookup
from opennames.match import features_for_point
from opennames.store import (
    attach_road_admin,
    connect,
    export_zip,
    feature_key,
    output_zip_name,
    write_rows,
)
from tests.common import sample_names, sample_roads, write_names_gpkg, write_roads_gpkg


class StoreLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        self.roads = write_roads_gpkg(self.root / "r.gpkg", sample_roads())

    def tearDown(self):
        self.tmp.cleanup()

    def test_output_zip_name(self):
        self.assertEqual(
            output_zip_name(date(2026, 11, 7)),
            "openpostcode_uk_2026311.zip",
        )

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
        zpath = export_zip(conn, self.root / "out.zip", progress=True)
        conn.close()
        with zipfile.ZipFile(zpath) as archive:
            self.assertEqual(set(archive.namelist()), {"postcodes.csv", "features.csv"})
        code, out, err = lookup(sqlite, ["sw1a", "1aa"])
        self.assertEqual(code, 0)
        self.assertIn("The Palace = ", out)
        self.assertIn("kind: landmark", out)
        self.assertIn("populated_place: Nuneaton", out)
        self.assertIn("-------", out)
        code, out, err = lookup(sqlite, ["ZZ99 9ZZ"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "postcode not found")
        code, out, err = lookup(self.root / "missing.sqlite", ["SW1A1AA"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "sqlite not found; run build")

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
