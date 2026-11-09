"""Nearest unique roads and closer landmarks for postcode points."""

import numpy as np
import pandas as pd
from shapely import STRtree
from shapely import distance as shp_distance
from shapely.geometry.base import BaseGeometry

from openpostcode import TILE_METRES, UNIQUE_NAME_CAP
from openpostcode.extract import read_landmarks, read_roads
from openpostcode.names import text_or_none

INITIAL_EXPAND_METRES = 10_000.0
MAX_EXPAND_METRES = 2_000_000.0
QUERY_START_METRES = 250.0


def _object_col(frame, column):
    if column not in frame.columns:
        return np.full(len(frame), None, dtype=object)
    return frame[column].to_numpy(dtype=object)


def _road_index(roads):
    geoms = np.asarray(roads.geometry.values, dtype=object)
    return {
        "n": len(geoms),
        "geoms": geoms,
        "tree": STRtree(geoms),
        "names": _object_col(roads, "name"),
        "unnamed": np.asarray(roads["unnamed"], dtype=int),
        "classification": _object_col(roads, "classification"),
    }


def _landmark_index(landmarks):
    geoms = np.asarray(landmarks.geometry.values, dtype=object)
    return {
        "n": len(geoms),
        "geoms": geoms,
        "tree": STRtree(geoms),
        "names": _object_col(landmarks, "name"),
        "local_type": _object_col(landmarks, "local_type"),
        "district_borough": _object_col(landmarks, "district_borough"),
        "county_unitary": _object_col(landmarks, "county_unitary"),
        "country": _object_col(landmarks, "country"),
    }


def _ensure_road_index(roads):
    if roads is None:
        return None
    if isinstance(roads, dict):
        if not roads.get("n"):
            return None
        return roads
    if getattr(roads, "empty", True):
        return None
    return _road_index(roads)


def _ensure_landmark_index(landmarks):
    if landmarks is None:
        return None
    if isinstance(landmarks, dict):
        if not landmarks.get("n"):
            return None
        return landmarks
    if getattr(landmarks, "empty", True):
        return None
    return _landmark_index(landmarks)


def _query_dwithin(tree, n_tree, points, distance):
    empty = np.array([], dtype=int)
    if n_tree == 0:
        return empty, empty
    if isinstance(points, BaseGeometry):
        raw = np.asarray(tree.query(points, predicate="dwithin", distance=distance))
        if raw.size == 0:
            return empty, empty
        return np.zeros(raw.shape[0], dtype=int), raw.astype(int, copy=False)
    if len(points) == 0:
        return empty, empty
    raw = np.asarray(tree.query(points, predicate="dwithin", distance=distance))
    if raw.size == 0:
        return empty, empty
    return raw[0].astype(int, copy=False), raw[1].astype(int, copy=False)


def unique_roads_for_points(points, roads, cap=UNIQUE_NAME_CAP):
    points = np.asarray(points, dtype=object)
    n_pts = len(points)
    results = [[] for _ in range(n_pts)]
    index = _ensure_road_index(roads)
    if index is None:
        return results
    pending = np.arange(n_pts, dtype=int)
    radius = QUERY_START_METRES
    while pending.size:
        inp, tree_idx = _query_dwithin(
            index["tree"], index["n"], points[pending], radius
        )
        bucket = {int(i): [] for i in pending}
        if inp.size:
            orig = pending[inp]
            dist = np.asarray(
                shp_distance(points[orig], index["geoms"][tree_idx]),
                dtype=float,
            )
            frame = pd.DataFrame(
                {
                    "pi": orig,
                    "name": index["names"][tree_idx],
                    "unnamed": index["unnamed"][tree_idx],
                    "classification": index["classification"][tree_idx],
                    "distance_m": dist,
                }
            )
            frame = frame.sort_values(["pi", "distance_m", "name"], kind="mergesort")
            frame = frame.drop_duplicates(["pi", "name"], keep="first")
            frame["rk"] = frame.groupby("pi", sort=False).cumcount()
            frame = frame[frame["rk"] < cap]
            for rec in frame.to_dict("records"):
                bucket[int(rec["pi"])].append(
                    {
                        "kind": "road",
                        "name": rec["name"],
                        "unnamed": int(rec["unnamed"]),
                        "classification": text_or_none(rec["classification"]),
                        "local_type": None,
                        "distance_m": float(rec["distance_m"]),
                    }
                )
        still = []
        for i in pending:
            recs = bucket[int(i)]
            results[int(i)] = recs
            if len(recs) < cap:
                still.append(int(i))
        if not still or radius >= MAX_EXPAND_METRES:
            break
        pending = np.asarray(still, dtype=int)
        radius = min(radius * 2, MAX_EXPAND_METRES)
    return results


