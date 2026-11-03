"""Independent maintenance, operational health and development-value assessments."""
import copy
from datetime import datetime, timezone

from gardener_common import VERSION, LABELS, age, merged_config, now_iso, select_repositories


def complete(section):
    return section.get("available") is True and section.get("complete") is True


def evidence(dimension, summary, url):
    return {"dimension": dimension, "summary": summary, "source": url}


def normalized_security(repo):
    sec = copy.deepcopy(repo.get("security") or {})
    # Accept v1 snapshots without pretending that missing v2 checks have run.
    if "dependabot" not in sec:
        old = (repo.get("dependencies") or {}).get("dependabot") or {}
        sec["dependabot"] = {
            "status": {"clear": "no_visible_alerts", "open": "findings"}.get(old.get("status"), "unknown"),
            "severityCounts": old.get("severityCounts") or {},
            "complete": False, "note": "Legacy snapshot has no pagination provenance",
        }
    for kind in ("secretScanning", "codeScanning", "workflowPermissions", "workflowContentReview"):
        sec.setdefault(kind, {"status": "not_checked"})
    return sec


def development_value(context):
    supported = {k: context.get(k, []) for k in ("demand", "differentiation", "feasibility")}
    missing = [k for k, v in supported.items() if not v]
    interest = context.get("user_interest", "unknown")
    if context.get("maintenance_intent") == "retired":
        status = "retire_review"
        action = "复核替代方案、外部引用和迁移说明，再决定是否归档。"
    elif not missing and interest == "high":
        status = "continue_candidate"
        action = context.get("next_milestone") or "用两周验证一个最小用户场景，并收集实际使用反馈。"
    elif context.get("maintenance_intent") == "stable":
        status, action = "maintain", "保持兼容和安全维护，按实际需求决定是否增加功能。"
    else:
        status = "insufficient_evidence"
        action = "补充目标用户、差异化、两周内可交付范围和你愿意投入的时间。"
    return {"status": status, "confidence": 0.75 if not missing and interest != "unknown" else 0.3,
            "evidence": supported, "userInterest": interest, "missing": missing,
            "nextExperiment": action, "note": "发展价值为待验证建议；不由 Star、提交次数或健康分推导。"}


