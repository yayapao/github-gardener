"""Evidence collection through gh. Repository content is data, never executable."""
import base64
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from gardener_common import (VERSION, GhClient, GhError, age, now_iso,
                             observed, paged, select_repositories)

MANIFESTS = {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
             "pyproject.toml", "requirements.txt", "poetry.lock", "Cargo.toml",
             "Cargo.lock", "go.mod", "go.sum", "pom.xml", "build.gradle",
             "Gemfile", "Gemfile.lock", "composer.json", "composer.lock", "pubspec.yaml"}
MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}


def excerpt(content):
    content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
    return next((line.strip()[:360] for line in content.splitlines()
                 if line.strip() and not line.startswith(("#", "[", "!", "<", chr(96)))), "")


def decode_file(data):
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return ""
    try:
        return base64.b64decode(data.get("content", ""), validate=False).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def collect_open_work(client, owner, name, cfg):
    output = {}
    for kind in ("issues", "pullRequests"):
        fields = ("isDraft reviewDecision reviews(last: 20) { nodes { state createdAt "
                  "authorAssociation } pageInfo { hasPreviousPage } }" if kind == "pullRequests" else "")
        query = """query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            %s(states: OPEN, first: 100, after: $cursor,
              orderBy: {field: CREATED_AT, direction: ASC}) {
              totalCount pageInfo { hasNextPage endCursor }
              nodes { number title url createdAt updatedAt authorAssociation %s
                comments(first: 100) {
                  totalCount pageInfo { hasNextPage }
                  nodes { authorAssociation createdAt }
                }
              }
            }
          }
        }""" % (kind, fields)
        items, cursor, sources, total, complete = [], None, [], None, False
        for _ in range(cfg["max_pages"]):
            source = {"endpoint": "graphql:" + kind, "fetchedAt": now_iso(), "status": "ok"}
            try:
                data = client.graphql(query, {"owner": owner, "name": name, "cursor": cursor})
                connection = (data.get("repository") or {}).get(kind)
                if not isinstance(connection, dict):
                    raise GhError("missing_connection")
            except GhError as exc:
                sources.append({**source, "status": "unknown", "reason": exc.reason})
                break
            sources.append(source)
            total = connection.get("totalCount")
            for node in connection.get("nodes") or []:
                comments = node.get("comments") or {}
                replies = [c.get("createdAt") for c in comments.get("nodes") or []
                           if c.get("authorAssociation") in MAINTAINERS and c.get("createdAt")]
                count = comments.get("totalCount")
                comments_complete = not comments.get("pageInfo", {}).get("hasNextPage", True)
                response = ("responded" if replies else "unanswered" if count == 0 else
                            "no_maintainer_response" if comments_complete else "unknown")
                item = {key: node.get(key) for key in
                        ("number", "title", "url", "createdAt", "updatedAt", "authorAssociation",
                         "isDraft", "reviewDecision")}
                item.update(comments=count, responseStatus=response,
                            lastMaintainerResponseAt=max(replies) if replies else None)
                if kind == "pullRequests":
                    reviews = node.get("reviews") or {}
                    review_nodes = reviews.get("nodes") or []
                    decision = node.get("reviewDecision")
                    approved = any(r.get("state") == "APPROVED" for r in review_nodes)
                    changes = any(r.get("state") == "CHANGES_REQUESTED" for r in review_nodes)
                    item["awaitingReview"] = (not node.get("isDraft")
                        and (decision == "REVIEW_REQUIRED" or not review_nodes)
                        and decision not in {"APPROVED", "CHANGES_REQUESTED"}
                        and not approved and not changes)
                    maint_reviews = [r["createdAt"] for r in review_nodes
                                     if r.get("authorAssociation") in MAINTAINERS and r.get("createdAt")]
                    if maint_reviews:
                        item["lastMaintainerResponseAt"] = max(maint_reviews + replies)
                items.append(item)
            info = connection.get("pageInfo") or {}
            if info.get("hasNextPage") is False:
                complete = True
                break
            next_cursor = info.get("endCursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        output[kind] = {"available": total is not None, "complete": complete,
                        "openCount": total, "items": items, "sources": sources}
    return output


def security_alerts(client, prefix, kind, cfg):
    paths = {
        "dependabot": "dependabot/alerts?state=open",
        "secretScanning": "secret-scanning/alerts?state=open",
        "codeScanning": "code-scanning/alerts?state=open",
    }
    result = paged(client, prefix + "/" + paths[kind], cfg)
    counts, links = {}, []
    for item in result["items"]:
        if kind == "secretScanning":
            severity = "critical"
        elif kind == "dependabot":
            severity = (item.get("security_advisory") or {}).get("severity") or "unknown"
        else:
            rule = item.get("rule") or {}
            severity = rule.get("security_severity_level") or rule.get("severity") or "unknown"
        counts[severity] = counts.get(severity, 0) + 1
        if item.get("html_url"):
            links.append(item["html_url"])
    # Secret scanning response includes the actual secret: never persist raw items.
    return {
        "status": "findings" if result["items"] else "no_visible_alerts" if result["complete"] else "unknown",
        "complete": result["complete"], "severityCounts": counts,
        "alertCount": len(result["items"]), "urls": links[:20], "sources": result["sources"],
    }


