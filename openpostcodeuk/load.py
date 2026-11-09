"""Locate the bundled lookup database and materialise sqlite."""

import importlib.metadata
import os
import tempfile
from importlib.resources import as_file, files
from pathlib import Path

from openpostcode.paths import OUTPUT_ZIP_NAME
from openpostcode.tables import import_zip

SKIP_IMPORT_ENV = "OPENPOSTCODEUK_SKIP_IMPORT"
SQLITE_NAME = "lookup.sqlite"


def _distribution_version():
    try:
        return importlib.metadata.version("openpostcodeuk")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _usable_file(path):
    path = Path(path)
    return path.is_file() and path.stat().st_size > 0


def _package_zip():
    ref = files("openpostcodeuk").joinpath("data", OUTPUT_ZIP_NAME)
    try:
        if ref.is_file() and ref.stat().st_size > 0:
            return ref
    except FileNotFoundError, OSError:
        pass
    return None


def _repo_root_dir():
    return Path(__file__).resolve().parents[1]


def _repo_zip():
    path = _repo_root_dir() / "etl" / "load" / OUTPUT_ZIP_NAME
    if _usable_file(path):
        return path
    return None


def _installed_sqlite():
    path = Path(__file__).resolve().parent / "data" / SQLITE_NAME
    if _usable_file(path):
        return path
    return None


def _cache_path(key):
    root = Path(tempfile.gettempdir()) / "openpostcodeuk"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{key}.sqlite"


def _sqlite_from_zip(zip_path, key):
    dest = _cache_path(key)
    if dest.is_file():
        return dest
    import_zip(zip_path, dest)
    return dest


def should_import_during_build():
    value = os.environ.get(SKIP_IMPORT_ENV, "").strip().lower()
    return value not in {"1", "true", "yes"}


def import_into_data_dir(data_dir, log=None):
    data_dir = Path(data_dir)
    sqlite_path = data_dir / SQLITE_NAME
    zip_path = data_dir / OUTPUT_ZIP_NAME
    if _usable_file(sqlite_path):
        if log is not None:
            log.write("lookup.sqlite already present\n")
        return sqlite_path
    if not _usable_file(zip_path):
        return None
    if log is not None:
        log.write("Importing lookup database (one-time install step)...\n")
    import_zip(zip_path, sqlite_path)
    if log is not None:
        log.write("Lookup database ready.\n")
    return sqlite_path


def run_build_import(build_lib, log=None, editable=False):
    if editable:
        return None
    if not should_import_during_build():
        if log is not None:
            log.write("skipping lookup import (OPENPOSTCODEUK_SKIP_IMPORT)\n")
        return None
    data_dir = Path(build_lib) / "openpostcodeuk" / "data"
    return import_into_data_dir(data_dir, log=log)


def ensure_sqlite():
    installed = _installed_sqlite()
    if installed is not None:
        return installed
    ref = _package_zip()
    if ref is not None:
        with as_file(ref) as zip_path:
            return _sqlite_from_zip(Path(zip_path), _distribution_version())
    repo = _repo_zip()
    if repo is not None:
        key = f"{repo.stat().st_mtime_ns}-{repo.stat().st_size}"
        return _sqlite_from_zip(repo, key)
    raise FileNotFoundError("openpostcode_uk.zip not found")
