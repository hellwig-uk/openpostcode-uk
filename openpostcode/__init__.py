"""OS Open Names / Open Roads postcode nearest-feature ETL."""

UNIQUE_NAME_CAP = 5
BNG_EPSG = 27700
TILE_METRES = 100_000
ROAD_LOCAL_TYPES = frozenset(
    {
        "Named Road",
        "Section Of Named Road",
        "Numbered Road",
        "Section Of Numbered Road",
    }
)
LANDMARK_EXCLUDED_TYPES = frozenset({"Postcode"}) | ROAD_LOCAL_TYPES
