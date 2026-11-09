"""Keep HEAD tracking only etl/load/openpostcode_uk.zip."""

import subprocess
from pathlib import Path


def _repo_root(cwd):
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return None
    return Path(output.strip())


def sync_load_zip(etl_dir, output_zip_name):
    etl_dir = Path(etl_dir).resolve()
    top = _repo_root(etl_dir)
    if top is None:
        return
    repo_etl = (top / "etl").resolve()
    if etl_dir != repo_etl:
        return
    rel = Path("etl") / "load" / output_zip_name
    subprocess.run(
        ["git", "add", "-f", str(rel)],
        cwd=top,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    listed = subprocess.check_output(
        ["git", "ls-files", "etl/load"],
        cwd=top,
        text=True,
    )
    for line in listed.splitlines():
        name = Path(line).name
        if not name.startswith("openpostcode_uk_") or not name.endswith(".zip"):
            continue
        subprocess.run(
            ["git", "rm", "--cached", "-q", "--ignore-unmatch", line],
            cwd=top,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