def analyze_repo(repo, cfg, now, owner):
    repo = copy.deepcopy(repo)
    name = repo["nameWithOwner"]
    url = repo.get("url") or "https://github.com/" + name
    ctx = cfg["repository_context"].get(name, {})
    project_type = ctx.get("project_type") or (
        "profile" if name.casefold() == (owner + "/" + owner).casefold() else
        "docs" if repo.get("primaryLanguage") in {"Markdown", "Text"} else "code")
    rm, act, rel, ci = [repo.get(k) or {} for k in ("readme", "activity", "releases", "ci")]
    issues, pulls = [repo.get(k) or {} for k in ("issues", "pullRequests")]
    sec = normalized_security(repo)
    ev, risks, wins, drafts = [], [], [], []

    def finding(severity, title, detail, sources, action):
        risks.append({"severity": severity, "title": title, "detail": detail,
                      "evidence": sources, "action": action})

    def win(action, impact, effort="10 分钟"):
        wins.append({"action": action, "impact": impact, "effort": effort})

    unanswered = []
    for item in issues.get("items") or []:
        status = item.get("responseStatus") or ("unanswered" if item.get("comments") == 0 else "unknown")
        days = age(item.get("createdAt"), now)
        if (days is not None and days >= cfg["issue_stale_days"]
                and status in {"unanswered", "no_maintainer_response"}
                and item.get("authorAssociation") not in {"OWNER", "MEMBER", "COLLABORATOR"}):
            unanswered.append({**item, "ageDays": days})
    awaiting = []
    for item in pulls.get("items") or []:
        decision = item.get("reviewDecision")
        waiting = item.get("awaitingReview")
        if waiting is None:
            waiting = decision == "REVIEW_REQUIRED" or (
                decision not in {"APPROVED", "CHANGES_REQUESTED"} and item.get("reviews") == 0)
        days = age(item.get("updatedAt"), now)
        if not item.get("isDraft") and waiting and days is not None and days >= cfg["pr_stale_days"]:
            awaiting.append({**item, "ageDays": days})
    if unanswered:
        finding("medium", "长期未获维护者回复的 Issue", "%d 个超过 %d 天。" % (len(unanswered), cfg["issue_stale_days"]),
                [i.get("url") or url for i in unanswered], "逐项读取线程，给出当前阻塞点与下一步。")
    if awaiting:
        finding("medium", "待审 PR", "%d 个非 Draft PR 超过 %d 天未推进。" % (len(awaiting), cfg["pr_stale_days"]),
                [i.get("url") or url for i in awaiting], "核对 CI、review 请求和变更范围后给出 review。")
    if ci.get("status") == "failing":
        finding("high", "失败 CI", "默认分支采样中至少一个工作流的最新运行失败。",
                [r.get("html_url") or url + "/actions" for r in ci.get("failedWorkflows") or [{}]],
                "查看失败 job 和日志，先复现再修复；不自动重跑或修改工作流。")
    for kind, title in (("dependabot", "依赖漏洞告警"), ("secretScanning", "凭据泄露告警"),
                        ("codeScanning", "代码扫描告警")):
        check = sec[kind]
        counts = check.get("severityCounts") or {}
        if check["status"] == "findings":
            high = sum(counts.get(k, 0) for k in ("critical", "high", "error"))
            finding("critical" if kind == "secretScanning" else "high" if high else "medium",
                    title, "可见告警严重度：" + str(counts), check.get("urls") or [url + "/security"],
                    "按告警定位影响版本与修复路径；凭据先撤销或轮换，不在报告中复述密钥。")
    perms = sec["workflowPermissions"]
    if perms.get("defaultWorkflowPermissions") == "write":
        finding("medium", "Actions 默认写权限", "默认 GITHUB_TOKEN 权限为 write；需结合工作流检查最小权限。",
                [url + "/settings/actions"], "读取工作流，评估改为只读默认值与 job 级最小权限。")
    if not repo.get("description"):
        win("提炼目标用户、核心结果和适用边界，补充一句话 description。", "便于访问者理解项目。")
    if not repo.get("homepageUrl"):
        win("选择已存在且可核验的演示或文档地址作为 Homepage。", "缩短从发现到使用的路径。")
    if len(repo.get("topics") or []) < 3:
        win("从项目真实用途提炼 3–8 个 Topics。", "提高相关搜索的可发现性。")
    if project_type == "code" and (repo.get("license") or {}).get("present") is False:
        finding("medium", "缺少可识别的许可证", "GitHub license 元数据为空；需核对文件与权利归属。",
                [url], "由用户选择适用许可证，不自动套用 MIT。")
    docs_age = age(rm.get("lastModifiedAt"), now)
    if docs_age is not None and docs_age >= cfg["docs_stale_days"]:
        win("对照当前版本检查 README 的安装命令、接口与截图；时间久仅是复核线索。", "确认是否存在真实文档差异。", "20 分钟")
    checks = rm.get("checks") or {}
    if project_type == "code" and not checks.get("usage"):
        win("基于真实接口补一个最小输入与预期输出示例。", "降低首次使用成本。", "20 分钟")
    community_files = (repo.get("community") or {}).get("files") or {}
    if project_type == "code" and community_files.get("contributing") is False:
        win("补充与现有开发命令一致的 CONTRIBUTING.md。", "明确贡献方式与验证要求。")
    if project_type == "code" and community_files.get("issueTemplate") is False:
        win("为实际支持流程准备 Issue 模板，保留必要复现字段。", "减少反馈所需的来回沟通。")

    replies = [i.get("lastMaintainerResponseAt") for i in
               (issues.get("items") or []) + (pulls.get("items") or []) if i.get("lastMaintainerResponseAt")]
    dates = [act.get("latestCommitAt"), rel.get("latestAt")] + replies
    ages = [age(d, now) for d in dates if age(d, now) is not None]
    last_days = min(ages) if ages else None
    independent = [
        act.get("commits30d", 0) >= 1 and act.get("commits90d", 0) >= 3,
        age(rel.get("latestAt"), now) is not None and age(rel.get("latestAt"), now) <= 180,
        any(age(d, now) is not None and age(d, now) <= 90 for d in replies),
    ]
    quiet = (last_days is not None and last_days >= cfg["dormant_days"]
             and act.get("complete") is True and rel.get("available") is True
             and complete(issues) and complete(pulls))
    intent = ctx.get("maintenance_intent", "unknown")
    if intent == "stable":
        maintenance = "stable"
    elif sum(independent) >= 2:
        maintenance = "active"
    elif quiet:
        maintenance = "dormant"
    elif (repo.get("license") or {}).get("present") and checks.get("usage") and complete(issues) and complete(pulls):
        maintenance = "stable" if last_days is not None and last_days < cfg["dormant_days"] else "unknown"
    else:
        maintenance = "unknown"
    retire_evidence = (intent == "retired" and ctx.get("archive_reason")
                       and ctx.get("archive_evidence_source"))
    archive_review = ctx.get("archive_review") or {}
    blockers = [key for key in ("external_usage_reviewed", "release_assets_reviewed", "migration_ready")
                if archive_review.get(key) is not True]
    dangerous = any(r["severity"] in {"critical", "high"} for r in risks)
    if not retire_evidence:
        blockers.append("retirement_evidence_missing")
    if not quiet or last_days < cfg["archive_candidate_days"]:
        blockers.append("inactivity_not_established")
    if not complete(issues) or issues.get("openCount") != 0:
        blockers.append("issues_not_known_empty")
    if not complete(pulls) or pulls.get("openCount") != 0:
        blockers.append("pull_requests_not_known_empty")
    if dangerous:
        blockers.append("unresolved_high_risks")
    if repo.get("isArchived"):
        blockers.append("already_archived")
    archive_candidate = not blockers
    archive_assessment = {
        "status": "candidate" if archive_candidate else "needs_owner_review" if retire_evidence else "insufficient_evidence",
        "reason": ctx.get("archive_reason"), "source": ctx.get("archive_evidence_source"),
        "blockers": blockers, "note": "安静、低 Star 或最后提交时间久，均不构成删除依据。",
    }
    # Health measures operational readiness, not activity or product value.
    components = []
    def component(key, weight, value, reason):
        components.append({"dimension": key, "weight": weight, "value": value, "reason": reason})
    meta = sum(bool(repo.get(k)) for k in ("description", "homepageUrl", "topics"))
    component("metadata", 15, meta / 3, "描述、Homepage 与 Topics 的完整性。")
    doc_value = None if rm.get("present") is None else (
        1.0 if project_type in {"docs", "profile"} and rm.get("present") else
        (int(checks.get("installation", False)) + int(checks.get("usage", False))) / 2)
    component("documentation", 20, doc_value, "检查可理解性入口；长度和时间不证明内容准确。")
    if project_type not in {"docs", "profile"}:
        license_present = (repo.get("license") or {}).get("present")
        component("license", 10, None if license_present is None else float(license_present), "许可证需人工确认适用性。")
        policy = (repo.get("community") or {}).get("securityPolicy")
        component("security_policy", 5, None if policy is None else float(policy), "披露渠道可见性。")
        component("ci", 15, {"passing": 1.0, "failing": 0.0}.get(ci.get("status")), "默认分支采样中的 CI。")
    component("response", 15, max(0, 1 - (len(unanswered) + len(awaiting)) / 4)
              if complete(issues) and complete(pulls) else None, "只衡量当前积压，不代表历史首次响应速度。")
    sec_known = all(sec[kind].get("complete") for kind in ("dependabot", "secretScanning", "codeScanning"))
    component("security_alerts", 20, (0.0 if any(sec[k]["status"] == "findings" for k in
              ("dependabot", "secretScanning", "codeScanning")) else 1.0) if sec_known else None,
              "可见告警覆盖；无可见告警不等于安全。")
    known = [c for c in components if c["value"] is not None]
    total_weight = sum(c["weight"] for c in components)
    known_weight = sum(c["weight"] for c in known)
    coverage = round(known_weight / total_weight, 2)
    score = round(sum(c["weight"] * c["value"] for c in known) / known_weight * 100) if known_weight else None
    needs_attention = bool(risks)
    health_state = "needs_attention" if needs_attention else "incomplete" if coverage < 1 else "observed_ready"
    ev += [
        evidence("activity", "30/90 天提交 %s/%s；最近公开 Release %s；维护者线程回复 %d 条。"
                 % (act.get("commits30d"), act.get("commits90d"), rel.get("latestAt"), len(replies)), url),
        evidence("response", "Issue %s / PR %s；未回复 %d，待审 %d；完整性 %s/%s。"
                 % (issues.get("openCount"), pulls.get("openCount"), len(unanswered), len(awaiting),
                    complete(issues), complete(pulls)), url + "/issues"),
        evidence("documentation", "README 路径 %s；适用类型 %s；旧日期只触发复核建议。"
                 % (rm.get("path", "README.md"), project_type), url),
        evidence("community", "社区文件可见性：" + str(community_files), url + "/community"),
        evidence("dependencies", "依赖清单 %s；SBOM 包 %s；过时版本检查 %s。" % (
            (repo.get("dependencies") or {}).get("manifests", []),
            (repo.get("dependencies") or {}).get("packageCount"),
            (repo.get("dependencies") or {}).get("outdatedVersions", "not_checked")), url + "/network/dependencies"),
    ]
    if intent != "unknown":
        ev.append(evidence("owner_intent", "用户配置的维护意图：" + intent, "config:repository_context." + name))
    for kind, result in sec.items():
        ev.append(evidence("security", kind + ": " + result["status"], url + "/security"))
    for kind, items in (("issue_reply", unanswered), ("pr_reply", awaiting)):
        for item in items[:5]:
            drafts.append({
                "type": kind, "target": item.get("url"), "title": item.get("title"),
                "draft": "感谢反馈。关于“%s”，我需要先核对当前版本和线程已有信息，再明确下一步。" % item.get("title", ""),
                "requiresThreadRead": True, "sent": False,
            })
    category = ("suggested_archive" if archive_candidate else "needs_attention" if needs_attention
                else maintenance)
    confidence = round(0.15 + 0.8 * sum([
        bool(rm.get("present")), act.get("complete") is True, rel.get("available") is True,
        complete(issues), complete(pulls), ci.get("status") in {"passing", "failing"}, sec_known,
        intent != "unknown",
    ]) / 8, 2)
    repo["security"] = sec
    repo["analysis"] = {
        "projectType": project_type, "maintenanceStatus": maintenance,
        "category": category, "categoryLabel": LABELS[category], "needsAttention": needs_attention,
        "healthScore": score, "health": {"state": health_state, "coverage": coverage, "components": components},
        "confidence": confidence, "evidence": ev, "risks": risks, "quickWins": wins,
        "lastActivityDays": last_days, "archiveCandidate": archive_candidate,
        "archiveAssessment": archive_assessment, "developmentValue": development_value(ctx),
        "oldUnansweredIssues": unanswered, "stalePullRequests": awaiting, "replyDrafts": drafts,
        "promotion": {"draftOnly": True, "sourceDescription": repo.get("description"),
                      "sourceReadme": rm.get("excerpt"),
                      "agentTask": "核对 README 与实际接口，提炼目标用户、最小示例、能力边界；不凭模板编造卖点。"},
    }
    return repo


