"""Shared GeoPackage fixtures for tests."""

from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
from shapely.geometry import LineString, Point


def write_names_gpkg(path, records):
    frame = gpd.GeoDataFrame(records, crs="EPSG:27700")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, layer="namedplace", driver="GPKG")
    return path


def write_roads_gpkg(path, records, layer="road_link"):
    frame = gpd.GeoDataFrame(records, crs="EPSG:27700")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, layer=layer, driver="GPKG")
    return path


def sample_names():
    return [
        {
            "id": "SW1A1AA",
            "name1": "SW1A 1AA",
            "name2": None,
            "local_type": "Postcode",
            "district_borough": "City of Westminster",
            "county_unitary": "Greater London",
            "country": "England",
            "populated_place": "Nuneaton",
            "geometry": Point(100, 100),
        },
        {
            "id": "SW1A1AB",
            "name1": "SW1A 1AB",
            "name2": None,
            "local_type": "Postcode",
            "district_borough": "City of Westminster",
            "county_unitary": "Greater London",
            "country": "England",
            "populated_place": "Nuneaton",
            "geometry": Point(102, 100),
        },
        {
            "id": "EMPTY1",
            "name1": "EMPTY1",
            "name2": None,
            "local_type": "Postcode",
            "district_borough": None,
            "county_unitary": None,
            "country": None,
            "geometry": Point(9000, 9000),
        },
        {
            "id": "palace",
            "name1": "Palas",
            "name2": "The Palace",
            "local_type": "Other Landform",
            "district_borough": "City of Westminster",
            "county_unitary": "Greater London",
            "country": "England",
            "geometry": Point(101, 100),
        },
        {
            "id": "onmall",
            "name1": "On Mall",
            "name2": None,
            "local_type": "Other Landform",
            "district_borough": None,
            "county_unitary": None,
            "country": None,
            "geometry": Point(100, 110),
        },
        {
            "id": "farhill",
            "name1": "Far Hill",
            "name2": None,
            "local_type": "Hill Or Mountain",
            "district_borough": None,
            "county_unitary": None,
            "country": "Wales",
            "geometry": Point(500, 100),
        },
        {
            "id": "nuneaton",
            "name1": "Nuneaton",
            "name2": None,
            "local_type": "Town",
            "district_borough": "Nuneaton and Bedworth",
            "county_unitary": "Warwickshire",
            "country": "England",
            "geometry": Point(400, 100),
        },
        {
            "id": "namedrd",
            "name1": "Ignore Street",
            "name2": None,
            "local_type": "Named Road",
            "district_borough": None,
            "county_unitary": None,
            "country": None,
            "geometry": Point(100, 100),
        },
    ]


def sample_roads():
    return [
        {
            "name_1": "Heol A",
            "name_2": "Mall Road",
            "road_classification": "A Road",
            "road_classification_number": "A1",
            "geometry": LineString([(100, 110), (120, 110)]),
        },
        {
            "name_1": "Heol A",
            "name_2": "Mall Road",
            "road_classification": "A Road",
            "road_classification_number": "A1",
            "geometry": LineString([(100, 105), (120, 105)]),
        },
        {
            "name_1": "Side Street",
            "name_2": None,
            "road_classification": "Local Road",
            "road_classification_number": None,
            "geometry": LineString([(130, 100), (150, 100)]),
        },
        {
            "name_1": None,
            "name_2": None,
            "road_classification": "A Road",
            "road_classification_number": "A302",
            "geometry": LineString([(100, 80), (140, 80)]),
        },
        {
            "name_1": None,
            "name_2": None,
            "road_classification": "Local Road",
            "road_classification_number": None,
            "geometry": LineString([(90, 100), (95, 100)]),
        },
        {
            "name_1": "Far Lane",
            "name_2": None,
            "road_classification": "Minor Road",
            "road_classification_number": None,
            "geometry": LineString([(8000, 8000), (8010, 8000)]),
        },
        {
            "name_1": "Extra One",
            "name_2": None,
            "road_classification": "Local Road",
            "road_classification_number": None,
            "geometry": LineString([(160, 100), (180, 100)]),
        },
        {
            "name_1": "Extra Two",
            "name_2": None,
            "road_classification": "Local Road",
            "road_classification_number": None,
            "geometry": LineString([(200, 100), (220, 100)]),
        },
    ]


def zip_gpkg(gpkg_path, zip_path, arcname=None):
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    inner = arcname or Path(gpkg_path).name
    with ZipFile(zip_path, "w") as archive:
        archive.write(gpkg_path, arcname=inner)
    return zip_path
