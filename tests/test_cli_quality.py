import io
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from openpostcode.cli import (
    QUALITY_PATHS,
    _tool,
    cmd_format,
    cmd_test,
    hoist_global_options,
    main,
    repo_root,
)


def _result(code, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["python"],
        returncode=code,
        stdout=stdout,
        stderr=stderr,
    )


class QualityCliTests(unittest.TestCase):
    def test_repo_root(self):
        self.assertEqual(repo_root(), Path(__file__).resolve().parents[1])

    def test_tool_forwards_output(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch(
            "openpostcode.cli.subprocess.run",
            return_value=_result(3, "out\n", "err\n"),
        ) as run:
            code = _tool(["isort", *QUALITY_PATHS], stdout, stderr)
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(), "out\n")
        self.assertEqual(stderr.getvalue(), "err\n")
        self.assertEqual(run.call_args.kwargs["cwd"], str(repo_root()))

    def test_tool_skips_empty_streams(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch(
            "openpostcode.cli.subprocess.run",
            return_value=_result(0, "", ""),
        ):
            self.assertEqual(_tool(["black"], stdout, stderr), 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_format_runs_isort_then_black(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd[2:])
            return _result(0)

        with mock.patch("openpostcode.cli.subprocess.run", run):
            self.assertEqual(cmd_format(io.StringIO(), io.StringIO()), 0)
        self.assertEqual(
            calls,
            [
                ["isort", *QUALITY_PATHS],
                ["black", *QUALITY_PATHS],
            ],
        )

    def test_format_stops_when_isort_fails(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd[2])
            return _result(1)

        with mock.patch("openpostcode.cli.subprocess.run", run):
            self.assertEqual(cmd_format(io.StringIO(), io.StringIO()), 1)
        self.assertEqual(calls, ["isort"])

    def test_format_stops_when_black_fails(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd[2])
            return _result(0 if cmd[2] == "isort" else 1)

        with mock.patch("openpostcode.cli.subprocess.run", run):
            self.assertEqual(cmd_format(io.StringIO(), io.StringIO()), 1)
        self.assertEqual(calls, ["isort", "black"])

    def test_test_stops_on_each_stage(self):
        stages = [
            (["isort"], 1),
            (["isort", "black"], 2),
            (["isort", "black", "coverage"], 3),
            (["isort", "black", "coverage", "coverage"], 4),
            (["isort", "black", "coverage", "coverage"], 0),
        ]
        for expected_modules, fail_at in stages:
            calls = []

            def run(cmd, fail_at=fail_at, calls=calls, **kwargs):
                calls.append(cmd[2])
                if fail_at and len(calls) == fail_at:
                    return _result(1)
                return _result(0)

            with mock.patch("openpostcode.cli.subprocess.run", run):
                code = cmd_test(io.StringIO(), io.StringIO())
            self.assertEqual(calls, expected_modules)
            self.assertEqual(code, 0 if fail_at == 0 else 1)

    def test_hoist_global_options(self):
        self.assertEqual(hoist_global_options(["--etl-dir", "x"]), ["--etl-dir", "x"])
        self.assertEqual(
            hoist_global_options(["export", "--force"]),
            ["--force", "export"],
        )
        self.assertEqual(
            hoist_global_options(["export", "--etl-dir", "x", "--force"]),
            ["--etl-dir", "x", "--force", "export"],
        )
        self.assertEqual(
            hoist_global_options(["get", "--etl-dir=foo", "SW1A", "1AA"]),
            ["--etl-dir=foo", "get", "SW1A", "1AA"],
        )
        self.assertEqual(
            hoist_global_options(["import", "--etl-dir", "x"]),
            ["--etl-dir", "x", "import"],
        )

    def test_main_dispatches_format_and_test(self):
        with mock.patch("openpostcode.cli.cmd_format", return_value=0) as fmt:
            self.assertEqual(main(["format"]), 0)
            fmt.assert_called_once()
        with mock.patch("openpostcode.cli.cmd_test", return_value=0) as test:
            self.assertEqual(main(["test"]), 0)
            test.assert_called_once()
        with mock.patch("openpostcode.cli.cmd_import", return_value=0) as imported:
            self.assertEqual(main(["import"], progress=False), 0)
            imported.assert_called_once()
        with mock.patch("openpostcode.cli.cmd_export", return_value=0) as exported:
            self.assertEqual(main(["export"], progress=False), 0)
            exported.assert_called_once()
