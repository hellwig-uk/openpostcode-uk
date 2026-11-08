import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opennames.gitindex import _repo_root, sync_load_zip


class GitIndexTests(unittest.TestCase):
    def test_repo_root_missing(self):
        with mock.patch(
            "opennames.gitindex.subprocess.check_output",
            side_effect=FileNotFoundError,
        ):
            self.assertIsNone(_repo_root("."))
        with mock.patch(
            "opennames.gitindex.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            self.assertIsNone(_repo_root("."))

    def test_sync_skips_without_repo(self):
        with mock.patch("opennames.gitindex._repo_root", return_value=None):
            sync_load_zip("/tmp/etl", "openpostcode_uk_2026001.zip")

    def test_sync_skips_other_etl_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            etl = Path(tmp) / "etl"
            etl.mkdir()
            with mock.patch(
                "opennames.gitindex._repo_root",
                return_value=Path(tmp) / "repo",
            ):
                sync_load_zip(etl, "openpostcode_uk_2026001.zip")

    def test_sync_adds_and_removes(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            etl = top / "etl"
            (etl / "load").mkdir(parents=True)
            zip_name = "openpostcode_uk_2026002.zip"
            calls = []

            def check_output(cmd, cwd=None, text=False, stderr=None):
                calls.append(("out", cmd, cwd))
                if cmd[:2] == ["git", "rev-parse"]:
                    return str(top) + "\n"
                if cmd[:2] == ["git", "ls-files"]:
                    return (
                        "etl/load/openpostcode_uk_2026001.zip\n"
                        "etl/load/.gitkeep\n"
                        f"etl/load/{zip_name}\n"
                    )
                raise AssertionError(cmd)

            def run(cmd, cwd=None, check=False, stdout=None, stderr=None):
                calls.append(("run", cmd, cwd))
                return subprocess.CompletedProcess(cmd, 0)

            with mock.patch("opennames.gitindex.subprocess.check_output", check_output):
                with mock.patch("opennames.gitindex.subprocess.run", run):
                    sync_load_zip(etl, zip_name)
            run_cmds = [item[1] for item in calls if item[0] == "run"]
            self.assertIn(["git", "add", "-f", f"etl/load/{zip_name}"], run_cmds)
            self.assertTrue(
                any(
                    cmd[:3] == ["git", "rm", "--cached"]
                    and "openpostcode_uk_2026001.zip" in cmd[-1]
                    for cmd in run_cmds
                )
            )
            self.assertFalse(
                any(
                    cmd[:3] == ["git", "rm", "--cached"] and zip_name in cmd[-1]
                    for cmd in run_cmds
                )
            )
