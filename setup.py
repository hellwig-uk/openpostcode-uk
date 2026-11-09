"""Warm a local sqlite cache from the CSV zip while building. Do not pack sqlite."""

import importlib.util
import sys
import tomllib
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


def _project_version():
    path = Path(__file__).resolve().parent / "pyproject.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


class BuildPy(build_py):
    def run(self):
        super().run()
        sys.dont_write_bytecode = True
        sys.path.insert(0, self.build_lib)
        try:
            load_path = Path(self.build_lib) / "openpostcodeuk" / "load.py"
            spec = importlib.util.spec_from_file_location(
                "_openpostcodeuk_build_load", load_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.run_build_import(
                self.build_lib,
                log=sys.stderr,
                editable=getattr(self, "editable_mode", False),
                version=_project_version(),
            )
        finally:
            sys.path.pop(0)


setup(cmdclass={"build_py": BuildPy})
