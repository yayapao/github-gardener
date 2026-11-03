#!/usr/bin/env python3
"""Install a self-contained skill, keeping upgrades recoverable."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile
from skill_files import skill_files


def install(source, target, force=False):
    source, target = Path(source).resolve(), Path(target).expanduser().absolute()
    if target.name != "github-gardener":
        raise ValueError("Destination must end in github-gardener")
    if (target.is_symlink() or target.resolve().is_relative_to(source)
            or source.is_relative_to(target.resolve())):
        raise ValueError("Destination overlaps source or is a symlink")
    payload = skill_files(source)
    if target.exists() and not force:
        raise ValueError("Destination exists; use --force to preserve it in a backup and replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".gardener-install-", dir=target.parent))
    staging = staging_root / "github-gardener"
    backup = None
    try:
        staging.mkdir()
        for relative in payload:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, destination)
        if not (staging / "SKILL.md").is_file():
            raise ValueError("Source lacks SKILL.md")
        if target.exists():
            backup_root = target.parent.parent / "skill-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix="github-gardener-", dir=backup_root)) / "github-gardener"
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup:
                backup.rename(target)
            raise
    finally:
        # Only the exact, newly created temporary directory is removed.
        shutil.rmtree(staging_root)
    return {"installed": str(target), "backup": str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", help="Exact skill directory; must end in github-gardener")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    codex_root = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    target = Path(args.destination) if args.destination else codex_root / "skills" / "github-gardener"
    try:
        result = install(source, target, args.force)
        print("Installed: " + result["installed"])
        if result["backup"]:
            print("Recoverable backup: " + result["backup"])
        print("Open a new Codex session to discover the skill.")
    except (OSError, ValueError) as exc:
        parser.exit(2, "install: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
