"""Resolve per-user paths without depending on a checkout or the current directory."""
import os
from pathlib import Path


def config_root(home=None, environ=None, platform=None):
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    platform = os.name if platform is None else platform
    configured = environ.get("XDG_CONFIG_HOME")
    # The XDG specification requires an absolute path; ignore relative values.
    if configured and Path(configured).is_absolute():
        return Path(configured)
    appdata = environ.get("APPDATA") if platform == "nt" else None
    if appdata and Path(appdata).is_absolute():
        return Path(appdata)
    return home / ".config"


def default_skill_path(home=None, environ=None):
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    configured = environ.get("CODEX_HOME")
    root = Path(configured).expanduser() if configured else home / ".codex"
    if not root.is_absolute():
        raise ValueError("CODEX_HOME must be an absolute path; use --destination for a relative target")
    return root / "skills" / "github-gardener"
