"""Build hook: import the lookup zip into sqlite while building the wheel."""

import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        sys.path.insert(0, self.build_lib)
        try:
            from openpostcodeuk.load import run_build_import

            run_build_import(
                self.build_lib,
                log=sys.stderr,
                editable=getattr(self, "editable_mode", False),
            )
        finally:
            sys.path.pop(0)


setup(cmdclass={"build_py": BuildPy})
