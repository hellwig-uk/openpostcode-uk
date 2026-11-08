"""Read postcodes, landmarks, and road links from GeoPackages."""

import sqlite3
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from tqdm import tqdm

from opennames import BNG_EPSG, LANDMARK_EXCLUDED_TYPES
from opennames.names import place_label, road_label, text_or_none

_LAYER_CACHE = {}
POSTCODE_WHERE = "local_type = 'Postcode'"
POSTCODE_CHUNK = 100_000


def _layer_fields(path, layer):
    info = pyogrio.read_info(path, layer=layer)
    fields = info.get("fields")
    if fields is None:
        fields = info.get("dtypes", {})
    if isinstance(fields, dict):
        return {str(name).lower() for name in fields}
    return {str(name).lower() for name in fields}


def _layer_names(path):
    listed = pyogrio.list_layers(path)
    names = []
    for row in listed:
        if isinstance(row, str):
            names.append(row)
        else:
            names.append(str(row[0]))
    return names


def find_layer(path, required):
    required = {name.lower() for name in required}
    for layer in _layer_names(path):
        fields = _layer_fields(path, layer)
        if required <= fields:
            return layer
    raise ValueError(f"no layer in {path} with columns {sorted(required)}")


def names_layer(path):
    key = (str(Path(path)), "names")
    if key not in _LAYER_CACHE:
        _LAYER_CACHE[key] = find_layer(path, {"local_type", "name1"})
    return _LAYER_CACHE[key]


def roads_layer(path):
    key = (str(Path(path)), "roads")
    if key not in _LAYER_CACHE:
        found = None
        for layer in _layer_names(path):
            compact = str(layer).lower().replace(" ", "")
            if compact in {"roadlink", "road_link"}:
                found = layer
                break
        if found is None:
            found = find_layer(path, {"name_1", "road_classification"})
        _LAYER_CACHE[key] = found
    return _LAYER_CACHE[key]


def _read_gpkg(path, layer, bbox=None, where=None, skip_features=0, max_features=None):
    kwargs = {"layer": layer, "bbox": bbox, "engine": "pyogrio"}
    if where is not None:
        kwargs["where"] = where
    if skip_features:
        kwargs["skip_features"] = skip_features
    if max_features is not None:
        kwargs["max_features"] = max_features
    frame = gpd.read_file(path, **kwargs)
    if frame.crs is None or frame.crs.to_epsg() != BNG_EPSG:
        raise ValueError(f"{path} layer {layer} is not EPSG:{BNG_EPSG}")
    frame.columns = [str(col) for col in frame.columns]
    lower = {col.lower(): col for col in frame.columns}
    rename = {actual: key for key, actual in lower.items() if actual != key}
    if rename:
        frame = frame.rename(columns=rename)
    return frame


def _count_rows(path, layer, where=None):
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        sql = f'SELECT COUNT(*) FROM "{layer}"'
        if where:
            sql = f"{sql} WHERE {where}"
        return int(conn.execute(sql).fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _prepare_postcodes(frame):
    if frame.empty:
        return frame.reset_index(drop=True)
    ident = _id_column(frame)
    frame = frame.copy()
    frame["postcode"] = frame[ident].map(
        lambda value: "".join(str(value).split()).upper()
    )
    for column in (
        "district_borough",
        "county_unitary",
        "country",
        "populated_place",
    ):
        if column not in frame.columns:
            frame[column] = None
    return frame.reset_index(drop=True)


def _id_column(frame):
    for key in ("id", "fid"):
        if key in frame.columns:
            return key
    raise ValueError("no id column")


def _object_col(frame, column):
    if column not in frame.columns:
        return np.full(len(frame), None, dtype=object)
    return frame[column].to_numpy(dtype=object)


def read_postcodes(path, bbox=None, progress=False, chunk_size=POSTCODE_CHUNK):
    layer = names_layer(path)
    size = Path(path).stat().st_size if Path(path).is_file() else 0
    if progress:
        tqdm.write(
            f"Open Names {Path(path).name} ({size / 1_000_000:.0f} MB), "
            f"layer {layer}",
            file=sys.stderr,
        )
        tqdm.write("Counting postcode rows…", file=sys.stderr)
    total = None if bbox is not None else _count_rows(path, layer, POSTCODE_WHERE)
    if progress and total is not None:
        tqdm.write(f"{total:,} postcode rows to read", file=sys.stderr)
    chunks = []
    skip = 0
    step = chunk_size if chunk_size and chunk_size > 0 else POSTCODE_CHUNK
    with tqdm(
        total=total,
        desc="read postcodes",
        unit="row",
        file=sys.stderr,
        disable=not progress,
        dynamic_ncols=True,
    ) as bar:
        while True:
            part = _read_gpkg(
                path,
                layer,
                bbox=bbox,
                where=POSTCODE_WHERE,
                skip_features=skip,
                max_features=step,
            )
            if part.empty:
                break
            chunks.append(part)
            skip += len(part)
            bar.update(len(part))
            if total is not None and skip >= total:
                break
            if len(part) < step:
                break
    if not chunks:
        frame = gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{BNG_EPSG}")
    else:
        frame = gpd.GeoDataFrame(
            pd.concat(chunks, ignore_index=True), crs=chunks[0].crs
        )
    return _prepare_postcodes(frame)


def read_landmarks(path, bbox=None):
    layer = names_layer(path)
    frame = _read_gpkg(path, layer, bbox=bbox)
    frame = frame[~frame["local_type"].isin(LANDMARK_EXCLUDED_TYPES)].copy()
    for column in ("district_borough", "county_unitary", "country", "name2"):
        if column not in frame.columns:
            frame[column] = None
    n1 = _object_col(frame, "name1")
    n2 = _object_col(frame, "name2")
    frame["name"] = [place_label(a, b) for a, b in zip(n1, n2)]
    return frame.reset_index(drop=True)


def read_roads(path, bbox=None):
    layer = roads_layer(path)
    frame = _read_gpkg(path, layer, bbox=bbox)
    names = []
    flags = []
    for name_1, name_2, number in zip(
        _object_col(frame, "name_1"),
        _object_col(frame, "name_2"),
        _object_col(frame, "road_classification_number"),
    ):
        name, flag = road_label(name_1, name_2, number)
        names.append(name)
        flags.append(flag)
    frame["name"] = names
    frame["unnamed"] = flags
    frame["classification"] = [
        text_or_none(value) for value in _object_col(frame, "road_classification")
    ]
    return frame.reset_index(drop=True)
