"""Locate the bundled load zip and materialise lookup.sqlite."""

import importlib.metadata
import tempfile
from importlib.resources import as_file, files
from pathlib import Path

from openpostcode.paths import OUTPUT_ZIP_NAME
from openpostcode.tables import import_zip


def _distribution_version():
    try:
        return importlib.metadata.version("openpostcodeuk")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


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
    if path.is_file() and path.stat().st_size > 0:
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


def ensure_sqlite():
    ref = _package_zip()
    if ref is not None:
        with as_file(ref) as zip_path:
            return _sqlite_from_zip(Path(zip_path), _distribution_version())
    repo = _repo_zip()
    if repo is not None:
        key = f"{repo.stat().st_mtime_ns}-{repo.stat().st_size}"
        return _sqlite_from_zip(repo, key)
    raise FileNotFoundError("openpostcode_uk.zip not found")
