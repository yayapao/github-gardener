#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  printf 'Usage: %s OWNER [OUTPUT.json]\n' "$0" >&2
  exit 2
fi

owner="$1"
if [[ ! "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
  printf 'Expected a GitHub login, not a URL or path.\n' >&2
  exit 2
fi
output=""
if [[ $# -eq 2 ]]; then
  output="$2"
fi

if ! command -v gh >/dev/null 2>&1; then
  printf 'gh is required. Install GitHub CLI first.\n' >&2
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq is required. Install jq first.\n' >&2
  exit 2
fi

if ! gh auth status >/dev/null 2>&1; then
  printf 'GitHub CLI is not authenticated. Run gh auth login.\n' >&2
  exit 2
fi

query='
  [.[][]]
  | map(select((.fork | not) and (.archived | not) and (.private | not)))
  | map({
      nameWithOwner: .full_name,
      description,
      homepage: .homepage,
      topics,
      license: (.license.spdx_id // null),
      language,
      stars: .stargazers_count,
      pushedAt: .pushed_at,
      defaultBranch: .default_branch
    })
'

if [[ -n "$output" ]]; then
  gh api --method GET --paginate --slurp \
    -H 'Accept: application/vnd.github+json' \
    "users/$owner/repos?type=owner&sort=pushed&direction=desc&per_page=100" \
    | jq "$query" > "$output"
  printf 'Wrote %s\n' "$output"
else
  gh api --method GET --paginate --slurp \
    -H 'Accept: application/vnd.github+json' \
    "users/$owner/repos?type=owner&sort=pushed&direction=desc&per_page=100" \
    | jq "$query"
fi
