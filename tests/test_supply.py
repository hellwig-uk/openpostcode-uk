import hashlib
import io
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

from openpostcode.paths import etl_paths
from openpostcode.supply import (
    download_zip,
    ensure_product,
    fetch_extract,
    file_md5,
    gpkg_beside,
    list_all_products,
    list_product,
    load_sources,
    md5s_current,
    save_sources,
    skip_all_downloads,
    unzip_gpkg,
)
from tests.common import (
    sample_names,
    sample_roads,
    write_names_gpkg,
    write_roads_gpkg,
    zip_gpkg,
)


class FakeResponse:
    def __init__(self, body=b"", headers=None):
        self.body = body
        self.headers = headers or {}
        self._pos = 0

    def read(self, size=-1):
        if size is None or size < 0:
            data = self.body[self._pos :]
            self._pos = len(self.body)
            return data
        data = self.body[self._pos : self._pos + size]
        self._pos += len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SupplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = etl_paths(self.root / "etl")
        for key in ("extract", "transform", "load"):
            self.paths[key].mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_md5_and_sources(self):
        path = self.root / "a.bin"
        path.write_bytes(b"abc")
        self.assertEqual(file_md5(path), hashlib.md5(b"abc").hexdigest())
        self.assertEqual(file_md5(path, progress=True), hashlib.md5(b"abc").hexdigest())
        self.assertEqual(load_sources(self.root / "missing.json"), {})
        dest = self.paths["sources"]
        save_sources(dest, {"ok": 1})
        self.assertEqual(load_sources(dest)["ok"], 1)

    def test_list_product(self):
        body = json.dumps(
            [
                {
                    "fileName": "opname_gpkg_gb.zip",
                    "md5": "Ab",
                    "size": 3,
                    "url": "https://blob",
                }
            ]
        ).encode()

        def opener(req, timeout=None):
            self.assertEqual(req.get_header("User-agent"), "openpostcode-uk")
            return FakeResponse(body)

        with mock.patch("urllib.request.urlopen", opener):
            item = list_product("https://example/list")
        self.assertEqual(item["md5"], "ab")
        self.assertEqual(item["url"], "https://blob")

        with mock.patch(
            "urllib.request.urlopen", lambda req, timeout=None: FakeResponse(b"[]")
        ):
            with self.assertRaises(ValueError):
                list_product("https://example/list")

    def test_list_all_products_default_name(self):
        payload = json.dumps(
            [{"fileName": "", "md5": "aa", "size": 1, "url": "https://blob"}]
        ).encode()
        with mock.patch(
            "urllib.request.urlopen",
            lambda req, timeout=None: FakeResponse(payload),
        ):
            listed = list_all_products()
        self.assertEqual(listed["open_names"]["fileName"], "opname_gpkg_gb.zip")
        self.assertEqual(listed["open_roads"]["fileName"], "oproad_gpkg_gb.zip")
        named = json.dumps(
            [
                {
                    "fileName": "opname_gpkg_gb.zip",
                    "md5": "aa",
                    "size": 1,
                    "url": "https://blob",
                }
            ]
        ).encode()
        with mock.patch(
            "urllib.request.urlopen",
            lambda req, timeout=None: FakeResponse(named),
        ):
            listed = list_all_products()
        self.assertEqual(listed["open_names"]["fileName"], "opname_gpkg_gb.zip")

    def test_download_and_unzip(self):
        gpkg = write_names_gpkg(self.root / "opname_gb.gpkg", sample_names())
        zip_path = self.root / "src.zip"
        with ZipFile(zip_path, "w") as archive:
            archive.write(gpkg, arcname="Data/opname_gb.gpkg")
        data = zip_path.read_bytes()
        dest = self.paths["extract"] / "opname_gpkg_gb.zip"

        def opener(req, timeout=None):
            return FakeResponse(data, headers={"Content-Length": str(len(data))})

        with mock.patch("urllib.request.urlopen", opener):
            download_zip("https://blob", dest, expected_size=len(data), progress=True)
        self.assertTrue(dest.is_file())
        written = unzip_gpkg(dest, self.paths["extract"], progress=True)
        self.assertEqual(written[0].name, "opname_gb.gpkg")
        self.assertEqual(gpkg_beside(dest).name, "opname_gb.gpkg")

        empty = self.paths["extract"] / "empty.zip"
        with ZipFile(empty, "w") as archive:
            archive.writestr("readme.txt", "nope")
        with self.assertRaises(ValueError):
            unzip_gpkg(empty, self.paths["extract"])

    def test_download_without_length(self):
        dest = self.paths["extract"] / "x.zip"
        with mock.patch(
            "urllib.request.urlopen",
            lambda req, timeout=None: FakeResponse(b"zzzz", headers={}),
        ):
            download_zip("https://blob", dest, expected_size=None, progress=False)
        self.assertEqual(dest.read_bytes(), b"zzzz")

    def test_gpkg_beside_fallbacks(self):
        extract = self.paths["extract"]
        names_zip = extract / "opname_gpkg_gb.zip"
        names_zip.write_bytes(b"z")
        (extract / "other.gpkg").write_bytes(b"g")
        self.assertEqual(gpkg_beside(names_zip).name, "other.gpkg")
        (extract / "opname_gb.gpkg").write_bytes(b"g")
        self.assertEqual(gpkg_beside(names_zip).name, "opname_gb.gpkg")
        roads_zip = extract / "oproad_gpkg_gb.zip"
        roads_zip.write_bytes(b"z")
        (extract / "oproad_gb.gpkg").write_bytes(b"g")
        self.assertEqual(gpkg_beside(roads_zip).name, "oproad_gb.gpkg")
        lonely = extract / "misc.zip"
        lonely.write_bytes(b"z")
        self.assertEqual(gpkg_beside(lonely).name, "opname_gb.gpkg")
        empty_dir = self.root / "empty"
        empty_dir.mkdir()
        self.assertIsNone(gpkg_beside(empty_dir / "none.zip"))
        named_dir = self.root / "named"
        named_dir.mkdir()
        (named_dir / "opname_extra.zip").write_bytes(b"z")
        (named_dir / "names_only.gpkg").write_bytes(b"g")
        self.assertEqual(
            gpkg_beside(named_dir / "opname_extra.zip").name, "names_only.gpkg"
        )
        road_dir = self.root / "roaded"
        road_dir.mkdir()
        (road_dir / "roads_extra.zip").write_bytes(b"z")
        (road_dir / "roads_only.gpkg").write_bytes(b"g")
        self.assertEqual(
            gpkg_beside(road_dir / "roads_extra.zip").name, "roads_only.gpkg"
        )

    def test_skip_all_and_ensure(self):
        self.assertFalse(skip_all_downloads(self.paths, {}, {}))
        self.paths["sqlite"].write_bytes(b"sql")
        self.assertFalse(skip_all_downloads(self.paths, {}, {}))
        (self.paths["load"] / "openpostcode_uk.zip").write_bytes(b"z")
        remote = {
            "open_names": {"md5": "aa"},
            "open_roads": {"md5": "bb"},
        }
        sources = {
            "open_names": {"md5": "aa"},
            "open_roads": {"md5": "zz"},
        }
        self.assertFalse(skip_all_downloads(self.paths, remote, sources))
        sources["open_roads"]["md5"] = "bb"
        self.assertTrue(skip_all_downloads(self.paths, remote, sources))
        self.assertTrue(md5s_current(remote, sources))
        self.assertFalse(md5s_current({}, sources))

        gpkg = write_roads_gpkg(self.root / "oproad_gb.gpkg", sample_roads())
        zpath = zip_gpkg(gpkg, self.paths["extract"] / "oproad_gpkg_gb.zip")
        digest = file_md5(zpath)
        log = io.StringIO()
        remote_item = {
            "fileName": "oproad_gpkg_gb.zip",
            "md5": digest,
            "size": zpath.stat().st_size,
            "url": "https://blob",
        }
        zip_out, gpkg_out = ensure_product(
            self.paths, "open_roads", remote_item, progress=False, log=log
        )
        self.assertIn("already present, md5 match", log.getvalue())
        self.assertEqual(zip_out, zpath)
        self.assertTrue(gpkg_out.is_file())
        again, again_gpkg = ensure_product(
            self.paths, "open_roads", remote_item, progress=False, log=None
        )
        self.assertTrue(again_gpkg.is_file())
        force_log = io.StringIO()
        with mock.patch("openpostcode.supply.download_zip") as download:
            with mock.patch("openpostcode.supply.file_md5") as hashed:
                forced_zip, forced_gpkg = ensure_product(
                    self.paths,
                    "open_roads",
                    {**remote_item, "md5": "0" * 32},
                    progress=False,
                    log=force_log,
                    force=True,
                )
        download.assert_not_called()
        hashed.assert_not_called()
        self.assertEqual(forced_zip, zpath)
        self.assertTrue(forced_gpkg.is_file())
        self.assertIn("skip download", force_log.getvalue())
        forced_gpkg.unlink()
        with mock.patch("openpostcode.supply.download_zip") as download:
            unzipped_zip, unzipped_gpkg = ensure_product(
                self.paths,
                "open_roads",
                {**remote_item, "md5": "0" * 32},
                progress=False,
                force=True,
            )
        download.assert_not_called()
        self.assertTrue(unzipped_gpkg.is_file())
        with mock.patch("openpostcode.supply.file_md5") as hashed:
            trusted_zip, trusted_gpkg = ensure_product(
                self.paths,
                "open_roads",
                remote_item,
                progress=False,
                log=io.StringIO(),
                recorded_md5=digest,
            )
        hashed.assert_not_called()
        self.assertTrue(trusted_gpkg.is_file())
        ensure_product(
            self.paths,
            "open_roads",
            remote_item,
            progress=False,
            log=None,
            recorded_md5=digest,
        )
        with mock.patch("openpostcode.supply._download_and_verify") as refresh:
            refresh.side_effect = lambda *a, **k: None
            ensure_product(
                self.paths,
                "open_roads",
                {**remote_item, "md5": "11" * 16},
                progress=False,
                recorded_md5="aa" * 16,
            )
        refresh.assert_called()
        with mock.patch("openpostcode.supply.gpkg_beside", return_value=None):
            with mock.patch("openpostcode.supply.unzip_gpkg", return_value=[]):
                with self.assertRaises(FileNotFoundError):
                    ensure_product(
                        self.paths,
                        "open_roads",
                        remote_item,
                        force=True,
                    )

        bad = dict(remote_item)
        bad["md5"] = "0" * 32
        with mock.patch(
            "openpostcode.supply.download_zip",
            lambda *a, **k: zpath.write_bytes(b"nope"),
        ):
            with self.assertRaises(ValueError):
                ensure_product(self.paths, "open_roads", bad, progress=False)

    def test_fetch_extract_skip_and_download(self):
        self.paths["sqlite"].write_bytes(b"sql")
        (self.paths["load"] / "openpostcode_uk.zip").write_bytes(b"z")
        digest = "ab" * 16
        sources = {
            "open_names": {"md5": digest},
            "open_roads": {"md5": digest},
        }
        save_sources(self.paths["sources"], sources)
        remote = {
            "open_names": {
                "fileName": "opname_gpkg_gb.zip",
                "md5": digest,
                "size": 1,
                "url": "https://blob/n",
                "list_url": "https://list/n",
            },
            "open_roads": {
                "fileName": "oproad_gpkg_gb.zip",
                "md5": digest,
                "size": 1,
                "url": "https://blob/r",
                "list_url": "https://list/r",
            },
        }
        names_zip = self.paths["extract"] / "opname_gpkg_gb.zip"
        roads_zip = self.paths["extract"] / "oproad_gpkg_gb.zip"
        names_zip.write_bytes(b"z")
        roads_zip.write_bytes(b"z")
        (self.paths["extract"] / "opname_gb.gpkg").write_bytes(b"g")
        (self.paths["extract"] / "oproad_gb.gpkg").write_bytes(b"g")
        log = io.StringIO()
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("openpostcode.supply.download_zip") as download:
                with mock.patch("openpostcode.supply.file_md5") as hashed:
                    listed, gpkgs = fetch_extract(self.paths, progress=False, log=log)
        self.assertEqual(listed, remote)
        download.assert_not_called()
        hashed.assert_not_called()
        self.assertTrue(gpkgs["open_names"]["gpkg"].is_file())
        self.assertIn("md5 match", log.getvalue())
        dummy_zip = names_zip
        dummy_gpkg = self.paths["extract"] / "opname_gb.gpkg"
        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch(
                "openpostcode.supply.ensure_product",
                return_value=(dummy_zip, dummy_gpkg),
            ) as ensure:
                _listed, gpkgs = fetch_extract(
                    self.paths, progress=False, log=io.StringIO(), force=True
                )
        self.assertIsNot(gpkgs, False)
        self.assertEqual(ensure.call_count, 2)
        with mock.patch(
            "openpostcode.supply.ensure_product",
            return_value=(dummy_zip, dummy_gpkg),
        ) as ensure:
            fetch_extract(self.paths, progress=False, log=None, remote=remote)
        self.assertEqual(ensure.call_count, 2)

        self.paths["sqlite"].unlink()
        names = write_names_gpkg(self.root / "opname_gb.gpkg", sample_names())
        roads = write_roads_gpkg(self.root / "oproad_gb.gpkg", sample_roads())
        nz = zip_gpkg(names, self.root / "n.zip", arcname="opname_gb.gpkg")
        rz = zip_gpkg(roads, self.root / "r.zip", arcname="oproad_gb.gpkg")
        remote["open_names"]["md5"] = file_md5(nz)
        remote["open_roads"]["md5"] = file_md5(rz)
        remote["open_names"]["size"] = nz.stat().st_size
        remote["open_roads"]["size"] = rz.stat().st_size

        def opener(req, timeout=None):
            url = req.full_url
            if url.endswith("/n"):
                return FakeResponse(nz.read_bytes(), headers={"Content-Length": "1"})
            return FakeResponse(rz.read_bytes(), headers={"Content-Length": "1"})

        with mock.patch("openpostcode.supply.list_all_products", return_value=remote):
            with mock.patch("urllib.request.urlopen", opener):
                _listed, gpkgs = fetch_extract(
                    self.paths, progress=False, log=io.StringIO()
                )
        self.assertTrue(gpkgs["open_names"]["gpkg"].is_file())
        self.assertTrue(gpkgs["open_roads"]["gpkg"].is_file())

    def test_ensure_unzip_when_gpkg_missing(self):
        names = write_names_gpkg(self.root / "opname_gb.gpkg", sample_names())
        zpath = zip_gpkg(names, self.paths["extract"] / "opname_gpkg_gb.zip")
        digest = file_md5(zpath)
        remote_item = {
            "fileName": "opname_gpkg_gb.zip",
            "md5": digest,
            "size": 1,
            "url": "https://blob",
        }
        _zip_out, gpkg_out = ensure_product(self.paths, "open_names", remote_item)
        self.assertTrue(gpkg_out.is_file())

    def test_ensure_raises_without_gpkg(self):
        zpath = self.paths["extract"] / "opname_gpkg_gb.zip"
        with ZipFile(zpath, "w") as archive:
            archive.writestr("readme.txt", "x")
        remote_item = {
            "fileName": "opname_gpkg_gb.zip",
            "md5": file_md5(zpath),
            "size": 1,
            "url": "https://blob",
        }
        with mock.patch("openpostcode.supply.unzip_gpkg", return_value=[]):
            with mock.patch("openpostcode.supply.gpkg_beside", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    ensure_product(self.paths, "open_names", remote_item)

    def test_ensure_redownloads_when_local_hash_differs(self):
        stale = self.paths["extract"] / "opname_gpkg_gb.zip"
        stale.write_bytes(b"stale")
        names = write_names_gpkg(self.root / "fresh_names.gpkg", sample_names())
        fresh = zip_gpkg(names, self.root / "fresh.zip")
        digest = file_md5(fresh)
        remote_item = {
            "fileName": "opname_gpkg_gb.zip",
            "md5": digest,
            "size": fresh.stat().st_size,
            "url": "https://blob",
        }

        def fake_download(url, dest, expected_size=None, progress=False):
            Path(dest).write_bytes(fresh.read_bytes())

        with mock.patch("openpostcode.supply.download_zip", fake_download):
            zip_out, gpkg_out = ensure_product(
                self.paths, "open_names", remote_item, progress=False
            )
        self.assertTrue(gpkg_out.is_file())
        self.assertEqual(file_md5(zip_out), digest)
