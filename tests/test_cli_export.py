import io
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

from openpostcode.cli import main, main_get
from openpostcode.export import run_export
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


class CliExportTests(unittest.TestCase):
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

    def _opener(self):
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

        return opener

    def _export_once(self, remote=None):
        remote = remote or self._remote()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("urllib.request.urlopen", self._opener()):
                with mock.patch("openpostcode.export.sync_load_zip"):
                    return main(
                        ["--etl-dir", str(self.etl), "export"],
                        stdout=io.StringIO(),
                        stderr=io.StringIO(),
                        progress=False,
                    )

    def test_export_and_get(self):
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
                with mock.patch("openpostcode.export.sync_load_zip"):
                    code = main(
                        ["--etl-dir", str(self.etl), "export"],
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
                    self.assertIn("export", help_out.getvalue())
                    self.assertIn("import", help_out.getvalue())
                    self.assertIn("--force", help_out.getvalue())

    def test_export_skips_when_current(self):
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
            with mock.patch("openpostcode.export.transform_all") as transform:
                with mock.patch("openpostcode.supply.download_zip") as download:
                    log = io.StringIO()
                    code = main(
                        ["--etl-dir", str(self.etl), "export"],
                        progress=False,
                        stderr=log,
                    )
        self.assertEqual(code, 0)
        transform.assert_not_called()
        download.assert_not_called()
        self.assertIn("load and sqlite current", log.getvalue())
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            self.assertEqual(run_export(self.paths, progress=False, log=None), 0)

    def test_export_writes_zip_from_sqlite(self):
        remote = self._remote()
        self.assertEqual(self._export_once(remote), 0)
        zpath = self.paths["load"] / OUTPUT_ZIP_NAME
        zpath.unlink()
        log = io.StringIO()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("openpostcode.export.transform_all") as transform:
                with mock.patch("openpostcode.supply.download_zip") as download:
                    with mock.patch("openpostcode.export.sync_load_zip"):
                        code = run_export(self.paths, progress=False, log=None)
                        zpath.unlink()
                        code_logged = run_export(self.paths, progress=False, log=log)
        self.assertEqual(code, 0)
        self.assertEqual(code_logged, 0)
        transform.assert_not_called()
        download.assert_not_called()
        self.assertTrue(zpath.is_file())
        self.assertIn("write load zip from sqlite", log.getvalue())

    def test_export_rebuilds_sqlite_from_load_zip(self):
        remote = self._remote()
        self.assertEqual(self._export_once(remote), 0)
        self.paths["sqlite"].unlink()
        log = io.StringIO()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("openpostcode.export.transform_all") as transform:
                with mock.patch("openpostcode.supply.download_zip") as download:
                    code = run_export(self.paths, progress=False, log=None)
                    self.paths["sqlite"].unlink()
                    code_logged = run_export(self.paths, progress=False, log=log)
        self.assertEqual(code, 0)
        self.assertEqual(code_logged, 0)
        transform.assert_not_called()
        download.assert_not_called()
        self.assertTrue(self.paths["sqlite"].is_file())
        self.assertIn("rebuild sqlite from load zip", log.getvalue())
        out = io.StringIO()
        code = main(
            ["--etl-dir", str(self.etl), "get", "sw1a", "1aa"],
            stdout=out,
            stderr=io.StringIO(),
            progress=False,
        )
        self.assertEqual(code, 0)
        self.assertIn("The Palace", out.getvalue())

    def test_export_rematches_when_sqlite_and_zip_missing(self):
        remote = self._remote()
        self.assertEqual(self._export_once(remote), 0)
        self.paths["sqlite"].unlink()
        (self.paths["load"] / OUTPUT_ZIP_NAME).unlink()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("openpostcode.supply.download_zip") as download:
                with mock.patch("openpostcode.export.sync_load_zip"):
                    code = main(
                        ["--etl-dir", str(self.etl), "export"],
                        progress=False,
                        stderr=io.StringIO(),
                    )
        self.assertEqual(code, 0)
        download.assert_not_called()
        self.assertTrue(self.paths["sqlite"].is_file())
        self.assertTrue((self.paths["load"] / OUTPUT_ZIP_NAME).is_file())

    def test_export_rebuilds_when_md5_changes(self):
        remote = self._remote()
        self.assertEqual(self._export_once(remote), 0)
        stale = {
            "open_names": {**remote["open_names"], "md5": "00" * 16},
            "open_roads": remote["open_roads"],
        }
        gpkgs = {
            "open_names": {
                "gpkg": self.names,
                "zip": self.nz,
                "remote": stale["open_names"],
            },
            "open_roads": {
                "gpkg": self.roads,
                "zip": self.rz,
                "remote": stale["open_roads"],
            },
        }
        with mock.patch("openpostcode.supply.list_all_products", return_value=stale):
            with mock.patch(
                "openpostcode.supply.fetch_extract",
                return_value=(stale, gpkgs),
            ) as fetch:
                with mock.patch("openpostcode.export.sync_load_zip"):
                    code = main(
                        ["--etl-dir", str(self.etl), "export"],
                        progress=False,
                        stderr=io.StringIO(),
                    )
        self.assertEqual(code, 0)
        fetch.assert_called()
        self.assertTrue((self.paths["load"] / OUTPUT_ZIP_NAME).is_file())

    def test_export_force_rematches(self):
        remote = self._remote()
        self.assertEqual(self._export_once(remote), 0)
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("openpostcode.supply.download_zip") as download:
                with mock.patch("openpostcode.export.sync_load_zip"):
                    code = main(
                        ["--etl-dir", str(self.etl), "export", "--force"],
                        progress=False,
                        stderr=io.StringIO(),
                    )
        self.assertEqual(code, 0)
        download.assert_not_called()
        self.assertTrue(self.paths["sqlite"].is_file())
        self.assertTrue((self.paths["load"] / OUTPUT_ZIP_NAME).is_file())

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
            sys, "argv", ["main.py", "--etl-dir", str(self.etl), "export"]
        ):
            with mock.patch("openpostcode.cli.cmd_export", return_value=0) as fn:
                self.assertEqual(main(progress=False), 0)
                fn.assert_called()
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["main.py"]):
            with mock.patch("openpostcode.cli.cmd_export") as fn:
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

        with mock.patch("openpostcode.supply.download_zip", fake_download):
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

    def test_export_force_flag(self):
        with mock.patch("openpostcode.cli.cmd_export", return_value=0) as fn:
            main(["export", "--force"], progress=False)
        self.assertTrue(fn.call_args.kwargs["force"])

    def test_progress_tty(self):
        with mock.patch.object(sys.stderr, "isatty", return_value=True):
            with mock.patch("openpostcode.cli.cmd_export", return_value=0) as fn:
                main(["--etl-dir", str(self.etl), "export"])
                self.assertTrue(fn.call_args.kwargs["progress"])
                self.assertFalse(fn.call_args.kwargs["force"])
