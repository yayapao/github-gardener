"""Select the same self-contained payload for local installation and packaging."""
from pathlib import Path

ROOT_FILES = ("SKILL.md", "README.md", "CONTRIBUTING.md", "config.example.json", "LICENSE")
RESOURCE_DIRS = ("agents", "references", "scripts", "docs")


def skill_files(source):
    source = Path(source).resolve()
    if not (source / "SKILL.md").is_file():
        raise ValueError("Source lacks SKILL.md")
    selected = []
    for name in ROOT_FILES + RESOURCE_DIRS:
        entry = source / name
        if entry.is_symlink():
            raise ValueError("Skill payload cannot contain symlinks: " + name)
        if not entry.exists():
            continue
        paths = [entry] if entry.is_file() else sorted(entry.rglob("*"))
        for path in paths:
            relative = path.relative_to(source)
            if (any(part in {"__pycache__", ".git", ".github", ".venv"} for part in relative.parts)
                    or path.suffix == ".pyc" or path.name == ".DS_Store"):
                continue
            if path.is_symlink():
                raise ValueError("Skill payload cannot contain symlinks: " + str(relative))
            if path.is_file():
                selected.append(relative)
    return sorted(selected)
