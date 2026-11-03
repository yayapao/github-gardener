"""Shared configuration, evidence and read-only gh transport. No third-party dependencies."""
import copy
import fnmatch
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2.0"
DEFAULT_CONFIG = {
    "owner": None, "include_private": False, "include_forks": False,
    "include_archived": False, "include": ["*"], "exclude": [],
    "audit_profile_repo": True, "max_repositories": 100, "max_pages": 5,
    "recent_runs": 30, "issue_stale_days": 30, "pr_stale_days": 14,
    "docs_stale_days": 365, "dormant_days": 180, "archive_candidate_days": 365,
    "repository_context": {},
}
LABELS = {"active": "活跃", "stable": "稳定维护", "needs_attention": "需关注",
          "dormant": "休眠", "suggested_archive": "建议归档", "unknown": "待判断"}


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def age(value, now):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0, (now - dt.replace(tzinfo=dt.tzinfo or timezone.utc)).days)
    except (ValueError, TypeError):
        return None


def merged_config(override=None):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(override or {})
    unknown = set(cfg) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError("Unknown config keys: " + ", ".join(sorted(unknown)))
    for field in ("include", "exclude"):
        if not isinstance(cfg[field], list) or not all(isinstance(x, str) for x in cfg[field]):
            raise ValueError(field + " must be an array of glob strings")
    for field in ("max_repositories", "max_pages", "recent_runs", "issue_stale_days",
                  "pr_stale_days", "docs_stale_days", "dormant_days", "archive_candidate_days"):
        if type(cfg[field]) is not int or cfg[field] < 1:
            raise ValueError(field + " must be a positive integer")
    if cfg["recent_runs"] > 100 or cfg["max_pages"] > 100:
        raise ValueError("recent_runs and max_pages must be <= 100")
    for field in ("include_private", "include_forks", "include_archived", "audit_profile_repo"):
        if type(cfg[field]) is not bool:
            raise ValueError(field + " must be a boolean")
    if not isinstance(cfg["repository_context"], dict):
        raise ValueError("repository_context must be an object")
    for context in cfg["repository_context"].values():
        if not isinstance(context, dict):
            raise ValueError("Each repository context must be an object")
        if context.get("maintenance_intent", "unknown") not in {"active", "stable", "paused", "retired", "unknown"}:
            raise ValueError("Invalid maintenance_intent")
        if context.get("project_type", "code") not in {"code", "docs", "profile", "template"}:
            raise ValueError("Invalid project_type")
        if context.get("user_interest", "unknown") not in {"high", "medium", "low", "unknown"}:
            raise ValueError("Invalid user_interest")
        if type(context.get("showcase_priority", 0)) is not int:
            raise ValueError("showcase_priority must be an integer")
        for key in ("demand", "differentiation", "feasibility"):
            entries = context.get(key, [])
            if not isinstance(entries, list):
                raise ValueError(key + " must be an array")
            for entry in entries:
                if not isinstance(entry, dict) or not entry.get("summary") or not entry.get("source"):
                    raise ValueError(key + " entries require summary and source")
    if cfg["owner"] and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", cfg["owner"]):
        raise ValueError("Invalid GitHub owner")
    return cfg


def load_config(path=None):
    return merged_config(json.loads(Path(path).expanduser().read_text()) if path else {})


def matches(repo, patterns):
    names = (repo.get("name", ""), repo.get("full_name", repo.get("nameWithOwner", "")))
    return any(fnmatch.fnmatchcase(n.casefold(), p.casefold()) for n in names for p in patterns)


def select_repositories(repos, cfg):
    selected = []
    for repo in repos:
        if (repo.get("fork", repo.get("isFork", False)) and not cfg["include_forks"]
                or repo.get("archived", repo.get("isArchived", False)) and not cfg["include_archived"]
                or (repo.get("private") or repo.get("visibility", "public") != "public")
                and not cfg["include_private"]):
            continue
        if matches(repo, cfg["include"] or ["*"]) and not matches(repo, cfg["exclude"]):
            selected.append(repo)
    return selected


class GhError(RuntimeError):
    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.reason, self.status = reason, status


class GhClient:
    """Only REST GET and GraphQL query operations are exposed."""
    def __init__(self):
        self.rate_limited = False

    def _run(self, args):
        if self.rate_limited:
            raise GhError("rate_limited")
        try:
            result = subprocess.run(["gh", "api"] + args, capture_output=True,
                                    text=True, timeout=60, check=False)
        except FileNotFoundError as exc:
            raise GhError("gh_not_installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise GhError("timeout") from exc
        if result.returncode:
            # Keep diagnostics, but never persist response bodies or possible credentials.
            msg = result.stderr.lower()
            found = re.search(r"http\s+(\d{3})", msg)
            status = int(found.group(1)) if found else None
            self.rate_limited = "rate limit" in msg or status == 429
            reason = ("rate_limited" if self.rate_limited else
                      "not_found_or_hidden" if status == 404 else
                      "forbidden" if status in (401, 403) else "api_error")
            raise GhError(reason, status)
        try:
            return json.loads(result.stdout or "null")
        except ValueError as exc:
            raise GhError("invalid_json") from exc

    def get(self, endpoint):
        return self._run(["--method", "GET", "-H", "Accept: application/vnd.github+json", endpoint])

    def graphql(self, query, variables):
        if not query.lstrip().startswith("query"):
            raise GhError("read_only_query_required")
        args = ["graphql", "-f", "query=" + query]
        for key, value in variables.items():
            if value is not None:
                args += ["-f", key + "=" + str(value)]
        data = self._run(args)
        if not isinstance(data, dict) or data.get("errors") or not data.get("data"):
            raise GhError("graphql_incomplete")
        return data["data"]


def observed(client, endpoint):
    record = {"endpoint": endpoint, "fetchedAt": now_iso(), "status": "ok"}
    try:
        data = client.get(endpoint)
        if data is None or data == {}:
            record["status"] = "unknown"
            record["reason"] = "empty_or_pending_response"
        return {"data": data, **record}
    except GhError as exc:
        return {"data": None, **record, "status": "unknown",
                "reason": exc.reason, "httpStatus": exc.status}


def paged(client, endpoint, cfg, array_key=None):
    items, sources, complete = [], [], False
    for page in range(1, cfg["max_pages"] + 1):
        separator = "&" if "?" in endpoint else "?"
        result = observed(client, endpoint + separator + "per_page=100&page=" + str(page))
        payload = result.pop("data")
        sources.append(result)
        batch = payload.get(array_key) if isinstance(payload, dict) and array_key else payload
        if result["status"] != "ok" or not isinstance(batch, list):
            break
        items.extend(batch)
        if len(batch) < 100:
            complete = True
            break
    return {"items": items, "complete": complete, "available": bool(
        sources and sources[0]["status"] == "ok"), "sources": sources}
