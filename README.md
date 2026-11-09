# openpostcode-uk

The definitive UK mapping from postcode and house number to a street, town, and related address fields is Royal Mail’s Postcode Address File (PAF). That database is Royal Mail’s property. It is copyrighted and licensed; you cannot use it freely in a product.

This package exists because a lot of software only needs a good-enough place for a postcode: “which road is this near?”, “which neighbourhood?”, enough to pre-fill or check an address form. Ordnance Survey publishes **OS Open Names** (including postcode points) and **OS Open Roads** under the Open Government Licence. From those, we match each postcode point to nearby named roads and landmarks. That is an approximation of PAF, not a copy of it. There is no house-number list and no official “this premises is on this street” row.

For most lookup and form-assist use cases that approximation is enough. Forms that assumed a licensed PAF (type a postcode, pick the exact street for that premise) need a small change in construction: treat the results as nearby context the user can confirm or edit, rather than as the Royal Mail street for a given house number.

There are two ways to get that context.

**Use the published lookup.** `pip install openpostcodeuk` installs the library and a command named `openpostcode_uk`. Both read a zip this repo already committed: nearest features for every GB postcode, built from a known OS Open Names / Open Roads release. Stdlib only. No Ordnance Survey download.

**Build from the OS sources.** Clone this repo, install `[dev]`, and run `python main.py export`. That downloads the national GeoPackages (~1.2 GB), matches every postcode against roads and landmarks, and writes the same zip. Use this to reproduce the match, change it, or produce a zip from a newer OS release before the GitHub Action has committed one.

The rest of this file shows the lookup output, then each path in detail.

## Lookup output

Up to five uniquely named features; unnamed rows count toward the cap. Distances are metres, weighted by the matcher.

`openpostcode_uk` (installed package) and `python main.py get` / `python get.py` (repo, after sqlite exists) print the same text. Unknown postcode exits `1` with `postcode not found`. SQL NULL prints as `null`.

### `SE1 9SG` — named road (London Bridge Street)

```text
$ openpostcode_uk SE1 9SG
road: London Bridge Street
weighted_distance: 12
kind: road
unnamed: 0
classification: Unclassified
local_type: null
populated_place: Bermondsey
district_borough: Southwark
county_unitary: Greater London
country: England
-------
road: St Thomas Street
weighted_distance: 43
kind: road
unnamed: 0
classification: A Road
local_type: null
populated_place: Bermondsey
district_borough: Southwark
county_unitary: Greater London
country: England
-------
road: Railway Approach
weighted_distance: 49
kind: road
unnamed: 0
classification: Not Classified
local_type: null
populated_place: Bermondsey
district_borough: Southwark
county_unitary: Greater London
country: England
-------
road: Joiner Street
weighted_distance: 62
kind: road
unnamed: 0
classification: Not Classified
local_type: null
populated_place: Bermondsey
district_borough: Southwark
county_unitary: Greater London
country: England
-------
road: unnamed
weighted_distance: 71
kind: road
unnamed: 1
classification: Unclassified
local_type: null
populated_place: Bermondsey
district_borough: Southwark
county_unitary: Greater London
country: England
-------
```

```python
import openpostcodeuk as opuk

opuk.get("SE1 9SG")
```

Unknown postcode returns `None`. A hit is a list: index `0` is the postcode as stored in sqlite (`SE19SG`, no space). Each following item is a dict. The feature kind is the first key and the name is its value (`"road": "London Bridge Street"`). There is no second `kind` field. Remaining keys, in order: `weighted_distance`, `unnamed`, `classification`, `local_type`, `populated_place`, `district_borough`, `county_unitary`, `country`. SQL NULL is Python `None`. `unnamed` and `weighted_distance` are `int`.

