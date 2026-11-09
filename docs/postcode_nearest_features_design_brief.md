# Design Brief: Postcode to Nearest Roads and Landmarks ETL

## Overview

Build an ETL process that links every UK postcode (from OS Open Names) to an ordered list of the nearest named features — primarily roads from OS Open Roads, with landmarks from OS Open Names inserted where they are closer.

The output is a ranked “nearest features” list per postcode that works in both urban and rural areas.

## Technology Stack

- **Python**: 3.14
- **Core library**: GeoPandas
- **Input formats**: GeoPackage for both source datasets
  - OS Open Names (`opname_gb.gpkg`)
  - OS Open Roads (`oproad_gb.gpkg`)
- **Spatial indexing**: GeoPandas spatial index (`sindex`) for nearest-neighbour queries
- **Coordinate reference system**: British National Grid (EPSG:27700)

## Source Data

### OS Open Names (GeoPackage)
- Postcode points (X, Y)
- Named places / landmarks (X, Y)
- Road/street names and their administrative attributes (district, borough, county, etc.)

### OS Open Roads (GeoPackage)
- Road link geometries (lines)
- Road names
- Road classifications

## Process Requirements

1. **Extract postcodes**  
   Load all postcode features from OS Open Names GeoPackage. Each postcode has a point geometry.

2. **Nearest roads (no distance threshold)**  
   For every postcode point, find the **k nearest road links** from OS Open Roads (recommended k = 5–7).  
   - No fixed distance cut-off (rural postcodes can be far from the nearest named road).  
   - Deduplicate by road name.  
   - Rank remaining unique road names by distance (nearest first).  
   - Flag unnamed road links.

3. **Landmarks**  
   From OS Open Names, identify named landmarks / places that are closer to the postcode point than the nearest road.  
   Insert any such landmarks into the ranked list at the correct distance position.

4. **Administrative data**  
   Attach administrative attributes (from OS Open Names) to the matched roads and landmarks.

5. **Edge cases**  
   - Postcodes with no nearby named road (e.g. large landmarks such as SW1A 1AA – Buckingham Palace).  
   - Postcodes that legitimately contain multiple street names.  
   - Unnamed road links.

## Output

One record per postcode containing:

- Postcode
- Postcode X, Y
- Ordered list of nearest features (roads and landmarks mixed), ranked by distance  
  Example structure:
  ```
  1. Buckingham Palace (landmark, 8 m)
  2. The Mall (road, 12 m)
  3. Buckingham Palace Road (road, 45 m)
  ...
  ```
- Administrative attributes for each feature where available

## Implementation Notes

- Prefer GeoPackage for both inputs so geometries and CRS are already present — no manual X/Y conversion required.
- Use GeoPandas `sindex.nearest` (or equivalent) for efficient k-nearest queries on the national datasets.
- Process in chunks or tiles if memory becomes an issue with the full Great Britain datasets.
- Deduplicate road names after the nearest-neighbour step so the final list contains unique names only.
- Output format is flexible (CSV, GeoPackage, Parquet, or database); prioritise ease of downstream use.
- Use sqlite as the intermediate processing format
- Use CSV as the published load format: one file per sqlite table (`postcode.csv`, `feature.csv`, `location.csv`) with the same columns and values.

## Constraints

- Free / Open Government Licence data only (OS Open Names + OS Open Roads).
- Must handle rural multi-street postcodes without a distance threshold.
- Keep the number of results per postcode bounded (top unique names after ranking) to control output size.
