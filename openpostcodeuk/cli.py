"""Console script matching python main.py get output."""

import argparse
import sys

from openpostcode.lookup import lookup
from openpostcodeuk.load import ensure_sqlite


def build_parser():
    parser = argparse.ArgumentParser(prog="openpostcode_uk")
    parser.add_argument("postcode", nargs="*")
    return parser


def main(argv=None, stdout=None, stderr=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    args = build_parser().parse_args(argv)
    if not args.postcode:
        stderr.write("postcode not found\n")
        return 1
    try:
        sqlite = ensure_sqlite()
    except FileNotFoundError:
        stderr.write("sqlite not found; run export or import\n")
        return 1
    code, out, err = lookup(sqlite, args.postcode)
    if out:
        stdout.write(out)
    if err:
        stderr.write(err + "\n")
    return code