def aggregate_report(snapshot, config=None):
    from gardener_report import build_profile
    cfg = merged_config(config)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("repositories"), list):
        raise ValueError("Snapshot requires a repositories array")
    owner = snapshot.get("owner") or cfg["owner"] or "owner"
    if cfg["owner"] and owner.casefold() != cfg["owner"].casefold():
        raise ValueError("Snapshot owner does not match configured owner")
    for repo in snapshot["repositories"]:
        if not isinstance(repo, dict) or not isinstance(repo.get("nameWithOwner"), str):
            raise ValueError("Each repository requires nameWithOwner")
        if repo["nameWithOwner"].split("/", 1)[0].casefold() != owner.casefold():
            raise ValueError("Repository owner does not match snapshot owner")
    captured_at = snapshot.get("generatedAt") or now_iso()
    now = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    now = now.replace(tzinfo=now.tzinfo or timezone.utc)
    selected = select_repositories(snapshot["repositories"], cfg)
    limited = len(selected) > cfg["max_repositories"]
    repos = [analyze_repo(r, cfg, now, owner) for r in selected[:cfg["max_repositories"]]]
    risks = [{**r, "repository": repo["nameWithOwner"]} for repo in repos for r in repo["analysis"]["risks"]]
    wins = [{**w, "repository": repo["nameWithOwner"]} for repo in repos for w in repo["analysis"]["quickWins"]]
    ordering = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    risks.sort(key=lambda r: ordering[r["severity"]])
    counts = {key: sum(r["analysis"]["category"] == key for r in repos) for key in LABELS}
    plan = [{"day": 1 if r["severity"] in {"high", "critical"} else 3, "repository": r["repository"],
             "action": r["action"], "evidence": r["evidence"]} for r in risks]
    plan.extend({"day": 7, "repository": w["repository"], "action": w["action"]} for w in wins)
    plan += [{"day": 14, "repository": r["nameWithOwner"], "action": r["analysis"]["developmentValue"]["nextExperiment"]}
             for r in repos]
    plan += [{"day": 21, "repository": "portfolio", "action": "核对展示目标，生成项目 README 与 Profile 的可审阅 diff。"},
             {"day": 30, "repository": "portfolio", "action": "重新扫描，对比覆盖率、风险和未回复工作项。"}]
    plan.sort(key=lambda p: p["day"])
    return {
        "schemaVersion": VERSION, "reportType": "github-gardener-analysis",
        "generatedAt": captured_at, "owner": owner, "readOnly": True,
        "scope": {**snapshot.get("scope", {}), "analysisInclude": cfg["include"],
                  "analysisExclude": cfg["exclude"], "analysisLimitReached": limited},
        "summary": {"repositoryCount": len(repos), "categoryCounts": counts,
                    "highRisks": sum(r["severity"] in {"critical", "high"} for r in risks),
                    "archiveCandidates": [r["nameWithOwner"] for r in repos if r["analysis"]["archiveCandidate"]]},
        "repositories": repos, "risks": risks, "quickWins": wins, "thirtyDayPlan": plan,
        "profileAudit": build_profile(owner, repos, cfg),
        "limitations": [
            "健康分按已观察维度归一化，必须同时查看覆盖率；100 分不代表安全。",
            "维护状态、健康风险和发展价值独立；Star 或最后提交时间不决定归档。",
            "安全覆盖为可见告警和 Actions 默认权限；工作流逻辑、过时版本和全历史密钥扫描未执行。",
            "Issue/PR 只覆盖开放工作项及采样评论，未计算历史首次响应时长。",
            "限流、分页上限、无权限或旧版快照使数据不完整；unknown 不能解释为空。",
        ],
    }
