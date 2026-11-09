"""Locate the bundled lookup zip and materialise sqlite in a local cache."""

import importlib.metadata
import os
import sys
import tomllib
from importlib.resources import as_file, files
from pathlib import Path

from openpostcode.paths import OUTPUT_ZIP_NAME
from openpostcode.tables import import_zip

CACHE_ENV = "OPENPOSTCODEUK_CACHE"
SKIP_IMPORT_ENV = "OPENPOSTCODEUK_SKIP_IMPORT"


def _declared_version():
    try:
        return importlib.metadata.version("openpostcodeuk")
    except importlib.metadata.PackageNotFoundError:
        pass
    version = _pyproject_version()
    if version:
        return version
    return "unknown"


def _pyproject_version(start=None):
    path = (Path.cwd() if start is None else Path(start)) / "pyproject.toml"
    if not path.is_file():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


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


def _cache_dir():
    override = os.environ.get(CACHE_ENV, "").strip()
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg) / "openpostcodeuk"
    return Path.home() / ".cache" / "openpostcodeuk"


def _cache_path(key):
    root = _cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{key}.sqlite"


def _sqlite_from_zip(zip_path, key, log=None):
    dest = _cache_path(key)
    if _usable_file(dest):
        return dest
    if log is not None:
        log.write("Importing lookup database from CSV zip (once per version)...\n")
        log.flush()
    tmp = dest.with_name(dest.name + ".partial")
    import_zip(zip_path, tmp)
    tmp.replace(dest)
    if log is not None:
        log.write("Lookup database ready.\n")
        log.flush()
    return dest


def should_import_during_build():
    value = os.environ.get(SKIP_IMPORT_ENV, "").strip().lower()
    return value not in {"1", "true", "yes"}


def run_build_import(build_lib, log=None, editable=False):
    if editable:
        return None
    if not should_import_during_build():
        if log is not None:
            log.write("skipping lookup import (OPENPOSTCODEUK_SKIP_IMPORT)\n")
        return None
    zip_path = Path(build_lib) / "openpostcodeuk" / "data" / OUTPUT_ZIP_NAME
    if not _usable_file(zip_path):
        return None
    return _sqlite_from_zip(zip_path, _declared_version(), log=log)


def ensure_sqlite(log=None):
    if log is None:
        log = sys.stderr
    ref = _package_zip()
    if ref is not None:
        with as_file(ref) as zip_path:
            return _sqlite_from_zip(Path(zip_path), _declared_version(), log=log)
    repo = _repo_zip()
    if repo is not None:
        key = f"{repo.stat().st_mtime_ns}-{repo.stat().st_size}"
        return _sqlite_from_zip(repo, key, log=log)
    raise FileNotFoundError("openpostcode_uk.zip not found")