def unique_roads_for_point(point, roads, cap=UNIQUE_NAME_CAP):
    return unique_roads_for_points(np.array([point], dtype=object), roads, cap=cap)[0]


def _landmarks_for_points(points, landmarks, thresholds, cap=UNIQUE_NAME_CAP):
    points = np.asarray(points, dtype=object)
    n_pts = len(points)
    results = [[] for _ in range(n_pts)]
    index = _ensure_landmark_index(landmarks)
    if index is None or n_pts == 0:
        return results
    thresholds = np.asarray(thresholds, dtype=float)
    unbound = []
    finite = []
    finite_thr = []
    for i, thr in enumerate(thresholds):
        if np.isnan(thr):
            unbound.append(i)
        elif thr > 0:
            finite.append(i)
            finite_thr.append(thr)
    if finite:
        pts = points[np.asarray(finite, dtype=int)]
        dist_arr = np.asarray(finite_thr, dtype=float)
        inp, tree_idx = _query_dwithin(index["tree"], index["n"], pts, dist_arr)
        if inp.size:
            orig = np.asarray(finite, dtype=int)[inp]
            dist = np.asarray(
                shp_distance(points[orig], index["geoms"][tree_idx]),
                dtype=float,
            )
            thr = np.asarray(finite_thr, dtype=float)[inp]
            keep = dist < thr
            orig = orig[keep]
            tree_idx = tree_idx[keep]
            dist = dist[keep]
            frame = pd.DataFrame(
                {
                    "pi": orig,
                    "ti": tree_idx,
                    "distance_m": dist,
                }
            )
            frame = frame.sort_values(["pi", "distance_m"], kind="mergesort")
            for rec in frame.to_dict("records"):
                i = int(rec["ti"])
                results[int(rec["pi"])].append(
                    {
                        "kind": "landmark",
                        "name": index["names"][i],
                        "unnamed": 0,
                        "classification": None,
                        "local_type": text_or_none(index["local_type"][i]),
                        "district_borough": text_or_none(index["district_borough"][i]),
                        "county_unitary": text_or_none(index["county_unitary"][i]),
                        "country": text_or_none(index["country"][i]),
                        "distance_m": float(rec["distance_m"]),
                    }
                )
    if unbound:
        pending = np.asarray(unbound, dtype=int)
        radius = QUERY_START_METRES
        while pending.size:
            inp, tree_idx = _query_dwithin(
                index["tree"], index["n"], points[pending], radius
            )
            bucket = {int(i): [] for i in pending}
            if inp.size:
                orig = pending[inp]
                dist = np.asarray(
                    shp_distance(points[orig], index["geoms"][tree_idx]),
                    dtype=float,
                )
                frame = pd.DataFrame(
                    {
                        "pi": orig,
                        "ti": tree_idx,
                        "name": index["names"][tree_idx],
                        "distance_m": dist,
                    }
                )
                frame = frame.sort_values(
                    ["pi", "distance_m", "name"], kind="mergesort"
                )
                frame = frame.drop_duplicates(["pi", "name"], keep="first")
                frame["rk"] = frame.groupby("pi", sort=False).cumcount()
                frame = frame[frame["rk"] < cap]
                for rec in frame.to_dict("records"):
                    i = int(rec["ti"])
                    bucket[int(rec["pi"])].append(
                        {
                            "kind": "landmark",
                            "name": rec["name"],
                            "unnamed": 0,
                            "classification": None,
                            "local_type": text_or_none(index["local_type"][i]),
                            "district_borough": text_or_none(
                                index["district_borough"][i]
                            ),
                            "county_unitary": text_or_none(index["county_unitary"][i]),
                            "country": text_or_none(index["country"][i]),
                            "distance_m": float(rec["distance_m"]),
                        }
                    )
            still = []
            for i in pending:
                recs = bucket[int(i)]
                results[int(i)] = recs
                if len(recs) < cap:
                    still.append(int(i))
            if still and radius < MAX_EXPAND_METRES:
                pending = np.asarray(still, dtype=int)
                radius = min(radius * 2, MAX_EXPAND_METRES)
            else:
                pending = np.array([], dtype=int)
    return results


def _landmarks_for_point(point, landmarks, threshold, cap=UNIQUE_NAME_CAP):
    if threshold is None:
        thr = np.nan
    else:
        thr = float(threshold)
    return _landmarks_for_points(
        np.array([point], dtype=object),
        landmarks,
        np.array([thr], dtype=float),
        cap=cap,
    )[0]


