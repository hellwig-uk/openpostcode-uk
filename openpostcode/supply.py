"""Download and unzip OS GeoPackage products."""

import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from datetime import timezone
from email.utils import parsedate_to_datetime
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


def _request(url, method="GET"):
    return urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method=method
    )


def fetch_json(url):
    with urllib.request.urlopen(_request(url)) as response:
        return json.loads(response.read().decode("utf-8"))


def zip_last_modified(url):
    with urllib.request.urlopen(_request(url, method="HEAD")) as response:
        raw = response.headers.get("Last-Modified")
    if not raw:
        raise ValueError(f"no Last-Modified for {url}")
    parsed = parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def package_version(remote):
    latest = None
    for item in remote.values():
        url = item.get("url")
        if not url:
            continue
        stamp = zip_last_modified(url)
        if latest is None or stamp > latest:
            latest = stamp
    if latest is None:
        raise ValueError("no Last-Modified on OS product zips")
    return f"1.{latest.year}.{latest.timetuple().tm_yday}"


def write_project_version(path, version):
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    replaced = False
    for line in lines:
        if not replaced and re.match(r"^version\s*=", line):
            out.append(f'version = "{version}"\n')
            replaced = True
        else:
            out.append(line)
    if not replaced:
        raise ValueError(f"no version field in {path}")
    path.write_text("".join(out), encoding="utf-8")
    return version


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


def md5s_current(remote, sources):
    for key, _list_url, _default in PRODUCTS:
        item = remote.get(key) or {}
        recorded = sources.get(key) or {}
        remote_md5 = (item.get("md5") or "").lower()
        if not remote_md5:
            return False
        if (recorded.get("md5") or "").lower() != remote_md5:
            return False
    return True


def skip_all_downloads(paths, remote, sources):
    if not paths["sqlite"].is_file():
        return False
    if not _load_zip_present(paths["load"]):
        return False
    return md5s_current(remote, sources)


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


def _download_and_verify(remote, zip_path, progress=False):
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


def ensure_product(
    paths, key, remote, progress=False, log=None, force=False, recorded_md5=None
):
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
    recorded = (recorded_md5 or "").lower()
    remote_md5 = remote["md5"].lower()
    downloaded = False
    if not zip_path.is_file():
        _download_and_verify(remote, zip_path, progress=progress)
        downloaded = True
    elif recorded == remote_md5:
        if log is not None:
            log.write(f"already present, md5 match: {zip_path.name}\n")
    elif recorded:
        _download_and_verify(remote, zip_path, progress=progress)
        downloaded = True
    elif file_md5(zip_path, progress=progress) == remote_md5:
        if log is not None:
            log.write(f"already present, md5 match: {zip_path.name}\n")
    else:
        _download_and_verify(remote, zip_path, progress=progress)
        downloaded = True
    gpkg = gpkg_beside(zip_path)
    if downloaded or gpkg is None or not Path(gpkg).is_file():
        unzip_gpkg(zip_path, paths["extract"], progress=progress)
        gpkg = gpkg_beside(zip_path)
    if gpkg is None:
        raise FileNotFoundError(f"no GeoPackage extracted from {zip_path}")
    return zip_path, Path(gpkg)


def fetch_extract(paths, progress=False, log=None, force=False, remote=None):
    ensure_dirs(paths)
    if remote is None:
        remote = list_all_products()
    sources = load_sources(paths["sources"])
    gpkgs = {}
    for key, item in remote.items():
        recorded = (sources.get(key) or {}).get("md5")
        zip_path, gpkg = ensure_product(
            paths,
            key,
            item,
            progress=progress,
            log=log,
            force=force,
            recorded_md5=recorded,
        )
        gpkgs[key] = {"zip": zip_path, "gpkg": gpkg, "remote": item}
    return remote, gpkgs