```python
[
    "SE19SG",
    {
        "road": "London Bridge Street",
        "weighted_distance": 12,
        "unnamed": 0,
        "classification": "Unclassified",
        "local_type": None,
        "populated_place": "Bermondsey",
        "district_borough": "Southwark",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "St Thomas Street",
        "weighted_distance": 43,
        "unnamed": 0,
        "classification": "A Road",
        "local_type": None,
        "populated_place": "Bermondsey",
        "district_borough": "Southwark",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Railway Approach",
        "weighted_distance": 49,
        "unnamed": 0,
        "classification": "Not Classified",
        "local_type": None,
        "populated_place": "Bermondsey",
        "district_borough": "Southwark",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Joiner Street",
        "weighted_distance": 62,
        "unnamed": 0,
        "classification": "Not Classified",
        "local_type": None,
        "populated_place": "Bermondsey",
        "district_borough": "Southwark",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "unnamed",
        "weighted_distance": 71,
        "unnamed": 1,
        "classification": "Unclassified",
        "local_type": None,
        "populated_place": "Bermondsey",
        "district_borough": "Southwark",
        "county_unitary": "Greater London",
        "country": "England",
    },
]
```

### `SW1A 1AA` — Buckingham Palace

```text
$ openpostcode_uk SW1A 1AA
road: unnamed
weighted_distance: 67
kind: road
unnamed: 1
classification: Not Classified
local_type: null
populated_place: City of Westminster
district_borough: City of Westminster
county_unitary: Greater London
country: England
-------
road: Buckingham Gate
weighted_distance: 101
kind: road
unnamed: 0
classification: A Road
local_type: null
populated_place: City of Westminster
district_borough: City of Westminster
county_unitary: Greater London
country: England
-------
road: Birdcage Walk
weighted_distance: 101
kind: road
unnamed: 0
classification: Not Classified
local_type: null
populated_place: City of Westminster
district_borough: City of Westminster
county_unitary: Greater London
country: England
-------
road: Constitution Hill
weighted_distance: 134
kind: road
unnamed: 0
classification: Not Classified
local_type: null
populated_place: City of Westminster
district_borough: City of Westminster
county_unitary: Greater London
country: England
-------
road: Stafford Place
weighted_distance: 146
kind: road
unnamed: 0
classification: Unclassified
local_type: null
populated_place: City of Westminster
district_borough: City of Westminster
county_unitary: Greater London
country: England
-------
```

```python
opuk.get("SW1A 1AA")
```

```python
[
    "SW1A1AA",
    {
        "road": "unnamed",
        "weighted_distance": 67,
        "unnamed": 1,
        "classification": "Not Classified",
        "local_type": None,
        "populated_place": "City of Westminster",
        "district_borough": "City of Westminster",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Buckingham Gate",
        "weighted_distance": 101,
        "unnamed": 0,
        "classification": "A Road",
        "local_type": None,
        "populated_place": "City of Westminster",
        "district_borough": "City of Westminster",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Birdcage Walk",
        "weighted_distance": 101,
        "unnamed": 0,
        "classification": "Not Classified",
        "local_type": None,
        "populated_place": "City of Westminster",
        "district_borough": "City of Westminster",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Constitution Hill",
        "weighted_distance": 134,
        "unnamed": 0,
        "classification": "Not Classified",
        "local_type": None,
        "populated_place": "City of Westminster",
        "district_borough": "City of Westminster",
        "county_unitary": "Greater London",
        "country": "England",
    },
    {
        "road": "Stafford Place",
        "weighted_distance": 146,
        "unnamed": 0,
        "classification": "Unclassified",
        "local_type": None,
        "populated_place": "City of Westminster",
        "district_borough": "City of Westminster",
        "county_unitary": "Greater London",
        "country": "England",
    },
]
```

## Using the published lookup

This is the path for application code. The data file is part of the package (and of git). You do not run the matcher.

The committed artefact is `etl/load/openpostcode_uk.zip`: three CSVs (`postcode.csv`, `feature.csv`, `location.csv`) that are 1:1 with the sqlite tables. A daily GitHub Action lists OS Open Names and Open Roads. When either zip md5 differs from `etl/sources.json`, it runs export, commits that zip plus `sources.json`, copies the zip into `openpostcodeuk/data/openpostcode_uk.zip` for the wheel, sets version `1.{year}.{day-of-year}` from the latest OS zip `Last-Modified`, and tags `v1.{year}.{yday}`. That tag dispatches `publish.yml`, which uploads the CSV-zip sdist to PyPI with Trusted Publishing (GitHub environment `pypi`). Git history is the version of the data.

```bash
python -m pip install openpostcodeuk
openpostcode_uk SE1 9SG
```

