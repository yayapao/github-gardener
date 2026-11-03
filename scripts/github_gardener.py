#!/usr/bin/env python3
"""Read-only GitHub gardener CLI. Local reports only; no remote mutation command."""
import argparse
import json
import sys
from pathlib import Path

from gardener_common import VERSION, GhError, load_config, merged_config
from gardener_collect import collect_snapshot
from gardener_analysis import aggregate_report
from gardener_report import render_markdown, write_outputs


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--version", action="version", version="github-gardener " + VERSION)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("scan", "collect", "analyze"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config")
        cmd.add_argument("--owner")
        cmd.add_argument("--include", action="append")
        cmd.add_argument("--exclude", action="append")
        cmd.add_argument("--max-repositories", type=int)
        for flag in ("private", "forks", "archived"):
            cmd.add_argument("--include-" + flag, action="store_true", default=None)
        cmd.add_argument("--output")
        if name != "collect":
            cmd.add_argument("--snapshot", required=name == "analyze")
            cmd.add_argument("--format", choices=["markdown", "json", "both"], default="markdown")
        if name == "scan":
            cmd.add_argument("--snapshot-out")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        for key in ("owner", "include", "exclude", "max_repositories",
                    "include_private", "include_forks", "include_archived"):
            if getattr(args, key) is not None:
                cfg[key] = getattr(args, key)
        cfg = merged_config(cfg)
        snapshot_path = getattr(args, "snapshot", None)
        snapshot = (json.loads(Path(snapshot_path).expanduser().read_text())
                    if snapshot_path else collect_snapshot(cfg))
        snapshot_out = args.output if args.command == "collect" else getattr(args, "snapshot_out", None)
        if snapshot_out:
            target = Path(snapshot_out).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        if args.command == "collect":
            if not args.output:
                print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        else:
            write_outputs(aggregate_report(snapshot, cfg), args.output, args.format)
        return 0
    except (ValueError, OSError, GhError) as exc:
        print("github-gardener: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