def collect_repo(client, raw, cfg, owner):
    full_name = raw["full_name"]
    prefix = "repos/" + full_name
    detail = observed(client, prefix)
    repo = detail["data"] if isinstance(detail["data"], dict) else raw
    branch = repo.get("default_branch") or "main"
    sources = [dict((k, v) for k, v in detail.items() if k != "data")]
    readme_result = observed(client, prefix + "/readme")
    readme_data = readme_result.pop("data")
    sources.append(readme_result)
    text = decode_file(readme_data)
    readme_path = (readme_data or {}).get("path", "README.md")
    readme_known = readme_result["status"] == "ok"
    tree_result = observed(client, prefix + "/git/trees/" + quote(branch, safe="") + "?recursive=1")
    tree = tree_result.pop("data")
    sources.append(tree_result)
    tree_complete = isinstance(tree, dict) and tree_result["status"] == "ok" and not tree.get("truncated", True)
    paths = [x.get("path", "") for x in (tree or {}).get("tree", [])] if isinstance(tree, dict) else []
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    commits = paged(client, prefix + "/commits?" + urlencode({"sha": branch, "since": since}), cfg)
    commit_dates = [((x.get("commit") or {}).get("committer") or {}).get("date") for x in commits["items"]]
    latest = observed(client, prefix + "/commits?" + urlencode({"sha": branch, "per_page": 1}))
    latest_data = latest.pop("data")
    sources.extend(commits["sources"] + [latest])
    latest_date = (((latest_data[0].get("commit") or {}).get("committer") or {}).get("date")
                   if isinstance(latest_data, list) and latest_data else None)
    rm_history = observed(client, prefix + "/commits?" + urlencode(
        {"sha": branch, "path": readme_path, "per_page": 1}))
    history = rm_history.pop("data")
    sources.append(rm_history)
    modified = (((history[0].get("commit") or {}).get("committer") or {}).get("date")
                if isinstance(history, list) and history else None)
    releases = observed(client, prefix + "/releases?per_page=10")
    release_data = releases.pop("data")
    sources.append(releases)
    public_releases = [x for x in release_data or [] if isinstance(x, dict) and not x.get("draft")]
    release_dates = [x["published_at"] for x in public_releases if x.get("published_at")]
    runs_result = observed(client, prefix + "/actions/runs?" + urlencode(
        {"branch": branch, "per_page": cfg["recent_runs"]}))
    runs = runs_result.pop("data")
    sources.append(runs_result)
    current_workflows = {}
    for run in (runs or {}).get("workflow_runs", []) if isinstance(runs, dict) else []:
        key = str(run.get("workflow_id") or run.get("path") or run.get("name"))
        if key not in current_workflows:
            current_workflows[key] = {k: run.get(k) for k in
                                      ("name", "conclusion", "status", "html_url", "created_at")}
    failed = [r for r in current_workflows.values()
              if r["conclusion"] in {"failure", "timed_out", "startup_failure", "action_required"}]
    status = ("failing" if failed else "passing" if current_workflows
              and all(r["conclusion"] == "success" for r in current_workflows.values()) else "unknown")
    work = collect_open_work(client, owner, repo.get("name", raw["name"]), cfg)
    permissions = observed(client, prefix + "/actions/permissions/workflow")
    permissions_data = permissions.pop("data")
    security = {kind: security_alerts(client, prefix, kind, cfg)
                for kind in ("dependabot", "secretScanning", "codeScanning")}
    security["workflowPermissions"] = {
        "status": "observed" if permissions["status"] == "ok" else "unknown",
        "defaultWorkflowPermissions": (permissions_data or {}).get("default_workflow_permissions"),
        "sources": [permissions],
    }
    security["workflowContentReview"] = {"status": "not_checked",
        "reason": "Workflow logic and action pinning require agent review of the listed YAML files."}
    sbom = observed(client, prefix + "/dependency-graph/sbom")
    sbom_data = sbom.pop("data")
    sources.append(sbom)
    community = observed(client, prefix + "/community/profile")
    community_data = community.pop("data")
    sources.append(community)
    upper = {x.upper() for x in paths}
    security_policy = any(x in upper for x in ("SECURITY.MD", ".GITHUB/SECURITY.MD", "DOCS/SECURITY.MD"))
    community_files = (community_data or {}).get("files") or {}
    file_patterns = {
        "contributing": ("CONTRIBUTING",), "codeOfConduct": ("CODE_OF_CONDUCT",),
        "issueTemplate": ("ISSUE_TEMPLATE",), "pullRequestTemplate": ("PULL_REQUEST_TEMPLATE",),
    }
    api_keys = {"contributing": "contributing", "codeOfConduct": "code_of_conduct",
                "issueTemplate": "issue_template", "pullRequestTemplate": "pull_request_template"}
    community_presence = {}
    for key, patterns in file_patterns.items():
        found = bool(community_files.get(api_keys[key])) or any(
            any(part.split(".")[0] in patterns for part in path.split("/")) for path in upper)
        community_presence[key] = found if tree_complete or community["status"] == "ok" else None
    sbom_packages = ((sbom_data or {}).get("sbom") or {}).get("packages", [])
    now = datetime.now(timezone.utc)
    return {
        "nameWithOwner": full_name, "name": repo.get("name"), "description": repo.get("description"),
        "homepageUrl": repo.get("homepage"), "topics": repo.get("topics") or [],
        "url": repo.get("html_url") or "https://github.com/" + full_name,
        "visibility": repo.get("visibility", "private" if repo.get("private") else "public"),
        "isFork": bool(repo.get("fork")), "isArchived": bool(repo.get("archived")),
        "defaultBranch": branch, "primaryLanguage": repo.get("language"),
        "stars": repo.get("stargazers_count"), "forks": repo.get("forks_count"),
        "license": {"present": bool(repo.get("license")),
                    "spdxId": (repo.get("license") or {}).get("spdx_id")},
        "community": {"available": community["status"] == "ok",
                      "healthPercentage": (community_data or {}).get("health_percentage"),
                      "files": community_presence,
                      "securityPolicy": security_policy if tree_complete else None},
        "readme": {"present": True if readme_known else None, "content": text[:60000],
                   "contentTruncated": len(text) > 60000, "path": readme_path,
                   "sha": (readme_data or {}).get("sha"), "characters": len(text),
                   "excerpt": excerpt(text), "lastModifiedAt": modified,
                   "checks": {k: bool(re.search(v, text, re.I)) for k, v in {
                       "installation": r"install|安装|快速开始|getting started",
                       "usage": r"usage|example|用法|示例|使用",
                       "testing": r"test|测试", "license": r"licen[cs]e|许可证",
                   }.items()}},
        "activity": {"latestCommitAt": latest_date,
                     "commits30d": sum(1 for d in commit_dates if age(d, now) is not None and age(d, now) <= 30),
                     "commits90d": len(commit_dates), "complete": commits["complete"],
                     "sources": commits["sources"]},
        "releases": {"available": releases["status"] == "ok",
                     "latestAt": max(release_dates) if release_dates else None,
                     "recentCount": len(public_releases), "sampleLimit": 10},
        **work,
        "ci": {"available": runs_result["status"] == "ok", "status": status,
               "sampleLimit": cfg["recent_runs"], "branch": branch,
               "currentWorkflows": list(current_workflows.values()), "failedWorkflows": failed,
               "note": "Latest run per workflow within the bounded default-branch sample; older workflows may be absent."},
        "dependencies": {"manifests": [p for p in paths if p.rsplit("/", 1)[-1] in MANIFESTS][:100],
                         "inventoryComplete": tree_complete, "sbomAvailable": sbom["status"] == "ok",
                         "packageCount": len(sbom_packages),
                         "packageSample": [{k: item.get(k) for k in ("name", "versionInfo", "licenseConcluded")}
                                           for item in sbom_packages[:50]],
                         "packageSampleLimit": 50,
                         "outdatedVersions": "not_checked"},
        "workflowFiles": [p for p in paths if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))],
        "security": security, "sources": sources,
    }