def merge_ranked(roads, landmarks):
    named = [row for row in roads if not row["unnamed"]]
    if named:
        threshold = min(row["distance_m"] for row in named)
        extra = landmarks
    elif roads:
        threshold = min(row["distance_m"] for row in roads)
        extra = landmarks
    else:
        extra = landmarks
        threshold = None
    if threshold is not None:
        extra = [row for row in extra if row["distance_m"] < threshold]
    mixed = list(extra) + list(roads)
    mixed.sort(key=lambda item: (item["distance_m"], item["kind"], item["name"]))
    return mixed, threshold


def attach_landmarks_bulk(points, road_hits_list, landmarks, cap=UNIQUE_NAME_CAP):
    n_pts = len(points)
    thresholds = np.empty(n_pts, dtype=float)
    for i, hits in enumerate(road_hits_list):
        named = [row for row in hits if not row["unnamed"]]
        src = named if named else hits
        if not src:
            thresholds[i] = np.nan
        else:
            thresholds[i] = min(row["distance_m"] for row in src)
    landmark_hits = _landmarks_for_points(points, landmarks, thresholds, cap=cap)
    return [merge_ranked(road_hits_list[i], landmark_hits[i])[0] for i in range(n_pts)]


def attach_landmarks(point, road_hits, landmarks, cap=UNIQUE_NAME_CAP):
    return attach_landmarks_bulk(
        np.array([point], dtype=object),
        [road_hits],
        landmarks,
        cap=cap,
    )[0]


def features_for_point(point, roads, landmarks, cap=UNIQUE_NAME_CAP):
    road_hits = unique_roads_for_point(point, roads, cap=cap)
    return attach_landmarks(point, road_hits, landmarks, cap=cap)


def tile_bounds(tile_x, tile_y, expand):
    return (
        tile_x - expand,
        tile_y - expand,
        tile_x + TILE_METRES + expand,
        tile_y + TILE_METRES + expand,
    )


def assign_tiles(postcodes, tile_metres=TILE_METRES):
    xs = postcodes.geometry.x.to_numpy()
    ys = postcodes.geometry.y.to_numpy()
    out = postcodes.copy()
    out["tile_x"] = np.floor(xs / tile_metres) * tile_metres
    out["tile_y"] = np.floor(ys / tile_metres) * tile_metres
    return out


def match_tile(
    group,
    roads_path,
    names_path,
    cap=UNIQUE_NAME_CAP,
    progress_cb=None,
    status_cb=None,
):
    expand = INITIAL_EXPAND_METRES
    tile_x = float(group["tile_x"].iloc[0])
    tile_y = float(group["tile_y"].iloc[0])
    points = np.asarray(group.geometry.values, dtype=object)
    if status_cb is not None:
        status_cb(f"reading roads +{expand:.0f}m")
    roads = read_roads(roads_path, bbox=tile_bounds(tile_x, tile_y, expand))
    index = _ensure_road_index(roads)
    hits = unique_roads_for_points(points, index, cap=cap)
    incomplete = [i for i, recs in enumerate(hits) if len(recs) < cap]
    while incomplete and expand < MAX_EXPAND_METRES:
        expand = min(expand * 2, MAX_EXPAND_METRES)
        if status_cb is not None:
            status_cb(f"expand +{expand:.0f}m ({len(incomplete)} postcodes)")
        sub = group.iloc[incomplete]
        xs = sub.geometry.x.to_numpy()
        ys = sub.geometry.y.to_numpy()
        bbox = (
            float(xs.min()) - expand,
            float(ys.min()) - expand,
            float(xs.max()) + expand,
            float(ys.max()) + expand,
        )
        roads = read_roads(roads_path, bbox=bbox)
        index = _ensure_road_index(roads)
        refreshed = unique_roads_for_points(
            points[np.asarray(incomplete)], index, cap=cap
        )
        still = []
        for local, global_i in enumerate(incomplete):
            hits[global_i] = refreshed[local]
            if len(hits[global_i]) < cap and expand < MAX_EXPAND_METRES:
                still.append(global_i)
        incomplete = still
    if status_cb is not None:
        status_cb(f"reading landmarks +{expand:.0f}m")
    landmarks = read_landmarks(names_path, bbox=tile_bounds(tile_x, tile_y, expand))
    ranked = attach_landmarks_bulk(points, hits, landmarks, cap=cap)
    results = []
    for offset, (_pos, row) in enumerate(group.iterrows()):
        results.append((row, ranked[offset]))
        if progress_cb is not None:
            progress_cb()
    return results