```python
import openpostcodeuk as opuk

opuk.get("SE1 9SG")
```

Default install is stdlib only. PyPI ships an sdist with `openpostcode_uk.zip` (the three table CSVs), not a wheel and not sqlite. `pip install openpostcodeuk` builds from that sdist and **imports the zip into a local sqlite cache as part of the install** (several minutes, once per version). After that, `opuk.get` and `openpostcode_uk` open the cache and return immediately. Cache directory is `$OPENPOSTCODEUK_CACHE`, else `$XDG_CACHE_HOME/openpostcodeuk`, else `~/.cache/openpostcodeuk`. There is no GitHub fetch at lookup time and no geopandas. Set `OPENPOSTCODEUK_SKIP_IMPORT=1` to skip the install-time import (editable/dev installs and the export Action).

From a clone, the same lookup without a wheel install still needs that zip (from git, or after `export` / `import`). Then:

```bash
.venv/bin/python get.py SW1A 1AA
.venv/bin/python main.py get SW1A 1AA
```

Those two commands read `etl/transform/lookup.sqlite`. Missing sqlite prints `sqlite not found; run export or import`.

`python main.py import` is how a clone refreshes sqlite from the **published** zip on GitHub (`etl/load/openpostcode_uk.zip` on `main`). It compares GitHub `etl/sources.json` to the local catalog. When sqlite and the local zip already match that catalog, import does nothing. When GitHub has a newer export, it downloads the zip and rebuilds sqlite. That is still “use the committed values”; it does not download OS GeoPackages or rematch the country.

## Building from OS sources

This is the path for producing the zip: matching every GB postcode against OS Open Names and OS Open Roads yourself.

You need a clone, Python 3.14, disk for the national GeoPackages (Open Names ~200 MB zip, Open Roads ~1 GB zip, plus unzipped GPKGs and sqlite), and the `[dev]` extra (geopandas, pyogrio, tqdm, plus black / isort / coverage for tests). A full rematch is slow (hours on a GitHub-hosted runner).

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python main.py export
```

`export` always hits the OS list JSON (cheap). For each product it downloads the GB zip only when the extract zip is missing or `etl/sources.json` md5 does not match the list. After a download it verifies `file_md5` against the list. It rematches sqlite when sqlite is missing, when an OS md5 changed, or with `--force`. It writes `etl/load/openpostcode_uk.zip` when that zip is missing or sqlite was rebuilt. When catalog, sqlite, and zip are already current, it logs that and exits 0.

`--force` rematches from the GeoPackages already on disk and skips re-download of present zips:

```bash
.venv/bin/python main.py export --force
```

`python main.py` with no command prints help. `--etl-dir` defaults to `etl`.

After a successful export in this repo, the new zip is also copied to `openpostcodeuk/data/` (wheel payload) and `pyproject.toml` version is set from the OS zip dates. The Action is the automated version of that: same `export`, then commit and tag when files changed.

Use this path when you want the match computed on your machine from the Ordnance Survey files, when you are changing matching code, or when you need a zip from OS data that is not yet in git.

## ETL layout

| Path | Role |
| --- | --- |
| `etl/extract/` | OS zips and GeoPackages (gitignored). Only needed to **build**. |
| `etl/transform/lookup.sqlite` | Working lookup DB (gitignored). `main.py get` / `get.py` read this. |
| `etl/load/openpostcode_uk.zip` | Published table CSVs. Committed. What **users** of the package consume. |
| `etl/sources.json` | OS list URLs and source-zip md5s for that export. Committed. |
| `openpostcodeuk/data/openpostcode_uk.zip` | Copy of the load zip inside the wheel. |

## Development commands

Format the tree (isort, then Black):

```bash
.venv/bin/python main.py format
```

Check isort, Black, tests, and 100% branch coverage:

```bash
.venv/bin/python main.py test
```

## Licence

The code is MIT. The lookup data is built from OS Open Names and OS Open Roads, which are public sector information under the Open Government Licence v3.0. Both apply: MIT for the software, OGL for the Ordnance Survey data. OGL requires this attribution:

Contains OS data © Crown copyright and database right 2026.  
Contains public sector information licensed under the Open Government Licence v3.0.  
https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

Full text is in `LICENSE`.
