"""ETL directory layout."""

from pathlib import Path

OUTPUT_ZIP_NAME = "openpostcode_uk.zip"


def etl_paths(etl_dir):
    root = Path(etl_dir)
    return {
        "root": root,
        "extract": root / "extract",
        "transform": root / "transform",
        "load": root / "load",
        "sqlite": root / "transform" / "lookup.sqlite",
        "sources": root / "sources.json",
    }


def ensure_dirs(paths):
    paths["extract"].mkdir(parents=True, exist_ok=True)
    paths["transform"].mkdir(parents=True, exist_ok=True)
    paths["load"].mkdir(parents=True, exist_ok=True)
