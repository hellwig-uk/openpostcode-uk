# openpostcode-uk

Approximate GB location context for a postcode from OS Open Names and OS Open Roads (Open Government Licence).

## Setup

Python 3.14. Use the project virtualenv:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

## ETL layout

| Path | Role |
| --- | --- |
| `etl/extract/` | downloaded zips and GeoPackages (gitignored) |
| `etl/transform/lookup.sqlite` | intermediate lookup database (gitignored) |
| `etl/load/openpostcode_uk_YYYYDDD.zip` | published `postcodes.csv` + `features.csv` |
| `etl/sources.json` | OS list URLs and source-zip md5s for that export |

`YYYY` is the local year of the build; `DDD` is the local day of the year (`001`–`366`).

## Commands

Fetch (if needed), transform, and export:

```bash
.venv/bin/python main.py build
```

`python main.py` with no command prints help. `--etl-dir` defaults to `etl`. Rebuild sqlite and the export from local extract files (`--force` does not re-download zips that are already present):

```bash
.venv/bin/python main.py build --force
```

Look up one postcode in sqlite:

```bash
.venv/bin/python get.py SW1A 1AA
.venv/bin/python main.py get SW1A 1AA
```

Unknown postcode exits `1`. Missing sqlite prints `sqlite not found; run build`.

Format the tree (isort, then Black):

```bash
.venv/bin/python main.py format
```

Check isort, Black, tests, and 100% branch coverage:

```bash
.venv/bin/python main.py test
```

Data attribution is in `LICENSE`.
