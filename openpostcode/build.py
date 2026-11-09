"""Orchestrate fetch, transform, and load."""

import sys

from tqdm import tqdm

from openpostcode import UNIQUE_NAME_CAP
from openpostcode.extract import read_postcodes
from openpostcode.gitindex import sync_load_zip
from openpostcode.match import assign_tiles, match_tile
from openpostcode.paths import OUTPUT_ZIP_NAME, ensure_dirs
from openpostcode.store import LOAD_ZIP_URL, connect, export_zip, import_zip, write_rows
from openpostcode.supply import download_zip, fetch_extract, load_sources, save_sources


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


def run_build(paths, progress=False, log=None, force=False):
    ensure_dirs(paths)
    remote, gpkgs = fetch_extract(paths, progress=progress, log=log, force=force)
    if gpkgs is False:
        return 0
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
    return 0


def run_import(paths, progress=False):
    ensure_dirs(paths)
    zip_path = paths["load"] / OUTPUT_ZIP_NAME
    download_zip(LOAD_ZIP_URL, zip_path, progress=progress)
    import_zip(zip_path, paths["sqlite"], progress=progress)
    return 0
