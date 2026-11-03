#!/usr/bin/env python3
"""Prepare or verify a local diff bundle. Never calls gh, git, or the network."""
import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def file_bytes(root, name):
    parts = PurePosixPath(name)
    if parts.is_absolute() or not parts.parts or any(p in {"..", ".git"} for p in parts.parts):
        raise ValueError("Unsafe repository-relative file: " + name)
    root = Path(root).resolve()
    target = root.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError("File escapes root: " + name)
    for parent in [target] + list(target.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Symlinks are not accepted: " + name)
    return target.read_bytes() if target.is_file() else None


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() if data is not None else None


def prepare(repo, base_sha, current, proposed, files, output, new_profile=False):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Expected OWNER/REPO")
    if new_profile:
        owner, name = repo.split("/")
        if base_sha is not None:
            raise ValueError("A new Profile has no base commit SHA")
        if owner.casefold() != name.casefold() or "README.md" not in files:
            raise ValueError("A new Profile requires OWNER/OWNER and a root README.md")
    elif not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise ValueError("Expected the reviewed 40-character base commit SHA")
    if len(set(files)) != len(files):
        raise ValueError("Duplicate file paths")
    entries, diff = [], []
    for name in files:
        before, after = file_bytes(current, name), file_bytes(proposed, name)
        if new_profile and before is not None:
            raise ValueError("A new Profile requires absent current files: " + name)
        if new_profile and name == "README.md" and not (after or b"").strip():
            raise ValueError("A new Profile requires a non-empty root README.md")
        if before == after:
            continue
        if after is None:
            raise ValueError("File deletion requires its own explicit review; not supported by this helper")
        if b"\0" in (before or b"") or b"\0" in after:
            raise ValueError("Binary files are not supported: " + name)
        # Refuse binary/invalid UTF-8; the helper is scoped to documentation.
        old_text = (before or b"").decode("utf-8")
        new_text = after.decode("utf-8")
        entries.append({"path": name, "beforeSha256": digest(before), "afterSha256": digest(after),
                        "beforeGitBlobSha": git_blob(before)})
        diff += list(difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                     fromfile="a/" + name if before is not None else "/dev/null", tofile="b/" + name))
        if old_text and not old_text.endswith("\n") or new_text and not new_text.endswith("\n"):
            diff.append("\n[Review note: original or proposed file has no final newline]\n")
    if not entries:
        raise ValueError("No changed files")
    diff_text = "".join(diff)
    plan = {
        "schemaVersion": "1.0", "repository": repo, "baseSha": base_sha,
        "action": "documentation_pr", "files": entries, "diffSha256": digest(diff_text.encode()),
        "workflow": ["create_branch", "commit_approved_files", "open_pull_request"],
        "requiresUserConfirmation": True,
        "excludedActions": ["merge", "comment", "close", "publish", "archive", "delete",
                            "rename", "visibility_change", "metadata_change"],
    }
    if new_profile:
        plan.update(action="new_profile_repository_then_documentation_pr",
                    expectedRepositoryState="absent", visibility="public")
        plan["workflow"] = ["verify_repository_absent", "create_public_profile_repository",
                            "read_real_base_sha"] + plan["workflow"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "changes.diff").write_text(diff_text, encoding="utf-8")
    return plan


def verify(plan_file, current, proposed):
    path = Path(plan_file)
    plan = json.loads(path.read_text())
    if digest((path.parent / "changes.diff").read_bytes()) != plan["diffSha256"]:
        raise ValueError("Diff changed after preparation; regenerate and review")
    for item in plan["files"]:
        if digest(file_bytes(current, item["path"])) != item["beforeSha256"]:
            raise ValueError("Current file changed: " + item["path"])
        if digest(file_bytes(proposed, item["path"])) != item["afterSha256"]:
            raise ValueError("Proposed file changed: " + item["path"])
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for cmd_name in ("plan", "verify"):
        cmd = commands.add_parser(cmd_name)
        cmd.add_argument("--current-dir", required=True)
        cmd.add_argument("--proposed-dir", required=True)
        if cmd_name == "plan":
            cmd.add_argument("--repo", required=True)
            base = cmd.add_mutually_exclusive_group(required=True)
            base.add_argument("--base-sha", help="Reviewed existing default-branch commit SHA")
            base.add_argument("--new-profile", action="store_true",
                              help="Plan an absent public OWNER/OWNER Profile; does not verify or create it")
            cmd.add_argument("--file", action="append", required=True)
            cmd.add_argument("--output", required=True)
        else:
            cmd.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = prepare(args.repo, args.base_sha, args.current_dir, args.proposed_dir,
                             args.file, args.output, new_profile=args.new_profile)
        else:
            result = verify(args.plan, args.current_dir, args.proposed_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, "prepare-change: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
