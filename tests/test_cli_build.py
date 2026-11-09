import io
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

from openpostcode.cli import main, main_get
from openpostcode.extract import read_landmarks, read_postcodes, read_roads
from openpostcode.match import features_for_point
from openpostcode.paths import OUTPUT_ZIP_NAME, etl_paths
from openpostcode.store import LOAD_ZIP_URL, connect, export_zip, write_rows
from openpostcode.supply import file_md5
from tests.common import (
    sample_names,
    sample_roads,
    write_names_gpkg,
    write_roads_gpkg,
    zip_gpkg,
)


class CliBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.etl = self.root / "etl"
        self.paths = etl_paths(self.etl)
        for key in ("extract", "transform", "load"):
            self.paths[key].mkdir(parents=True)
        self.names = write_names_gpkg(self.root / "opname_gb.gpkg", sample_names())
        self.roads = write_roads_gpkg(self.root / "oproad_gb.gpkg", sample_roads())
        self.nz = zip_gpkg(
            self.names, self.root / "opname_gpkg_gb.zip", arcname="opname_gb.gpkg"
        )
        self.rz = zip_gpkg(
            self.roads, self.root / "oproad_gpkg_gb.zip", arcname="oproad_gb.gpkg"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _remote(self):
        return {
            "open_names": {
                "fileName": "opname_gpkg_gb.zip",
                "md5": file_md5(self.nz),
                "size": self.nz.stat().st_size,
                "url": "https://blob/n",
                "list_url": "https://list/n",
            },
            "open_roads": {
                "fileName": "oproad_gpkg_gb.zip",
                "md5": file_md5(self.rz),
                "size": self.rz.stat().st_size,
                "url": "https://blob/r",
                "list_url": "https://list/r",
            },
        }

    def test_build_and_get(self):
        remote = self._remote()

        def opener(req, timeout=None):
            url = req.full_url
            data = self.nz.read_bytes() if url.endswith("/n") else self.rz.read_bytes()

            class Resp:
                headers = {"Content-Length": str(len(data))}

                def __init__(self):
                    self._data = data

                def read(self, n=-1):
                    out = self._data
                    self._data = b""
                    return out

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            return Resp()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("urllib.request.urlopen", opener):
                with mock.patch("openpostcode.build.sync_load_zip"):
                    code = main(
                        ["--etl-dir", str(self.etl), "build"],
                        stdout=stdout,
                        stderr=stderr,
                        progress=False,
                    )
                    self.assertEqual(code, 0)
                    zpath = self.paths["load"] / OUTPUT_ZIP_NAME
                    self.assertTrue(zpath.is_file())
                    with ZipFile(zpath) as archive:
                        self.assertEqual(
                            set(archive.namelist()),
                            {"postcode.csv", "feature.csv", "location.csv"},
                        )
                    out = io.StringIO()
                    err = io.StringIO()
                    code = main(
                        ["--etl-dir", str(self.etl), "get", "sw1a", "1aa"],
                        stdout=out,
                        stderr=err,
                        progress=False,
                    )
                    self.assertEqual(code, 0)
                    self.assertIn("The Palace", out.getvalue())
                    missing = io.StringIO()
                    code = main(
                        ["--etl-dir", str(self.etl), "get", "ZZ99", "9ZZ"],
                        stdout=io.StringIO(),
                        stderr=missing,
                        progress=False,
                    )
                    self.assertEqual(code, 1)
                    self.assertIn("postcode not found", missing.getvalue())
                    get_out = io.StringIO()
                    get_err = io.StringIO()
                    code = main_get(
                        ["--etl-dir", str(self.etl), "SW1A1AA"],
                        stdout=get_out,
                        stderr=get_err,
                    )
                    self.assertEqual(code, 0)
                    code = main_get(
                        ["--etl-dir", str(self.etl)],
                        stdout=io.StringIO(),
                        stderr=err,
                    )
                    self.assertEqual(code, 1)
                    self.assertIn("postcode not found", err.getvalue())
                    help_out = io.StringIO()
                    code = main(
                        ["--etl-dir", str(self.etl)],
                        stdout=help_out,
                        progress=False,
                    )
                    self.assertEqual(code, 0)
                    self.assertIn("build", help_out.getvalue())
                    self.assertIn("import", help_out.getvalue())
                    self.assertIn("--force", help_out.getvalue())

    def test_build_skips_when_current(self):
        remote = self._remote()
        self.paths["sqlite"].write_text("x")
        (self.paths["load"] / OUTPUT_ZIP_NAME).write_bytes(b"z")
        from openpostcode.supply import save_sources

        save_sources(
            self.paths["sources"],
            {
                "open_names": {"md5": remote["open_names"]["md5"]},
                "open_roads": {"md5": remote["open_roads"]["md5"]},
            },
        )
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            code = main(
                ["--etl-dir", str(self.etl), "build"],
                progress=False,
                stderr=io.StringIO(),
            )
        self.assertEqual(code, 0)

    def test_entrypoints(self):
        with mock.patch("openpostcode.cli.main", return_value=0):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(
                    str(Path(__file__).resolve().parents[1] / "main.py"),
                    run_name="__main__",
                )
            self.assertEqual(raised.exception.code, 0)
        with mock.patch("openpostcode.cli.main_get", return_value=0):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(
                    str(Path(__file__).resolve().parents[1] / "get.py"),
                    run_name="__main__",
                )
            self.assertEqual(raised.exception.code, 0)

    def test_main_argv_none(self):
        with mock.patch.object(
            sys, "argv", ["main.py", "--etl-dir", str(self.etl), "build"]
        ):
            with mock.patch("openpostcode.cli.cmd_build", return_value=0) as fn:
                self.assertEqual(main(progress=False), 0)
                fn.assert_called()
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["main.py"]):
            with mock.patch("openpostcode.cli.cmd_build") as fn:
                self.assertEqual(main(stdout=out, progress=False), 0)
                fn.assert_not_called()
        self.assertIn("usage:", out.getvalue())
        self.assertIn("--force", out.getvalue())
        with mock.patch.object(sys, "argv", ["get.py", "SW1A1AA"]):
            with mock.patch("openpostcode.cli.cmd_get", return_value=0) as fn:
                self.assertEqual(main_get(), 0)
                fn.assert_called()

    def test_import_rebuilds_sqlite(self):
        posts = read_postcodes(self.names)
        roads = read_roads(self.roads)
        marks = read_landmarks(self.names)
        collected = []
        for _pos, row in posts.iterrows():
            ranked = features_for_point(row.geometry, roads, marks, cap=5)
            collected.append((row, ranked))
        src = self.root / "src.sqlite"
        conn = connect(src)
        write_rows(conn, collected)
        zpath = export_zip(conn, self.root / "src.zip")
        conn.close()

        def fake_download(url, dest, expected_size=None, progress=False):
            self.assertEqual(url, LOAD_ZIP_URL)
            Path(dest).write_bytes(zpath.read_bytes())

        with mock.patch("openpostcode.build.download_zip", fake_download):
            code = main(
                ["--etl-dir", str(self.etl), "import"],
                progress=False,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
        self.assertEqual(code, 0)
        out = io.StringIO()
        code = main(
            ["--etl-dir", str(self.etl), "get", "sw1a", "1aa"],
            stdout=out,
            stderr=io.StringIO(),
            progress=False,
        )
        self.assertEqual(code, 0)
        self.assertIn("The Palace", out.getvalue())

    def test_build_force_flag(self):
        with mock.patch("openpostcode.cli.cmd_build", return_value=0) as fn:
            main(["build", "--force"], progress=False)
        self.assertTrue(fn.call_args.kwargs["force"])

    def test_progress_tty(self):
        with mock.patch.object(sys.stderr, "isatty", return_value=True):
            with mock.patch("openpostcode.cli.cmd_build", return_value=0) as fn:
                main(["--etl-dir", str(self.etl), "build"])
                self.assertTrue(fn.call_args.kwargs["progress"])
                self.assertFalse(fn.call_args.kwargs["force"])
