"""All tests are offline; subprocess gh transport is always mocked."""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gardener_common import GhClient, GhError, merged_config, paged
from gardener_collect import collect_snapshot, collect_repo, collect_open_work, security_alerts
from gardener_analysis import aggregate_report
from gardener_report import render_markdown
from prepare_change import prepare, verify
from install_skill import install
from package_skill import package


def snapshot():
    raw = json.loads((ROOT / "tests/fixtures/snapshot.json").read_text())
    # Explicit completeness/security provenance makes this a v2 scenario.
    raw["schemaVersion"] = "2.0"
    raw["scope"]["exclude"] = []
    for repo in raw["repositories"]:
        for key in ("issues", "pullRequests"):
            repo[key]["complete"] = True
        repo["activity"]["complete"] = True
        old = repo["dependencies"]["dependabot"]
        repo["security"] = {
            "dependabot": {"status": "findings" if old["status"] == "open" else "no_visible_alerts",
                           "severityCounts": old["severityCounts"], "complete": True},
            "secretScanning": {"status": "no_visible_alerts", "complete": True},
            "codeScanning": {"status": "no_visible_alerts", "complete": True},
            "workflowPermissions": {"status": "observed", "defaultWorkflowPermissions": "read"},
            "workflowContentReview": {"status": "not_checked"},
        }
    return raw


