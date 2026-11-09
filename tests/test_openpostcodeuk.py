import importlib.metadata
import io
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import openpostcodeuk as opuk
from openpostcode.extract import read_landmarks, read_postcodes, read_roads
from openpostcode.match import features_for_point
from openpostcode.store import connect, export_zip, write_rows
from openpostcode.tables import import_zip
from openpostcodeuk.api import FEATURE_KEYS, get
from openpostcodeuk.cli import main
from openpostcodeuk.load import (
    _distribution_version,
    _installed_sqlite,
    _package_zip,
    _repo_root_dir,
    _repo_zip,
    ensure_sqlite,
    import_into_data_dir,
    run_build_import,
    should_import_during_build,
)
from tests.common import sample_names, sample_roads, write_names_gpkg, write_roads_gpkg


class OpenpostcodeukTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        names = write_names_gpkg(self.root / "n.gpkg", sample_names())
        roads = write_roads_gpkg(self.root / "r.gpkg", sample_roads())
        posts = read_postcodes(names)
        road_rows = read_roads(roads)
        marks = read_landmarks(names)
        collected = []
        for _pos, row in posts.iterrows():
            ranked = features_for_point(row.geometry, road_rows, marks, cap=5)
            collected.append((row, ranked))
        self.sqlite = self.root / "lookup.sqlite"
        conn = connect(self.sqlite)
        write_rows(conn, collected)
        self.zip_path = export_zip(conn, self.root / "openpostcode_uk.zip")
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_returns_postcode_then_dicts(self):
        with mock.patch("openpostcodeuk.api.ensure_sqlite", return_value=self.sqlite):
            missing = opuk.get("ZZ99 9ZZ")
            hit = opuk.get("sw1a 1aa")
        self.assertIsNone(missing)
        self.assertEqual(hit[0], "SW1A1AA")
        self.assertGreater(len(hit), 1)
        palace = next(item for item in hit[1:] if "The Palace" in item.values())
        self.assertEqual(palace["landmark"], "The Palace")
        self.assertNotIn("kind", palace)
        self.assertEqual(list(palace.keys()), ["landmark", *FEATURE_KEYS])
        self.assertIsInstance(palace["weighted_distance"], int)
        self.assertIsInstance(palace["unnamed"], int)
        self.assertIsNone(palace["classification"])
        conn = sqlite3.connect(self.sqlite)
        conn.execute("DELETE FROM location WHERE postcode = 'SW1A1AB'")
        conn.commit()
        conn.close()
        with mock.patch("openpostcodeuk.api.ensure_sqlite", return_value=self.sqlite):
            only = get("SW1A1AB")
        self.assertEqual(only, ["SW1A1AB"])
        with mock.patch(
            "openpostcodeuk.api.ensure_sqlite",
            return_value=self.root / "missing.sqlite",
        ):
            with self.assertRaises(FileNotFoundError):
                get("SW1A1AA")

    def test_cli_matches_lookup_text(self):
        with mock.patch("openpostcodeuk.cli.ensure_sqlite", return_value=self.sqlite):
            out = io.StringIO()
            err = io.StringIO()
            code = main(["SW1A", "1AA"], stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertIn("landmark: The Palace", out.getvalue())
        self.assertIn("kind: landmark", out.getvalue())
        with mock.patch("openpostcodeuk.cli.ensure_sqlite", return_value=self.sqlite):
            err = io.StringIO()
            code = main(["ZZ99", "9ZZ"], stdout=io.StringIO(), stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("postcode not found", err.getvalue())
        err = io.StringIO()
        self.assertEqual(main([], stdout=io.StringIO(), stderr=err), 1)
        self.assertIn("postcode not found", err.getvalue())
        with mock.patch(
            "openpostcodeuk.cli.ensure_sqlite",
            side_effect=FileNotFoundError,
        ):
            err = io.StringIO()
            code = main(["SW1A1AA"], stdout=io.StringIO(), stderr=err)
        self.assertEqual(code, 1)
        self.assertIn("sqlite not found; run export or import", err.getvalue())
        with mock.patch("sys.argv", ["openpostcode_uk"]):
            err = io.StringIO()
            with mock.patch("sys.stderr", err):
                with mock.patch("sys.stdout", io.StringIO()):
                    code = main()
        self.assertEqual(code, 1)
        self.assertIn("postcode not found", err.getvalue())

    def test_ensure_sqlite_from_repo_zip_and_cache(self):
        imported = import_zip(self.zip_path, self.root / "fromzip.sqlite")
        self.assertTrue(Path(imported).is_file())
        with mock.patch("openpostcodeuk.load._installed_sqlite", return_value=None):
            with mock.patch("openpostcodeuk.load._package_zip", return_value=None):
                with mock.patch(
                    "openpostcodeuk.load._repo_zip", return_value=self.zip_path
                ):
                    first = ensure_sqlite()
                    second = ensure_sqlite()
            self.assertEqual(first, second)
            self.assertTrue(first.is_file())
            with mock.patch(
                "openpostcodeuk.load._package_zip", return_value=self.zip_path
            ):
                with mock.patch(
                    "openpostcodeuk.load._distribution_version",
                    return_value="test-zip",
                ):
                    packed = ensure_sqlite()
            self.assertTrue(packed.is_file())
            with mock.patch("openpostcodeuk.load._package_zip", return_value=None):
                with mock.patch("openpostcodeuk.load._repo_zip", return_value=None):
                    with self.assertRaises(FileNotFoundError):
                        ensure_sqlite()
        with mock.patch(
            "openpostcodeuk.load._installed_sqlite", return_value=self.sqlite
        ):
            self.assertEqual(ensure_sqlite(), self.sqlite)

    def test_package_zip_errors_and_empty(self):
        class Boom:
            def joinpath(self, *args):
                return self

            def is_file(self):
                raise OSError("nope")

            def stat(self):
                raise FileNotFoundError("gone")

        with mock.patch("openpostcodeuk.load.files", return_value=Boom()):
            self.assertIsNone(_package_zip())

        class Missing:
            def joinpath(self, *args):
                return self

            def is_file(self):
                raise FileNotFoundError("gone")

        with mock.patch("openpostcodeuk.load.files", return_value=Missing()):
            self.assertIsNone(_package_zip())

        class Empty:
            def joinpath(self, *args):
                return self

            def is_file(self):
                return True

            def stat(self):
                return mock.Mock(st_size=0)

        with mock.patch("openpostcodeuk.load.files", return_value=Empty()):
            self.assertIsNone(_package_zip())

        class Present:
            def joinpath(self, *args):
                return self

            def is_file(self):
                return True

            def stat(self):
                return mock.Mock(st_size=10)

        with mock.patch("openpostcodeuk.load.files", return_value=Present()):
            self.assertIsInstance(_package_zip(), Present)
        load = self.root / "etl" / "load"
        load.mkdir(parents=True)
        zpath = load / "openpostcode_uk.zip"
        zpath.write_bytes(b"")
        with mock.patch("openpostcodeuk.load._repo_root_dir", return_value=self.root):
            self.assertIsNone(_repo_zip())
            zpath.write_bytes(b"data")
            self.assertEqual(_repo_zip(), zpath)
        with mock.patch(
            "openpostcodeuk.load.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError,
        ):
            self.assertEqual(_distribution_version(), "unknown")
        self.assertIsInstance(_distribution_version(), str)
        self.assertTrue(_repo_root_dir().is_dir())

    def test_import_into_data_dir_and_build_hook(self):
        data = self.root / "openpostcodeuk" / "data"
        data.mkdir(parents=True)
        self.assertIsNone(import_into_data_dir(data, log=None))
        shutil.copy2(self.zip_path, data / "openpostcode_uk.zip")
        log = io.StringIO()
        built = import_into_data_dir(data, log=log)
        self.assertTrue(built.is_file())
        self.assertIn("one-time install step", log.getvalue())
        log2 = io.StringIO()
        again = import_into_data_dir(data, log=log2)
        self.assertEqual(again, built)
        self.assertIn("already present", log2.getvalue())
        self.assertEqual(import_into_data_dir(data, log=None), built)

        build_lib = self.root / "build" / "lib"
        dest = build_lib / "openpostcodeuk" / "data"
        dest.mkdir(parents=True)
        shutil.copy2(self.zip_path, dest / "openpostcode_uk.zip")
        self.assertIsNone(run_build_import(build_lib, log=None, editable=True))
        with mock.patch.dict("os.environ", {"OPENPOSTCODEUK_SKIP_IMPORT": "1"}):
            self.assertFalse(should_import_during_build())
            skip_log = io.StringIO()
            self.assertIsNone(run_build_import(build_lib, log=skip_log))
            self.assertIn("OPENPOSTCODEUK_SKIP_IMPORT", skip_log.getvalue())
            self.assertIsNone(run_build_import(build_lib, log=None))
        with mock.patch.dict("os.environ", {"OPENPOSTCODEUK_SKIP_IMPORT": ""}):
            self.assertTrue(should_import_during_build())
            hooked = run_build_import(build_lib, log=None, editable=False)
        self.assertTrue(hooked.is_file())
        with mock.patch.dict("os.environ", {"OPENPOSTCODEUK_SKIP_IMPORT": "yes"}):
            self.assertFalse(should_import_during_build())
        with mock.patch("openpostcodeuk.load._usable_file", return_value=False):
            self.assertIsNone(_installed_sqlite())
        with mock.patch("openpostcodeuk.load._usable_file", return_value=True):
            self.assertEqual(_installed_sqlite().name, "lookup.sqlite")
