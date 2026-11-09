"""Warm a local sqlite cache from the CSV zip while building. Do not pack sqlite."""

import importlib.util
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


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
            )
        finally:
            sys.path.pop(0)


setup(cmdclass={"build_py": BuildPy})