class FakeGh:
    def __init__(self):
        self.calls = []

    def graphql(self, query, variables):
        kind = "pullRequests" if "pullRequests(" in query else "issues"
        return {"repository": {kind: {
            "totalCount": 0, "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}}

    def get(self, endpoint):
        self.calls.append(endpoint)
        repo = {"full_name": "me/tool", "name": "tool", "owner": {"login": "me"},
                "description": "A useful tool", "default_branch": "feature/docs",
                "visibility": "public", "html_url": "https://github.com/me/tool"}
        if endpoint == "user":
            return {"login": "me"}
        if endpoint.startswith("users/me/repos?"):
            return [repo, {**repo, "name": "fork", "full_name": "me/fork", "fork": True}]
        if endpoint == "repos/me/tool":
            return repo
        if endpoint.endswith("/readme"):
            return {"encoding": "base64", "path": "docs/README.md", "sha": "f" * 40,
                    "content": base64.b64encode(b"# Tool\n\nA useful tool.\n\nInstallation and usage.").decode()}
        if "/git/trees/" in endpoint:
            return {"truncated": False, "tree": [{"path": ".github/SECURITY.md"}, {"path": "pyproject.toml"}]}
        if "/commits?" in endpoint:
            return [{"commit": {"committer": {"date": "2026-10-31T00:00:00Z"}}}]
        if "/releases?" in endpoint:
            return [{"draft": True, "published_at": "2026-11-01T00:00:00Z"},
                    {"draft": False, "published_at": "2026-10-01T00:00:00Z"}]
        if "/actions/runs?" in endpoint:
            return {"workflow_runs": [
                {"workflow_id": 1, "conclusion": "success", "status": "completed", "html_url": "https://example.com/ci-1"},
                {"workflow_id": 2, "conclusion": "failure", "status": "completed", "html_url": "https://example.com/ci-2"},
                {"workflow_id": 1, "conclusion": "failure", "status": "completed", "html_url": "https://example.com/old"},
            ]}
        if endpoint.endswith("/actions/permissions/workflow"):
            return {"default_workflow_permissions": "read"}
        if "/alerts?" in endpoint:
            return []
        if endpoint.endswith("/dependency-graph/sbom"):
            return {"sbom": {"packages": [{"name": "example"}]}}
        if endpoint.endswith("/community/profile"):
            return {"health_percentage": 80}
        raise AssertionError("Unexpected fake endpoint " + endpoint)


class AnalysisTests(unittest.TestCase):
    def result(self, data=None, cfg=None):
        return aggregate_report(data or snapshot(), cfg)

    def repo(self, name, data=None, cfg=None):
        return next(r for r in self.result(data, cfg)["repositories"] if r["name"] == name)

    def test_activity_and_health_are_independent(self):
        data = snapshot()
        data["repositories"][0]["ci"]["status"] = "failing"
        a = self.repo("active-lib", data)["analysis"]
        self.assertEqual(a["maintenanceStatus"], "active")
        self.assertEqual(a["category"], "needs_attention")
        self.assertTrue(a["needsAttention"])

    def test_quiet_project_is_not_archive_candidate(self):
        a = self.repo("archive-me")["analysis"]
        self.assertEqual(a["maintenanceStatus"], "dormant")
        self.assertFalse(a["archiveCandidate"])
        self.assertEqual(a["archiveAssessment"]["status"], "insufficient_evidence")

    def test_retirement_needs_evidence_and_references_review(self):
        ctx = {"maintenance_intent": "retired", "archive_reason": "Superseded by another maintained tool",
               "archive_evidence_source": "https://example.com/retirement"}
        cfg = {"repository_context": {"fixture-user/archive-me": ctx}}
        self.assertFalse(self.repo("archive-me", cfg=cfg)["analysis"]["archiveCandidate"])
        ctx["archive_review"] = {"external_usage_reviewed": True, "release_assets_reviewed": True, "migration_ready": True}
        self.assertTrue(self.repo("archive-me", cfg=cfg)["analysis"]["archiveCandidate"])
        data = snapshot()
        data["repositories"][4]["pullRequests"]["available"] = False
        self.assertFalse(self.repo("archive-me", data, cfg)["analysis"]["archiveCandidate"])

    def test_stable_owner_intent_preserves_mature_tool(self):
        cfg = {"repository_context": {"fixture-user/archive-me": {"maintenance_intent": "stable"}}}
        self.assertEqual(self.repo("archive-me", cfg=cfg)["analysis"]["maintenanceStatus"], "stable")

    def test_unknown_api_is_not_empty_and_drops_confidence(self):
        data = snapshot()
        repo = data["repositories"][0]
        normal = self.repo("active-lib")["analysis"]
        for key in ("issues", "pullRequests"):
            repo[key] = {"available": False, "complete": False, "openCount": None}
        repo["security"] = {"dependabot": {"status": "unknown", "complete": False}}
        a = self.repo("active-lib", data)["analysis"]
        self.assertLess(a["confidence"], normal["confidence"])
        self.assertLess(a["health"]["coverage"], 1)
        self.assertEqual(a["health"]["state"], "incomplete")

    def test_profile_does_not_require_license_ci_or_install(self):
        data = snapshot()
        repo = data["repositories"][-1]
        repo["license"]["present"] = False
        repo["readme"]["characters"] = 20
        a = self.repo("fixture-user", data)["analysis"]
        self.assertEqual(a["projectType"], "profile")
        self.assertFalse(any(c["dimension"] in {"license", "ci"} for c in a["health"]["components"]))
        self.assertFalse(a["risks"])

    def test_stars_do_not_establish_development_value(self):
        data = snapshot()
        data["repositories"][0]["stars"] = 1000000
        a = self.repo("active-lib", data)["analysis"]
        self.assertEqual(a["developmentValue"]["status"], "insufficient_evidence")
        ctx = {"user_interest": "high", "next_milestone": "Ship one tested integration in two weeks"}
        for key in ("demand", "differentiation", "feasibility"):
            ctx[key] = [{"summary": "Documented " + key, "source": "https://example.com/" + key}]
        a = self.repo("active-lib", cfg={"repository_context": {"fixture-user/active-lib": ctx}})["analysis"]
        self.assertEqual(a["developmentValue"]["status"], "continue_candidate")

    def test_draft_and_changes_requested_prs_are_not_awaiting_review(self):
        data = snapshot()
        pulls = data["repositories"][2]["pullRequests"]["items"]
        pulls[0]["reviewDecision"] = "CHANGES_REQUESTED"
        a = self.repo("neglected-app", data)["analysis"]
        self.assertEqual(a["stalePullRequests"], [])

    def test_excludes_apply_to_offline_analysis_and_profile(self):
        report = self.result(cfg={"include": ["active-*"], "exclude": ["*user/active-lib"]})
        self.assertEqual(report["repositories"], [])
        self.assertEqual(report["profileAudit"]["status"], "outside_scope")

    def test_profile_never_discloses_private_projects_or_audit_scores(self):
        data = snapshot()
        data["repositories"][0]["visibility"] = "private"
        report = self.result(data, {"include_private": True})
        draft = report["profileAudit"]["readmeDraft"]
        self.assertNotIn("active-lib", draft)
        self.assertNotIn("健康分", draft)
        self.assertNotIn("neglected-app", draft)
        self.assertIn("stable-tool", draft)

    def test_private_profile_content_is_not_reused_in_public_draft(self):
        data = snapshot()
        data["repositories"][-1]["visibility"] = "private"
        data["repositories"][-1]["readme"]["excerpt"] = "PRIVATE_PROFILE_SENTINEL"
        report = self.result(data, {"include_private": True})
        self.assertNotIn("PRIVATE_PROFILE_SENTINEL", report["profileAudit"]["readmeDraft"])
        self.assertEqual(report["profileAudit"]["status"], "not_public")

    def test_document_age_only_proposes_validation(self):
        repo = self.repo("archive-me")
        self.assertFalse(any("过期" in r["title"] for r in repo["analysis"]["risks"]))
        self.assertTrue(any("复核" in w["action"] for w in repo["analysis"]["quickWins"]))

    def test_v1_remains_readable_but_not_treated_as_complete(self):
        raw = json.loads((ROOT / "tests/fixtures/snapshot.json").read_text())
        report = aggregate_report(raw)
        self.assertFalse(report["summary"]["archiveCandidates"])
        self.assertTrue(all(r["analysis"]["health"]["coverage"] < 1 for r in report["repositories"]))

    def test_markdown_and_plan_reference_real_risks(self):
        report = self.result()
        text = render_markdown(report)
        self.assertIn("fixture-user/neglected-app", text)
        self.assertIn("secretScanning", text)
        self.assertTrue(all(p["repository"] == "fixture-user/neglected-app"
                            for p in report["thirtyDayPlan"] if p["day"] == 1))

    def test_shipped_v2_scenario_and_context_cover_all_five_decisions(self):
        data = json.loads((ROOT / "tests/fixtures/snapshot-v2.json").read_text())
        cfg = json.loads((ROOT / "tests/fixtures/context.json").read_text())
        report = aggregate_report(data, cfg)
        self.assertTrue(all(report["summary"]["categoryCounts"][name] == 1
                            for name in ("active", "stable", "needs_attention", "dormant", "suggested_archive")))
        self.assertEqual(report["summary"]["archiveCandidates"], ["fixture-user/archive-me"])
        self.assertEqual(report["repositories"][0]["analysis"]["developmentValue"]["status"], "continue_candidate")

    def test_profile_can_be_explicitly_skipped(self):
        self.assertEqual(self.result(cfg={"audit_profile_repo": False})["profileAudit"]["status"], "skipped")

    def test_invalid_context_and_owner_fail_cleanly(self):
        with self.assertRaises(ValueError):
            merged_config({"repository_context": {"fixture-user/tool": {"showcase_priority": "highest"}}})
        data = snapshot()
        data["repositories"][0]["nameWithOwner"] = "someone-else/tool"
        with self.assertRaises(ValueError):
            self.result(data)


class CollectorTests(unittest.TestCase):
    def test_collector_reads_branch_readme_real_dates_and_all_workflows(self):
        client = FakeGh()
        result = collect_snapshot(merged_config({"owner": "me"}), client)
        self.assertEqual(len(result["repositories"]), 1)
        repo = result["repositories"][0]
        self.assertEqual(repo["ci"]["status"], "failing")
        self.assertEqual(len(repo["ci"]["failedWorkflows"]), 1)
        self.assertEqual(repo["releases"]["latestAt"], "2026-10-01T00:00:00Z")
        self.assertTrue(repo["community"]["securityPolicy"])
        self.assertTrue(any("path=docs%2FREADME.md" in x for x in client.calls))
        self.assertTrue(any("trees/feature%2Fdocs" in x for x in client.calls))
        self.assertTrue(all(s.get("fetchedAt") for s in repo["sources"]))

    def test_collection_never_fetches_excluded_or_out_of_scope_profile(self):
        client = FakeGh()
        report = collect_snapshot(merged_config({"owner": "me", "exclude": ["tool"]}), client)
        self.assertEqual(report["repositories"], [])
        self.assertTrue(all(path.startswith("users/me/repos?") for path in client.calls))

    def test_private_owner_mismatch_stops_before_listing(self):
        client = FakeGh()
        with self.assertRaises(ValueError):
            collect_snapshot(merged_config({"owner": "someone-else", "include_private": True}), client)
        self.assertEqual(client.calls, ["user"])

    def test_partial_pagination_does_not_claim_zero(self):
        class Partial(FakeGh):
            def get(self, endpoint):
                if endpoint.endswith("&page=1"):
                    return [{"number": n} for n in range(100)]
                raise GhError("forbidden", 403)
        result = paged(Partial(), "repos/me/tool/dependabot/alerts?state=open", merged_config())
        self.assertEqual(len(result["items"]), 100)
        self.assertFalse(result["complete"])
        self.assertEqual(result["sources"][-1]["reason"], "forbidden")

    def test_secret_response_never_persists_secret(self):
        marker = "FIXTURE_SECRET_DO_NOT_PERSIST"
        class Secrets(FakeGh):
            def get(self, endpoint):
                return [{"secret": marker, "html_url": "https://example.com/alert"}]
        result = security_alerts(Secrets(), "repos/me/tool", "secretScanning", merged_config())
        self.assertNotIn(marker, json.dumps(result))
        self.assertEqual(result["severityCounts"]["critical"], 1)

    def test_graphql_counts_maintainer_reply_and_paginated_issues(self):
        class Work(FakeGh):
            def graphql(self, query, variables):
                kind = "pullRequests" if "pullRequests(" in query else "issues"
                more = kind == "issues" and variables["cursor"] is None
                return {"repository": {kind: {
                    "totalCount": 2 if kind == "issues" else 0,
                    "pageInfo": {"hasNextPage": more, "endCursor": "cursor-2" if more else None},
                    "nodes": [{
                        "number": 1 if more else 2,
                        "title": "A question", "createdAt": "2025-01-01T00:00:00Z",
                        "comments": {"totalCount": 1,
                                     "pageInfo": {"hasNextPage": False},
                                     "nodes": [{"authorAssociation": "OWNER" if more else "NONE",
                                                "createdAt": "2026-10-20T00:00:00Z"}]},
                    }] if kind == "issues" else [],
                }}}
        result = collect_open_work(Work(), "me", "tool", merged_config())
        self.assertTrue(result["issues"]["complete"])
        self.assertEqual([x["responseStatus"] for x in result["issues"]["items"]],
                         ["responded", "no_maintainer_response"])

    def test_graphql_failure_is_unknown(self):
        class Failed(FakeGh):
            def graphql(self, query, variables):
                raise GhError("graphql_incomplete")
        result = collect_open_work(Failed(), "me", "tool", merged_config())
        self.assertIsNone(result["issues"]["openCount"])
        self.assertFalse(result["issues"]["complete"])

    def test_transport_builds_get_and_rejects_graphql_mutations(self):
        with patch("gardener_common.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout='{"ok": true}', stderr="")
            client = GhClient()
            client.get("repos/me/tool")
            args = run.call_args.args[0]
            self.assertEqual(args[:5], ["gh", "api", "--method", "GET", "-H"])
            with self.assertRaises(GhError):
                client.graphql("mutation { deleteRepository }", {})
            self.assertEqual(run.call_count, 1)

    def test_rate_limit_stops_followup_requests(self):
        with patch("gardener_common.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="rate limit exceeded (HTTP 403)")
            client = GhClient()
            for _ in range(2):
                with self.assertRaises(GhError):
                    client.get("repos/me/tool")
            self.assertEqual(run.call_count, 1)


class ChangeAndCliTests(unittest.TestCase):
    def test_jq_inventory_pipeline_uses_only_mock_gh(self):
        import shutil
        if not shutil.which("jq"):
            self.skipTest("jq is not installed")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root / "gh"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = auth ]; then exit 0; fi\n"
                "printf '%s\\n' '[[{\"full_name\":\"me/keep\",\"private\":false,\"fork\":false,\"archived\":false},"
                "{\"full_name\":\"me/fork\",\"fork\":true},"
                "{\"full_name\":\"me/old\",\"archived\":true},"
                "{\"full_name\":\"me/private\",\"private\":true}]]'\n"
            )
            fake.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if "TOKEN" not in k}
            env["PATH"] = str(root) + os.pathsep + env["PATH"]
            result = subprocess.run(["bash", str(ROOT / "scripts/quick_inventory.sh"), "me"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([r["nameWithOwner"] for r in json.loads(result.stdout)], ["me/keep"])

    def test_diff_rejects_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (after / "README.md").write_bytes(b"binary\0content")
            with self.assertRaises(ValueError):
                prepare("me/tool", "a" * 40, before, after, ["README.md"], root / "bundle")

    def test_install_preserves_existing_and_backups_are_outside_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "skills/github-gardener"
            install(ROOT, target)
            (target / "user-note.txt").write_text("preserve")
            with self.assertRaises(ValueError):
                install(ROOT, target)
            result = install(ROOT, target, force=True)
            backup = Path(result["backup"])
            self.assertEqual((backup / "user-note.txt").read_text(), "preserve")
            self.assertFalse(backup.is_relative_to(target.parent))
            with self.assertRaises(ValueError):
                install(ROOT, ROOT, force=True)
            with self.assertRaises(ValueError):
                install(ROOT, ROOT / "nested/github-gardener", force=True)

    def test_package_is_self_contained_and_extracts_into_runnable_skill(self):
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive_path = package(ROOT, root / "github-gardener.skill")
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("github-gardener/evals/evals.json", archive.namelist())
                self.assertFalse(any("__pycache__" in name for name in archive.namelist()))
                archive.extractall(root / "extracted")
            result = subprocess.run([sys.executable, "-B", str(
                root / "extracted/github-gardener/scripts/github_gardener.py"), "analyze",
                "--snapshot", str(root / "extracted/github-gardener/tests/fixtures/snapshot-v2.json"),
                "--format", "json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["readOnly"])

    def test_install_and_package_share_payload_without_repository_or_local_data(self):
        import shutil
        import zipfile
        from skill_files import skill_files
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source/github-gardener"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            excluded = [".git/config", ".github/workflows/local-only.yml", ".env",
                        "reports/private.json", "config.local.json", "unknown-local-note.txt"]
            for name in excluded:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("LOCAL_ONLY_SENTINEL\n")
            (source / "docs").mkdir(exist_ok=True)
            (source / "docs/design.md").write_text("Public design notes\n")
            target = root / "skills/github-gardener"
            install(source, target)
            installed = {p.relative_to(target).as_posix(): p.read_bytes()
                         for p in target.rglob("*") if p.is_file()}
            self.assertFalse(set(excluded) & installed.keys())
            self.assertIn("docs/design.md", installed)
            self.assertEqual(set(installed), {p.as_posix() for p in skill_files(source)})
            with zipfile.ZipFile(package(source, root / "github-gardener.skill")) as archive:
                packaged = {name.removeprefix("github-gardener/"): archive.read(name)
                            for name in archive.namelist()}
            self.assertEqual(packaged, installed)

    def test_install_and_package_reject_symlinks_in_skill_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source/github-gardener"
            (source / "references").mkdir(parents=True)
            (source / "SKILL.md").write_text("# Skill\n")
            (root / "outside.md").write_text("Must not escape\n")
            (source / "references/linked.md").symlink_to(root / "outside.md")
            with self.assertRaises(ValueError):
                install(source, root / "skills/github-gardener")
            with self.assertRaises(ValueError):
                package(source, root / "github-gardener.skill")

    def test_multi_file_diff_and_tampering_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after, bundle = [root / n for n in ("before", "after", "bundle")]
            before.mkdir()
            after.mkdir()
            for name in ("README.md", "CONTRIBUTING.md"):
                (before / name).write_text("before\n")
                (after / name).write_text("after\n")
            plan = prepare("me/tool", "a" * 40, before, after,
                           ["README.md", "CONTRIBUTING.md"], bundle)
            self.assertEqual(len(plan["files"]), 2)
            self.assertEqual(len(verify(bundle / "plan.json", before, after)["files"]), 2)
            (after / "README.md").write_text("changed after review\n")
            with self.assertRaises(ValueError):
                verify(bundle / "plan.json", before, after)

    def test_new_profile_uses_absent_baseline_and_verifiable_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after, bundle = [root / n for n in ("before", "after", "bundle")]
            before.mkdir()
            (after / "assets").mkdir(parents=True)
            (after / "README.md").write_text("# Demo\n\nUseful Agent projects.\n")
            (after / "assets/banner.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>\n')
            plan = prepare("me/me", None, before, after,
                           ["README.md", "assets/banner.svg"], bundle, new_profile=True)
            self.assertIsNone(plan["baseSha"])
            self.assertEqual(plan["expectedRepositoryState"], "absent")
            self.assertEqual(plan["visibility"], "public")
            self.assertTrue(all(f["beforeSha256"] is None for f in plan["files"]))
            self.assertEqual(verify(bundle / "plan.json", before, after), plan)
            (after / "README.md").write_text("Unreviewed content\n")
            with self.assertRaises(ValueError):
                verify(bundle / "plan.json", before, after)

    def test_new_profile_rejects_existing_files_or_fabricated_base(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (after / "README.md").write_text("Candidate\n")
            for repo, sha, files in (("me/tool", None, ["README.md"]),
                                     ("me/me", "0" * 40, ["README.md"]),
                                     ("me/me", None, ["docs/README.md"])):
                with self.subTest(repo=repo, sha=sha, files=files), self.assertRaises(ValueError):
                    prepare(repo, sha, before, after, files, root / "bundle", new_profile=True)
            with self.assertRaises(ValueError):
                prepare("me/me", None, before, after, ["README.md"], root / "bundle")
            (after / "README.md").write_text("\n")
            with self.assertRaises(ValueError):
                prepare("me/me", None, before, after, ["README.md"], root / "bundle", new_profile=True)
            (after / "README.md").write_text("Candidate\n")
            (before / "README.md").write_text("Existing content\n")
            with self.assertRaises(ValueError):
                prepare("me/me", None, before, after, ["README.md"], root / "bundle", new_profile=True)

    def test_new_profile_cli_accepts_only_one_baseline_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before, after = root / "before", root / "after"
            before.mkdir()
            after.mkdir()
            (after / "README.md").write_text("# Agent projects\n")
            cmd = [sys.executable, "-B", str(ROOT / "scripts/prepare_change.py"), "plan",
                   "--repo", "me/me", "--new-profile", "--current-dir", str(before),
                   "--proposed-dir", str(after), "--file", "README.md", "--output", str(root / "bundle")]
            env = {k: v for k, v in os.environ.items() if "TOKEN" not in k}
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(json.loads(result.stdout)["baseSha"])
            invalid = subprocess.run(cmd + ["--base-sha", "a" * 40], env=env,
                                     capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)

    def test_diff_rejects_path_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "real.md").write_text("content\n")
            (root / "link.md").symlink_to(root / "real.md")
            for filename in ("../README.md", "/README.md", ".git/config", "link.md"):
                with self.assertRaises(ValueError):
                    prepare("me/tool", "a" * 40, root, root, [filename], root / "bundle")

    def test_cli_outputs_and_validation_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "snapshot.json"
            source.write_text(json.dumps(snapshot()))
            # Avoid inheriting real authentication even in this offline subprocess.
            env = {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN"}}
            cmd = [sys.executable, "-B", str(ROOT / "scripts/github_gardener.py"), "analyze",
                   "--snapshot", str(source), "--format", "both", "--output", str(root / "reports")]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / "reports/github-gardener-report.json").read_text())
            self.assertTrue(report["readOnly"])
            self.assertEqual(report["schemaVersion"], "2.0")
            self.assertTrue((root / "reports/profile-readme-draft.md").exists())
            bad = subprocess.run(cmd + ["--max-repositories", "-2"], env=env, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
