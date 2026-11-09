"""Download and unzip OS GeoPackage products."""

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from tqdm import tqdm

from openpostcode.paths import OUTPUT_ZIP_NAME, ensure_dirs

OPEN_NAMES_LIST = (
    "https://api.os.uk/downloads/v1/products/OpenNames/downloads"
    "?format=GeoPackage&area=GB"
)
OPEN_ROADS_LIST = (
    "https://api.os.uk/downloads/v1/products/OpenRoads/downloads"
    "?format=GeoPackage&area=GB"
)
USER_AGENT = "openpostcode-uk"
PRODUCTS = (
    ("open_names", OPEN_NAMES_LIST, "opname_gpkg_gb.zip"),
    ("open_roads", OPEN_ROADS_LIST, "oproad_gpkg_gb.zip"),
)


def file_md5(path, progress=False):
    path = Path(path)
    size = path.stat().st_size if path.is_file() else 0
    digest = hashlib.md5(usedforsecurity=False)
    with (
        open(path, "rb") as handle,
        tqdm(
            total=size or None,
            unit="B",
            unit_scale=True,
            desc=f"hash {path.name}",
            file=sys.stderr,
            disable=not progress,
        ) as bar,
    ):
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            bar.update(len(chunk))
    return digest.hexdigest()


def load_sources(path):
    if not Path(path).is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_sources(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _request(url):
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def list_product(list_url):
    with urllib.request.urlopen(_request(list_url)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        raise ValueError(f"empty download list for {list_url}")
    item = payload[0]
    return {
        "fileName": item["fileName"],
        "md5": item["md5"].lower(),
        "size": item.get("size"),
        "url": item["url"],
        "list_url": list_url,
    }


def list_all_products():
    listed = {}
    for key, list_url, default_name in PRODUCTS:
        item = list_product(list_url)
        if not item.get("fileName"):
            item["fileName"] = default_name
        listed[key] = item
    return listed


def _load_zip_present(load_dir):
    return (Path(load_dir) / OUTPUT_ZIP_NAME).is_file()


def skip_all_downloads(paths, remote, sources):
    if not paths["sqlite"].is_file():
        return False
    if not _load_zip_present(paths["load"]):
        return False
    for key, item in remote.items():
        recorded = sources.get(key) or {}
        if (recorded.get("md5") or "").lower() != item["md5"]:
            return False
    return True


def download_zip(url, dest, expected_size=None, progress=False):
    dest = Path(dest)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(_request(url)) as response:
        total = response.headers.get("Content-Length")
        total = int(total) if total else expected_size or 0
        with (
            open(tmp, "wb") as handle,
            tqdm(
                total=total or None,
                unit="B",
                unit_scale=True,
                desc=f"download {dest.name}",
                file=sys.stderr,
                disable=not progress,
            ) as bar,
        ):
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                handle.write(chunk)
                bar.update(len(chunk))
    tmp.replace(dest)


def unzip_gpkg(zip_path, extract_dir, progress=False):
    extract_dir = Path(extract_dir)
    written = []
    with zipfile.ZipFile(zip_path) as archive:
        members = [
            info
            for info in archive.infolist()
            if info.filename.lower().endswith(".gpkg")
        ]
        if not members:
            raise ValueError(f"no .gpkg in {zip_path}")
        for info in members:
            name = Path(info.filename).name
            target = extract_dir / name
            total = info.file_size or None
            with (
                archive.open(info) as src,
                open(target, "wb") as out,
                tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    desc=f"extract {name}",
                    file=sys.stderr,
                    disable=not progress,
                ) as bar,
            ):
                while True:
                    chunk = src.read(1024 * 64)
                    if not chunk:
                        break
                    out.write(chunk)
                    bar.update(len(chunk))
            written.append(target)
    return written


def gpkg_beside(zip_path):
    zip_path = Path(zip_path)
    extract_dir = zip_path.parent
    if zip_path.name.endswith("_gpkg_gb.zip"):
        direct = extract_dir / zip_path.name.replace("_gpkg_gb.zip", "_gb.gpkg")
        if direct.is_file():
            return direct
    matches = sorted(extract_dir.glob("*.gpkg"))
    if not matches:
        return None
    lowered = zip_path.name.lower()
    if "name" in lowered:
        for path in matches:
            if "name" in path.name.lower():
                return path
    if "road" in lowered:
        for path in matches:
            if "road" in path.name.lower():
                return path
    return matches[0]


def ensure_product(paths, key, remote, progress=False, log=None, force=False):
    zip_path = paths["extract"] / remote["fileName"]
    if force and zip_path.is_file():
        if log is not None:
            log.write(f"using local {zip_path.name} (--force, skip download)\n")
        gpkg = gpkg_beside(zip_path)
        if gpkg is None or not Path(gpkg).is_file():
            unzip_gpkg(zip_path, paths["extract"], progress=progress)
            gpkg = gpkg_beside(zip_path)
        if gpkg is None:
            raise FileNotFoundError(f"no GeoPackage extracted from {zip_path}")
        return zip_path, Path(gpkg)
    if zip_path.is_file() and file_md5(zip_path, progress=progress) == remote["md5"]:
        if log is not None:
            log.write(f"already present, md5 match: {zip_path.name}\n")
        downloaded = False
    else:
        download_zip(
            remote["url"],
            zip_path,
            expected_size=remote.get("size"),
            progress=progress,
        )
        actual = file_md5(zip_path, progress=progress)
        if actual != remote["md5"]:
            raise ValueError(
                f"md5 mismatch for {zip_path.name}: {actual} != {remote['md5']}"
            )
        downloaded = True
    gpkg = gpkg_beside(zip_path)
    if downloaded or gpkg is None or not Path(gpkg).is_file():
        unzip_gpkg(zip_path, paths["extract"], progress=progress)
        gpkg = gpkg_beside(zip_path)
    if gpkg is None:
        raise FileNotFoundError(f"no GeoPackage extracted from {zip_path}")
    return zip_path, Path(gpkg)


def fetch_extract(paths, progress=False, log=None, force=False):
    ensure_dirs(paths)
    remote = list_all_products()
    sources = load_sources(paths["sources"])
    if not force and skip_all_downloads(paths, remote, sources):
        if log is not None:
            log.write("already present, md5 match: load and sqlite current\n")
        return remote, False
    gpkgs = {}
    for key, item in remote.items():
        zip_path, gpkg = ensure_product(
            paths, key, item, progress=progress, log=log, force=force
        )
        gpkgs[key] = {"zip": zip_path, "gpkg": gpkg, "remote": item}
    return remote, gpkgs
