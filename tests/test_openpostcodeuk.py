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
    CACHE_ENV,
    _cache_dir,
    _declared_version,
    _package_zip,
    _pyproject_version,
    _repo_root_dir,
    _repo_zip,
    ensure_sqlite,
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
        cache = self.root / "cache"
        log = io.StringIO()
        with mock.patch.dict("os.environ", {CACHE_ENV: str(cache)}):
            with mock.patch("openpostcodeuk.load._package_zip", return_value=None):
                with mock.patch(
                    "openpostcodeuk.load._repo_zip", return_value=self.zip_path
                ):
                    first = ensure_sqlite(log=log)
                    second = ensure_sqlite()
            self.assertEqual(first, second)
            self.assertTrue(first.is_file())
            self.assertEqual(first.parent, cache)
            self.assertIn("once per version", log.getvalue())
            self.assertIn("Lookup database ready", log.getvalue())
            with mock.patch(
                "openpostcodeuk.load._package_zip", return_value=self.zip_path
            ):
                with mock.patch(
                    "openpostcodeuk.load._declared_version",
                    return_value="test-zip",
                ):
                    packed = ensure_sqlite(log=io.StringIO())
            self.assertTrue(packed.is_file())
            self.assertEqual(packed.name, "test-zip.sqlite")
            with mock.patch("openpostcodeuk.load._package_zip", return_value=None):
                with mock.patch("openpostcodeuk.load._repo_zip", return_value=None):
                    with self.assertRaises(FileNotFoundError):
                        ensure_sqlite(log=io.StringIO())

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
            with mock.patch(
                "openpostcodeuk.load._pyproject_version", return_value=None
            ):
                self.assertEqual(_declared_version(), "unknown")
        self.assertIsInstance(_declared_version(), str)
        self.assertTrue(_repo_root_dir().is_dir())

    def test_pyproject_version_and_cache_dir(self):
        missing = self.root / "empty"
        missing.mkdir()
        self.assertIsNone(_pyproject_version(missing))
        toml = self.root / "pyproject.toml"
        toml.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        self.assertIsNone(_pyproject_version(self.root))
        toml.write_text("[project]\nversion = '9.9.9'\n", encoding="utf-8")
        self.assertEqual(_pyproject_version(self.root), "9.9.9")
        with mock.patch("openpostcodeuk.load.Path.cwd", return_value=self.root):
            self.assertEqual(_pyproject_version(), "9.9.9")
        with mock.patch(
            "openpostcodeuk.load.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError,
        ):
            with mock.patch(
                "openpostcodeuk.load._pyproject_version", return_value="1.2.3"
            ):
                self.assertEqual(_declared_version(), "1.2.3")
        xdg = self.root / "xdg"
        home = self.root / "home"
        with mock.patch.dict(
            "os.environ",
            {CACHE_ENV: "", "XDG_CACHE_HOME": str(xdg)},
        ):
            self.assertEqual(_cache_dir(), xdg / "openpostcodeuk")
        with mock.patch.dict(
            "os.environ",
            {CACHE_ENV: "", "XDG_CACHE_HOME": ""},
        ):
            with mock.patch("openpostcodeuk.load.Path.home", return_value=home):
                self.assertEqual(_cache_dir(), home / ".cache" / "openpostcodeuk")
        named = self.root / "named-cache"
        with mock.patch.dict("os.environ", {CACHE_ENV: str(named)}):
            self.assertEqual(_cache_dir(), named)

    def test_build_hook_warms_cache_without_packing_sqlite(self):
        build_lib = self.root / "build" / "lib"
        dest = build_lib / "openpostcodeuk" / "data"
        dest.mkdir(parents=True)
        cache = self.root / "install-cache"
        self.assertIsNone(run_build_import(build_lib, log=None, editable=False))
        shutil.copy2(self.zip_path, dest / "openpostcode_uk.zip")
        self.assertIsNone(run_build_import(build_lib, log=None, editable=True))
        with mock.patch.dict(
            "os.environ",
            {CACHE_ENV: str(cache), "OPENPOSTCODEUK_SKIP_IMPORT": "1"},
        ):
            self.assertFalse(should_import_during_build())
            skip_log = io.StringIO()
            self.assertIsNone(run_build_import(build_lib, log=skip_log))
            self.assertIn("OPENPOSTCODEUK_SKIP_IMPORT", skip_log.getvalue())
            self.assertIsNone(run_build_import(build_lib, log=None))
        with mock.patch.dict(
            "os.environ",
            {CACHE_ENV: str(cache), "OPENPOSTCODEUK_SKIP_IMPORT": ""},
        ):
            self.assertTrue(should_import_during_build())
            with mock.patch(
                "openpostcodeuk.load._declared_version", return_value="built"
            ):
                hooked = run_build_import(build_lib, log=None, editable=False)
                again = run_build_import(build_lib, log=None, editable=False)
            with mock.patch(
                "openpostcodeuk.load._declared_version", return_value="logged"
            ):
                log = io.StringIO()
                logged = run_build_import(build_lib, log=log, editable=False)
        self.assertTrue(hooked.is_file())
        self.assertEqual(hooked, again)
        self.assertEqual(hooked.parent, cache)
        self.assertTrue(logged.is_file())
        self.assertFalse((dest / "lookup.sqlite").exists())
        self.assertIn("once per version", log.getvalue())
        with mock.patch.dict("os.environ", {"OPENPOSTCODEUK_SKIP_IMPORT": "yes"}):
            self.assertFalse(should_import_during_build())
        with mock.patch.dict("os.environ", {"OPENPOSTCODEUK_SKIP_IMPORT": "true"}):
            self.assertFalse(should_import_during_build())
