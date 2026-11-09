"""Orchestrate fetch, transform, and load."""

import sqlite3
import sys

from tqdm import tqdm

from openpostcode import UNIQUE_NAME_CAP, supply
from openpostcode.extract import read_postcodes
from openpostcode.gitindex import sync_load_zip
from openpostcode.match import assign_tiles, match_tile
from openpostcode.paths import OUTPUT_ZIP_NAME, ensure_dirs
from openpostcode.store import LOAD_ZIP_URL, connect, export_zip, import_zip, write_rows
from openpostcode.supply import (
    load_sources,
    md5s_current,
    save_sources,
    skip_all_downloads,
)


def transform_all(names_gpkg, roads_gpkg, progress=False, writer=None):
    postcodes = read_postcodes(names_gpkg, progress=progress)
    tiled = assign_tiles(postcodes)
    groups = list(tiled.groupby(["tile_x", "tile_y"], sort=True))
    if progress:
        tqdm.write(
            f"{len(postcodes)} postcodes in {len(groups)} tiles",
            file=sys.stderr,
        )
    collected = []
    with tqdm(
        total=len(groups),
        desc="tiles",
        file=sys.stderr,
        disable=not progress,
        dynamic_ncols=True,
    ) as tile_bar:
        for (_tx, _ty), group in groups:
            tile_id = f"{int(_tx)}_{int(_ty)}"
            inner = tqdm(
                total=len(group),
                desc=f"postcodes {tile_id}",
                file=sys.stderr,
                disable=not progress,
                leave=False,
                dynamic_ncols=True,
                mininterval=0.3,
            )

            def on_postcode():
                inner.update(1)

            def on_status(text):
                inner.set_postfix_str(text, refresh=True)
                tile_bar.set_postfix_str(f"{tile_id} {text}", refresh=True)

            rows = match_tile(
                group,
                roads_gpkg,
                names_gpkg,
                cap=UNIQUE_NAME_CAP,
                progress_cb=on_postcode,
                status_cb=on_status if progress else None,
            )
            named_hits = 0
            landmark_hits = 0
            for postcode_row, ranked in rows:
                named_hits += sum(
                    1
                    for item in ranked
                    if item["kind"] == "road" and not item["unnamed"]
                )
                landmark_hits += sum(1 for item in ranked if item["kind"] == "landmark")
                if writer is None:
                    collected.append((postcode_row, ranked))
            if writer is not None:
                writer(rows)
            inner.set_postfix_str(
                f"roads={named_hits} landmarks={landmark_hits}",
                refresh=False,
            )
            inner.close()
            tile_bar.set_postfix_str(
                f"{tile_id} roads={named_hits} landmarks={landmark_hits}",
                refresh=True,
            )
            tile_bar.update(1)
    return collected


def write_catalog(paths, remote, output_zip):
    payload = load_sources(paths["sources"])
    for key, item in remote.items():
        payload[key] = {
            "list_url": item["list_url"],
            "fileName": item["fileName"],
            "md5": item["md5"],
            "size": item.get("size"),
        }
    payload["output_zip"] = output_zip
    save_sources(paths["sources"], payload)


def _rematch_and_write(paths, gpkgs, remote, progress=False):
    names_gpkg = gpkgs["open_names"]["gpkg"]
    roads_gpkg = gpkgs["open_roads"]["gpkg"]
    conn = connect(paths["sqlite"])
    keys = {}
    next_id = 1

    def writer(rows):
        nonlocal keys, next_id
        keys, next_id = write_rows(
            conn, rows, progress=False, keys=keys, next_id=next_id
        )

    try:
        transform_all(names_gpkg, roads_gpkg, progress=progress, writer=writer)
        zip_path = paths["load"] / OUTPUT_ZIP_NAME
        export_zip(conn, zip_path, progress=progress)
    finally:
        conn.close()
    write_catalog(paths, remote, OUTPUT_ZIP_NAME)
    sync_load_zip(paths["root"], OUTPUT_ZIP_NAME)


def _write_zip_from_sqlite(paths, remote, progress=False):
    zip_path = paths["load"] / OUTPUT_ZIP_NAME
    conn = sqlite3.connect(paths["sqlite"])
    try:
        export_zip(conn, zip_path, progress=progress)
    finally:
        conn.close()
    write_catalog(paths, remote, OUTPUT_ZIP_NAME)
    sync_load_zip(paths["root"], OUTPUT_ZIP_NAME)


def run_export(paths, progress=False, log=None, force=False):
    ensure_dirs(paths)
    remote = supply.list_all_products()
    sources = load_sources(paths["sources"])
    zip_path = paths["load"] / OUTPUT_ZIP_NAME
    sqlite_ok = paths["sqlite"].is_file()
    zip_ok = zip_path.is_file()
    if force:
        _remote, gpkgs = supply.fetch_extract(
            paths, progress=progress, log=log, force=True, remote=remote
        )
        _rematch_and_write(paths, gpkgs, remote, progress=progress)
        return 0
    if skip_all_downloads(paths, remote, sources):
        if log is not None:
            log.write("already present, md5 match: load and sqlite current\n")
        return 0
    catalog_ok = md5s_current(remote, sources)
    if catalog_ok and not sqlite_ok and zip_ok:
        if log is not None:
            log.write("rebuild sqlite from load zip\n")
        import_zip(zip_path, paths["sqlite"], progress=progress)
        write_catalog(paths, remote, OUTPUT_ZIP_NAME)
        return 0
    if catalog_ok and sqlite_ok and not zip_ok:
        if log is not None:
            log.write("write load zip from sqlite\n")
        _write_zip_from_sqlite(paths, remote, progress=progress)
        return 0
    _remote, gpkgs = supply.fetch_extract(
        paths, progress=progress, log=log, force=False, remote=remote
    )
    _rematch_and_write(paths, gpkgs, remote, progress=progress)
    return 0


def run_import(paths, progress=False):
    ensure_dirs(paths)
    zip_path = paths["load"] / OUTPUT_ZIP_NAME
    supply.download_zip(LOAD_ZIP_URL, zip_path, progress=progress)
    import_zip(zip_path, paths["sqlite"], progress=progress)
    return 0