def collect_snapshot(cfg, client=None):
    client = client or GhClient()
    owner = cfg["owner"]
    if not owner or cfg["include_private"]:
        login = client.get("user").get("login")
        owner = owner or login
        if not owner or cfg["include_private"] and owner.casefold() != str(login).casefold():
            raise ValueError("Private scope requires --owner to match the authenticated user")
    endpoint = ("user/repos?affiliation=owner&visibility=all&sort=pushed" if cfg["include_private"]
                else "users/" + owner + "/repos?type=owner&sort=pushed")
    listing = paged(client, endpoint, cfg)
    if not listing["available"]:
        raise GhError("Repository listing unavailable; no audit produced")
    owned = [r for r in listing["items"] if
             str((r.get("owner") or {}).get("login", "")).casefold() == owner.casefold()]
    selected = select_repositories(owned, cfg)
    capped = len(selected) > cfg["max_repositories"]
    selected = selected[:cfg["max_repositories"]]
    return {
        "schemaVersion": VERSION, "generatedAt": now_iso(), "owner": owner,
        "scope": {"include": cfg["include"], "exclude": cfg["exclude"],
                  "includePrivate": cfg["include_private"], "includeForks": cfg["include_forks"],
                  "includeArchived": cfg["include_archived"],
                  "listingComplete": listing["complete"], "repositoryLimitReached": capped,
                  "observedCount": len(owned), "selectedCount": len(selected)},
        "sources": listing["sources"],
        "repositories": [collect_repo(client, r, cfg, owner) for r in selected],
    }
