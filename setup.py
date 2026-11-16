from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).parent


class BuildPy(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / "dam_verify" / "_resources"
        for source, destination, pattern in ((ROOT / "schemas", target / "schemas", "*.json"),
                                            (ROOT / "dam" / "action_bundles", target / "action_bundles", "*.yaml")):
            destination.mkdir(parents=True, exist_ok=True)
            for path in source.glob(pattern):
                if path.is_file():
                    copy2(path, destination / path.name)


setup(cmdclass={"build_py": BuildPy})
