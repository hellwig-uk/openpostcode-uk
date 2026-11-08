import tempfile
import unittest
from pathlib import Path

from shapely.geometry import LineString, Point

from opennames.build import transform_all
from opennames.extract import read_landmarks, read_postcodes, read_roads
from opennames.match import (
    _ensure_landmark_index,
    _ensure_road_index,
    _landmark_index,
    _landmarks_for_point,
    _query_dwithin,
    _road_index,
    assign_tiles,
    attach_landmarks,
    features_for_point,
    match_tile,
    merge_ranked,
    unique_roads_for_point,
    unique_roads_for_points,
)
from tests.common import sample_names, sample_roads, write_names_gpkg, write_roads_gpkg


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        self.roads = write_roads_gpkg(self.root / "r.gpkg", sample_roads())

    def tearDown(self):
        self.tmp.cleanup()

    def test_unique_roads_and_landmarks(self):
        posts = read_postcodes(self.names)
        roads = read_roads(self.roads)
        marks = read_landmarks(self.names)
        urban = posts[posts["postcode"] == "SW1A1AA"].iloc[0]
        ranked = features_for_point(urban.geometry, roads, marks, cap=5)
        names = [row["name"] for row in ranked]
        self.assertEqual(names[0], "The Palace")
        self.assertIn("unnamed", names)
        self.assertNotIn("Far Hill", names)
        self.assertLessEqual(sum(1 for row in ranked if row["kind"] == "road"), 5)

        empty_ranked = unique_roads_for_point(Point(0, 0), roads.iloc[0:0])
        self.assertEqual(empty_ranked, [])
        none_ranked = unique_roads_for_point(Point(0, 0), None)
        self.assertEqual(none_ranked, [])
        grown = unique_roads_for_point(urban.geometry, roads, cap=len(roads))
        self.assertIn("Far Lane", [row["name"] for row in grown])
        far = unique_roads_for_point(Point(1e8, 1e8), roads, cap=5)
        self.assertEqual(far, [])
        on_road = features_for_point(Point(100, 80), roads, marks, cap=5)
        self.assertTrue(any(row["distance_m"] == 0 for row in on_road))
        dropped = roads.drop(columns=["classification"])
        self.assertTrue(unique_roads_for_point(urban.geometry, dropped, cap=1))

    def test_no_named_road_uses_unnamed_threshold(self):
        roads = read_roads(self.roads)
        unnamed_only = roads[roads["unnamed"] == 1]
        marks = read_landmarks(self.names)
        point = Point(90, 100)
        ranked = features_for_point(point, unnamed_only, marks, cap=5)
        kinds = {row["kind"] for row in ranked}
        self.assertIn("road", kinds)

    def test_no_roads_takes_nearest_landmarks(self):
        marks = read_landmarks(self.names)
        ranked = features_for_point(Point(101, 100), None, marks, cap=5)
        self.assertGreaterEqual(len(ranked), 1)
        self.assertEqual(
            _landmarks_for_point(Point(1e8, 1e8), marks, None, cap=5),
            [],
        )
        self.assertEqual(
            _landmarks_for_point(Point(1e8, 1e8), marks, 0.5, cap=5),
            [],
        )
        self.assertTrue(all(row["kind"] == "landmark" for row in ranked))
        self.assertEqual(
            features_for_point(Point(0, 0), None, marks.iloc[0:0], cap=5),
            [],
        )
        twins = write_names_gpkg(
            self.root / "twins.gpkg",
            [
                {
                    "id": "h1",
                    "name1": "Twin Hill",
                    "local_type": "Hill Or Mountain",
                    "geometry": Point(0, 0),
                },
                {
                    "id": "h2",
                    "name1": "Twin Hill",
                    "local_type": "Hill Or Mountain",
                    "geometry": Point(400, 0),
                },
            ],
        )
        twin_marks = read_landmarks(twins)
        self.assertEqual(
            len(_landmarks_for_point(Point(0, 0), twin_marks, None, cap=1)),
            1,
        )
        twin_ranked = features_for_point(Point(0, 0), None, twin_marks, cap=2)
        self.assertEqual(twin_ranked[0]["name"], "Twin Hill")
        self.assertEqual(twin_ranked[0]["distance_m"], 0)
        self.assertIsNone(_ensure_landmark_index({"n": 0}))
        self.assertIsNone(_ensure_landmark_index(twin_marks.iloc[0:0]))
        packed = _landmark_index(twin_marks)
        self.assertIs(_ensure_landmark_index(packed), packed)
        self.assertEqual(attach_landmarks(Point(0, 0), [], {"n": 0}), [])
        edge = write_names_gpkg(
            self.root / "edge.gpkg",
            [
                {
                    "id": "e1",
                    "name1": "Edge Hill",
                    "local_type": "Hill Or Mountain",
                    "geometry": Point(5, 0),
                }
            ],
        )
        edge_hits = _landmarks_for_point(Point(0, 0), read_landmarks(edge), 5)
        self.assertEqual(edge_hits, [])

    def test_merge_ranked(self):
        roads = [{"name": "A", "unnamed": 0, "kind": "road", "distance_m": 10}]
        lms = [
            {"name": "L", "unnamed": 0, "kind": "landmark", "distance_m": 4},
            {"name": "Far", "unnamed": 0, "kind": "landmark", "distance_m": 50},
        ]
        mixed, threshold = merge_ranked(roads, lms)
        self.assertEqual(threshold, 10)
        self.assertEqual([row["name"] for row in mixed], ["L", "A"])
        mixed2, threshold2 = merge_ranked(
            [{"name": "u", "unnamed": 1, "kind": "road", "distance_m": 3}],
            lms,
        )
        self.assertEqual(threshold2, 3)
        mixed3, threshold3 = merge_ranked([], lms)
        self.assertIsNone(threshold3)
        self.assertEqual(len(mixed3), 2)

    def test_match_tile_and_expand(self):
        posts = assign_tiles(read_postcodes(self.names))
        group = posts[posts["postcode"] == "SW1A1AA"]
        seen = {"n": 0}

        def cb():
            seen["n"] += 1

        status = []
        rows = match_tile(
            group,
            self.roads,
            self.names,
            cap=5,
            progress_cb=cb,
            status_cb=status.append,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(seen["n"], 1)
        self.assertTrue(any("reading roads" in item for item in status))
        _row, ranked = rows[0]
        self.assertGreaterEqual(len(ranked), 1)
        rural = posts[posts["postcode"] == "EMPTY1"]
        rural_rows = match_tile(rural, self.roads, self.names, cap=5)
        names = [item["name"] for item in rural_rows[0][1]]
        self.assertIn("Far Lane", names)

        far_names = write_names_gpkg(
            self.root / "far_n.gpkg",
            [
                {
                    "id": "ZZ1AA",
                    "name1": "ZZ1AA",
                    "name2": None,
                    "local_type": "Postcode",
                    "district_borough": None,
                    "county_unitary": None,
                    "country": None,
                    "geometry": Point(200000, 200000),
                }
            ],
        )
        far_roads = write_roads_gpkg(
            self.root / "far_r.gpkg",
            [
                {
                    "name_1": "Near End",
                    "name_2": None,
                    "road_classification": "Local Road",
                    "road_classification_number": None,
                    "geometry": LineString([(200000, 200000), (200010, 200000)]),
                },
                {
                    "name_1": "Distant End",
                    "name_2": None,
                    "road_classification": "Local Road",
                    "road_classification_number": None,
                    "geometry": LineString([(180000, 200000), (180010, 200000)]),
                },
            ],
        )
        far_posts = assign_tiles(read_postcodes(far_names))
        expand_notes = []
        far_rows = match_tile(
            far_posts,
            far_roads,
            far_names,
            cap=5,
            status_cb=expand_notes.append,
        )
        far_hit_names = [item["name"] for item in far_rows[0][1]]
        self.assertIn("Distant End", far_hit_names)
        self.assertTrue(any("expand" in item for item in expand_notes))
        silent = match_tile(far_posts, far_roads, far_names, cap=5)
        self.assertIn("Distant End", [item["name"] for item in silent[0][1]])

    def test_cap_limits_unique_names(self):
        roads = read_roads(self.roads)
        point = Point(100, 100)
        ranked = unique_roads_for_point(point, roads, cap=2)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(len({row["name"] for row in ranked}), 2)
        self.assertEqual(unique_roads_for_point(point, {}), [])
        packed_roads = _road_index(roads)
        self.assertIs(_ensure_road_index(packed_roads), packed_roads)
        self.assertIsNone(_ensure_landmark_index(None))
        self.assertIsNone(_ensure_landmark_index({}))
        self.assertIsNone(_ensure_landmark_index({"n": 0}))
        self.assertIsNone(_ensure_landmark_index({"n": False}))
        bulk = unique_roads_for_points([], roads, cap=2)
        self.assertEqual(bulk, [])
        from shapely import STRtree

        tree = STRtree(roads.geometry.values)
        empty_inp, empty_tr = _query_dwithin(tree, len(roads), [], 10)
        self.assertEqual(list(empty_inp), [])
        scalar_inp, scalar_tr = _query_dwithin(tree, len(roads), point, 200)
        self.assertEqual(len(scalar_inp), len(scalar_tr))
        z_inp, z_tr = _query_dwithin(tree, 0, point, 200)
        self.assertEqual(list(z_inp), [])
        miss_inp, miss_tr = _query_dwithin(tree, len(roads), point, 0.01)
        self.assertEqual(list(miss_inp), [])

    def test_transform_all_with_progress(self):
        rows = transform_all(self.names, self.roads, progress=True)
        self.assertGreaterEqual(len(rows), 1)
        written = []
        empty = transform_all(
            self.names,
            self.roads,
            progress=False,
            writer=written.extend,
        )
        self.assertEqual(empty, [])
        self.assertGreaterEqual(len(written), 1)
