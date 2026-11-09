import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import geopandas as gpd
from shapely.geometry import LineString, Point

from openpostcode.extract import (
    _count_rows,
    _id_column,
    find_layer,
    names_layer,
    read_landmarks,
    read_postcodes,
    read_roads,
    roads_layer,
)
from tests.common import sample_names, sample_roads, write_names_gpkg, write_roads_gpkg


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_postcodes_landmarks_roads(self):
        names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        roads = write_roads_gpkg(self.root / "r.gpkg", sample_roads())
        posts = read_postcodes(names)
        self.assertIn("SW1A1AA", set(posts["postcode"]))
        self.assertIn("EMPTY1", set(posts["postcode"]))
        marks = read_landmarks(names)
        self.assertEqual(
            set(marks["name"]), {"The Palace", "Far Hill", "On Mall", "Nuneaton"}
        )
        links = read_roads(roads)
        mall = links[links["name"] == "Mall Road"].iloc[0]
        self.assertEqual(int(mall["unnamed"]), 0)
        numbered = links[links["name"] == "A302"].iloc[0]
        self.assertEqual(int(numbered["unnamed"]), 0)
        unnamed = links[links["name"] == "unnamed"].iloc[0]
        self.assertEqual(int(unnamed["unnamed"]), 1)
        self.assertEqual(names_layer(names), "namedplace")
        self.assertEqual(roads_layer(roads), "road_link")

    def test_missing_admin_and_id(self):
        records = [
            {
                "Id": "AA1AA",
                "name1": "AA1AA",
                "local_type": "Postcode",
                "geometry": Point(0, 0),
            }
        ]
        path = write_names_gpkg(self.root / "n2.gpkg", records)
        posts = read_postcodes(path)
        self.assertEqual(posts.iloc[0]["postcode"], "AA1AA")
        self.assertTrue(posts.iloc[0]["district_borough"] is None)

    def test_wrong_crs(self):
        frame = gpd.GeoDataFrame(
            {"id": ["A"], "name1": ["A"], "local_type": ["Postcode"]},
            geometry=[Point(0, 0)],
            crs="EPSG:4326",
        )
        path = self.root / "bad.gpkg"
        frame.to_file(path, layer="namedplace", driver="GPKG")
        with self.assertRaises(ValueError):
            read_postcodes(path)

    def test_find_layer_and_id_errors(self):
        frame = gpd.GeoDataFrame(
            {"foo": [1]},
            geometry=[Point(0, 0)],
            crs="EPSG:27700",
        )
        path = self.root / "x.gpkg"
        frame.to_file(path, layer="other", driver="GPKG")
        with self.assertRaises(ValueError):
            find_layer(path, {"local_type", "name1"})
        with self.assertRaises(ValueError):
            _id_column(frame)
        roads_alt = write_roads_gpkg(
            self.root / "alt.gpkg",
            sample_roads(),
            layer="highways",
        )
        self.assertEqual(roads_layer(roads_alt), "highways")

    def test_landmarks_without_optional_columns(self):
        records = [
            {
                "id": "h1",
                "name1": "Hill",
                "local_type": "Hill Or Mountain",
                "geometry": Point(1, 1),
            }
        ]
        path = write_names_gpkg(self.root / "lm.gpkg", records)
        marks = read_landmarks(path)
        self.assertEqual(marks.iloc[0]["name"], "Hill")
        roads_min = write_roads_gpkg(
            self.root / "min.gpkg",
            [{"name_1": "Only", "geometry": LineString([(0, 0), (1, 0)])}],
        )
        links = read_roads(roads_min)
        self.assertEqual(links.iloc[0]["name"], "Only")

    def test_read_postcodes_chunked_and_empty(self):
        names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        posts = read_postcodes(names, progress=True, chunk_size=1)
        self.assertIn("SW1A1AA", set(posts["postcode"]))
        self.assertGreaterEqual(len(posts), 3)
        boxed = read_postcodes(names, bbox=(0, 0, 200, 200), chunk_size=10)
        self.assertIn("SW1A1AA", set(boxed["postcode"]))
        only_place = write_names_gpkg(
            self.root / "none.gpkg",
            [
                {
                    "id": "h1",
                    "name1": "Hill",
                    "local_type": "Hill Or Mountain",
                    "geometry": Point(1, 1),
                }
            ],
        )
        empty = read_postcodes(only_place, chunk_size=0)
        self.assertEqual(len(empty), 0)

    def test_count_rows_sqlite_errors(self):
        names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        layer = names_layer(names)
        self.assertGreaterEqual(_count_rows(names, layer), 1)
        self.assertGreaterEqual(_count_rows(names, layer, "local_type = 'Postcode'"), 1)
        with mock.patch(
            "openpostcode.extract.sqlite3.connect",
            side_effect=sqlite3.Error("nope"),
        ):
            self.assertIsNone(_count_rows(names, layer))
        with mock.patch("openpostcode.extract.sqlite3.connect") as connect:
            conn = mock.MagicMock()
            conn.execute.side_effect = sqlite3.Error("bad sql")
            connect.return_value = conn
            self.assertIsNone(_count_rows(names, layer, "local_type = 'Postcode'"))
            conn.close.assert_called()
