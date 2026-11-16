#!/usr/bin/env python3
"""Persist Git identity after gh authorization; configure only the selected repository."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def identity_path():
    root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root.expanduser() / "github-gardener" / "identity.json"


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        # Do not echo external command diagnostics that could contain credentials.
        if "user/emails" in args:
            raise ValueError("Cannot read verified primary email; refresh gh authorization with user:email")
        raise ValueError(args[0] + " failed; check authentication or repository access")
    return result.stdout.strip()


def current_user():
    user = json.loads(run("gh", "api", "--hostname", "github.com", "--method", "GET", "user"))
    if not isinstance(user, dict) or not user.get("login") or type(user.get("id")) is not int:
        raise ValueError("GitHub did not return a valid authenticated user")
    return user


def verified_primary_email():
    emails = json.loads(run("gh", "api", "--hostname", "github.com", "--method", "GET", "user/emails"))
    if not isinstance(emails, list):
        raise ValueError("GitHub did not return an email list")
    primary = [entry.get("email") for entry in emails if isinstance(entry, dict)
               and entry.get("primary") is True and entry.get("verified") is True]
    if len(primary) != 1 or not isinstance(primary[0], str):
        raise ValueError("No unique verified primary email; confirm the email on GitHub and authorize again")
    return primary[0]


def validate(identity):
    fields = {"version", "host", "github_login", "github_user_id", "git_name", "git_email", "git_email_source"}
    if isinstance(identity, dict):
        identity = {"git_email_source": "unknown", **identity}
    if not isinstance(identity, dict) or set(identity) != fields:
        raise ValueError("Invalid local identity configuration")
    if identity["version"] != 1 or identity["host"] != "github.com":
        raise ValueError("Unsupported identity configuration")
    if type(identity["github_user_id"]) is not int or identity["github_user_id"] < 1:
        raise ValueError("Invalid GitHub user ID")
    if not isinstance(identity["github_login"], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", identity["github_login"]):
        raise ValueError("Invalid GitHub login")
    for key in ("git_name", "git_email"):
        value = identity[key]
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0<>"):
            raise ValueError("Invalid " + key)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", identity["git_email"]):
        raise ValueError("Invalid git_email")
    if identity["git_email_source"] not in {"github_verified_primary", "user_input", "github_profile", "unknown"}:
        raise ValueError("Invalid git_email_source")
    return identity


def load_identity(require_verified=True):
    path = identity_path()
    if not path.is_file():
        raise ValueError("No saved identity; run setup after GitHub authorization")
    identity = validate(json.loads(path.read_text()))
    if require_verified and identity["git_email_source"] != "github_verified_primary":
        raise ValueError("Saved email was not verified through GitHub; authorize and run setup again")
    return identity


def verify_account(identity, user):
    if (identity["github_user_id"] != user["id"] or
            identity["github_login"].casefold() != user["login"].casefold()):
        raise ValueError("Active GitHub account differs from saved identity; do not switch silently")


def verify_identity(identity):
    verify_account(identity, current_user())
    if identity["git_email"] != verified_primary_email():
        raise ValueError("GitHub primary email changed; run setup to refresh the saved identity")


def setup_identity(expected_login=None, replace_account=False):
    user = current_user()
    if expected_login and user["login"].casefold() != expected_login.casefold():
        raise ValueError("Active GitHub account does not match the requested login")
    previous = load_identity(require_verified=False) if identity_path().exists() else None
    if previous and not replace_account:
        verify_account(previous, user)
    identity = validate({
        "version": 1,
        "host": "github.com",
        "github_login": user["login"],
        "github_user_id": user["id"],
        "git_name": user["login"],
        "git_email": verified_primary_email(),
        "git_email_source": "github_verified_primary",
    })
    path = identity_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".identity-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(json.dumps(identity, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return identity


def apply_identity(repo):
    identity = load_identity()
    verify_identity(identity)
    root = str(Path(repo).expanduser().resolve())
    run("git", "-C", root, "rev-parse", "--git-dir")
    run("git", "-C", root, "config", "--local", "user.name", identity["git_name"])
    run("git", "-C", root, "config", "--local", "user.email", identity["git_email"])
    prefix = identity["git_name"] + " <" + identity["git_email"] + "> "
    for variable in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        if not run("git", "-C", root, "var", variable).startswith(prefix):
            raise ValueError(variable + " is overridden; resolve the environment before committing")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="Save identity after successful gh authorization")
    setup.add_argument("--expected-login", help="Require this GitHub account before saving")
    setup.add_argument("--replace-account", action="store_true", help="Use only after an authorized account change")
    show = commands.add_parser("show")
    show.add_argument("--verify", action="store_true", help="Also check the active GitHub account")
    apply = commands.add_parser("apply", help="Set and verify repository-local Git identity")
    apply.add_argument("--repo", required=True)
    args = parser.parse_args()
    try:
        if args.command == "setup":
            identity = setup_identity(args.expected_login, args.replace_account)
        elif args.command == "apply":
            identity = apply_identity(args.repo)
        else:
            identity = load_identity()
            if args.verify:
                verify_identity(identity)
        print(json.dumps({"path": str(identity_path()), **identity}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("github-identity: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
