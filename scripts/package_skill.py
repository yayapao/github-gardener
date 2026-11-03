#!/usr/bin/env python3
"""Build a self-contained .skill ZIP with tests and evals; no network or Token."""
import argparse
from pathlib import Path
import zipfile
from skill_files import skill_files


def package(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source.name != "github-gardener" or not (source / "SKILL.md").is_file():
        raise ValueError("Expected a github-gardener directory with SKILL.md")
    if destination.is_relative_to(source):
        raise ValueError("Place the archive outside the source directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in skill_files(source):
            archive.write(source / relative, Path("github-gardener") / relative)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip():
            raise ValueError("Archive integrity check failed")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parents[1], args.output))
