"""Command-line entry points."""

import argparse
import subprocess
import sys
from pathlib import Path

from openpostcode.build import run_build, run_import
from openpostcode.lookup import lookup
from openpostcode.paths import etl_paths

QUALITY_PATHS = ("openpostcode", "tests", "main.py", "get.py")
_COMMANDS = {"build", "get", "format", "test", "import"}
_VALUE_FLAGS = {"--etl-dir"}
_BARE_FLAGS = {"--force"}


def _etl_dir_arg(parser):
    parser.add_argument(
        "--etl-dir",
        default="etl",
        help="ETL directory (default: etl)",
    )


def hoist_global_options(argv):
    argv = list(argv)
    cmd_at = next((i for i, arg in enumerate(argv) if arg in _COMMANDS), None)
    if cmd_at is None:
        return argv
    head, command, tail = argv[:cmd_at], argv[cmd_at], argv[cmd_at + 1 :]
    hoisted = []
    kept = []
    i = 0
    while i < len(tail):
        arg = tail[i]
        if arg in _BARE_FLAGS:
            hoisted.append(arg)
            i += 1
        elif arg in _VALUE_FLAGS and i + 1 < len(tail):
            hoisted.extend([arg, tail[i + 1]])
            i += 2
        elif arg.startswith("--etl-dir="):
            hoisted.append(arg)
            i += 1
        else:
            kept.append(arg)
            i += 1
    return hoisted + head + [command] + kept


def build_parser():
    parser = argparse.ArgumentParser(prog="main.py")
    _etl_dir_arg(parser)
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild sqlite and export from local files; do not re-download present zips",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "build",
        help="fetch, transform, and export",
        description=(
            "fetch, transform, and export. "
            "Use --force to rebuild sqlite and the export from local files "
            "without re-downloading zips that are already present."
        ),
    )
    get_parser = sub.add_parser("get", help="look up a postcode in sqlite")
    get_parser.add_argument("postcode", nargs="*")
    sub.add_parser(
        "import",
        help="download the published zip and rebuild sqlite",
    )
    sub.add_parser("format", help="run isort then black")
    sub.add_parser(
        "test",
        help="check isort, black, tests, and 100%% branch coverage",
    )
    return parser


def get_parser():
    parser = argparse.ArgumentParser(prog="get.py")
    _etl_dir_arg(parser)
    parser.add_argument("postcode", nargs="*")
    return parser


def cmd_build(etl_dir, progress=True, log=None, force=False):
    paths = etl_paths(etl_dir)
    return run_build(paths, progress=progress, log=log, force=force)


def cmd_import(etl_dir, progress=True):
    paths = etl_paths(etl_dir)
    return run_import(paths, progress=progress)


def repo_root():
    return Path(__file__).resolve().parents[1]


def _tool(module_args, stdout, stderr):
    result = subprocess.run(
        [sys.executable, "-m", *module_args],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        stdout.write(result.stdout)
    if result.stderr:
        stderr.write(result.stderr)
    return result.returncode


def cmd_format(stdout, stderr):
    code = _tool(["isort", *QUALITY_PATHS], stdout, stderr)
    if code:
        return code
    return _tool(["black", *QUALITY_PATHS], stdout, stderr)


def cmd_test(stdout, stderr):
    code = _tool(["isort", "--check-only", *QUALITY_PATHS], stdout, stderr)
    if code:
        return code
    code = _tool(["black", "--check", *QUALITY_PATHS], stdout, stderr)
    if code:
        return code
    code = _tool(
        [
            "coverage",
            "run",
            "--branch",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-t",
            ".",
        ],
        stdout,
        stderr,
    )
    if code:
        return code
    return _tool(["coverage", "report", "--fail-under", "100"], stdout, stderr)


def cmd_get(etl_dir, tokens, stdout, stderr):
    paths = etl_paths(etl_dir)
    if not tokens:
        stderr.write("postcode not found\n")
        return 1
    code, out, err = lookup(paths["sqlite"], tokens)
    if out:
        stdout.write(out)
    if err:
        stderr.write(err + "\n")
    return code


def main(argv=None, stdout=None, stderr=None, progress=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parser = build_parser()
    args = parser.parse_args(hoist_global_options(argv))
    if args.command is None:
        parser.print_help(stdout)
        return 0
    use_progress = sys.stderr.isatty() if progress is None else progress
    if args.command == "get":
        return cmd_get(args.etl_dir, args.postcode, stdout, stderr)
    if args.command == "format":
        return cmd_format(stdout, stderr)
    if args.command == "test":
        return cmd_test(stdout, stderr)
    if args.command == "import":
        return cmd_import(args.etl_dir, progress=use_progress)
    return cmd_build(
        args.etl_dir,
        progress=use_progress,
        log=stderr,
        force=getattr(args, "force", False),
    )


def main_get(argv=None, stdout=None, stderr=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    parser = get_parser()
    args = parser.parse_args(argv)
    return cmd_get(args.etl_dir, args.postcode, stdout, stderr)
