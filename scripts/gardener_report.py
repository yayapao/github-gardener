"""Human review artifacts. Public profile drafts exclude internal audit metrics."""
import json
from pathlib import Path

from gardener_common import LABELS, matches


def cell(value):
    return str(value if value is not None else "未知").replace("|", r"\|").replace("\n", " ").replace("<", "&lt;")


def build_profile(owner, repos, cfg):
    full_name = owner + "/" + owner
    if not cfg["audit_profile_repo"]:
        return {"status": "skipped", "profileRepository": full_name,
                "profileRepositoryFound": False, "checks": {}, "recommendedRepositories": [],
                "readmeDraft": "", "draftOnly": True}
    observed_profile = next((r for r in repos if r["nameWithOwner"].casefold() == full_name.casefold()), None)
    profile = observed_profile if observed_profile and observed_profile.get("visibility", "public") == "public" else None
    eligible = []
    for repo in repos:
        analysis = repo["analysis"]
        if (repo["nameWithOwner"] != full_name and repo.get("visibility", "public") == "public"
                and not repo.get("isArchived") and not repo.get("isFork")
                and analysis["maintenanceStatus"] in {"active", "stable"}
                and not analysis["needsAttention"] and repo.get("description")):
            eligible.append(repo)
    def priority(repo):
        ctx = cfg["repository_context"].get(repo["nameWithOwner"], {})
        return (ctx.get("showcase_priority", 0), ctx.get("user_interest") == "high",
                bool((repo.get("readme") or {}).get("checks", {}).get("usage")))
    eligible.sort(key=priority, reverse=True)
    recommendations = [{
        "nameWithOwner": r["nameWithOwner"], "url": r.get("url"),
        "reason": r["description"], "maintenanceStatus": r["analysis"]["maintenanceStatus"],
        "dataConfidence": r["analysis"]["confidence"],
    } for r in eligible[:6]]
    intro = ((profile or {}).get("readme") or {}).get("excerpt")
    lines = ["# " + owner + " · 开源作品", "", intro or "> 请补充你希望展示的身份、目标用户和关注方向。", "",
             "## 从这些项目开始", ""]
    for repo in eligible[:6]:
        lines += ["### [%s](%s)" % (cell(repo["name"]), repo.get("url") or
                                   "https://github.com/" + repo["nameWithOwner"]),
                  "", cell(repo["description"]), ""]
        if repo.get("homepageUrl"):
            lines += ["[查看演示或文档](%s)" % repo["homepageUrl"], ""]
    if not eligible:
        lines += ["> 当前证据不足以推荐公开展示项目；先完善项目说明与维护状态。", ""]
    if profile:
        status = "observed"
    elif observed_profile:
        status = "not_public"
    elif matches({"name": owner, "full_name": full_name}, cfg["exclude"]) or not matches(
            {"name": owner, "full_name": full_name}, cfg["include"] or ["*"]):
        status = "outside_scope"
    else:
        status = "not_observed"
    return {
        "status": status, "profileRepository": full_name, "profileRepositoryFound": bool(profile),
        "checks": {"introductionObserved": bool(intro),
                   "readmeObserved": bool(profile and (profile.get("readme") or {}).get("present")),
                   "note": "只审计本次范围内的 Profile；未观察到不等于仓库不存在。"},
        "recommendedRepositories": recommendations, "readmeDraft": "\n".join(lines).rstrip() + "\n",
        "agentNextStep": "结合用户风格选择视觉与叙事，读取项目实际示例；草案不包含健康分或虚构成就。",
        "draftOnly": True,
    }


def render_markdown(report):
    lines = ["# Github Gardener · " + cell(report["owner"]), "",
             "只读快照：" + report["generatedAt"], "",
             "## 项目组合", "",
             "| 仓库 | 维护状态 | 决策分类 | 健康分 / 覆盖率 | 置信度 | 发展价值 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for repo in report["repositories"]:
        a = repo["analysis"]
        lines += ["| %s | %s | %s | %s / %.0f%% | %.2f | %s |" % (
            cell(repo["nameWithOwner"]), LABELS[a["maintenanceStatus"]], a["categoryLabel"],
            cell(a["healthScore"]), a["health"]["coverage"] * 100, a["confidence"],
            a["developmentValue"]["status"])]
    lines += ["", "评分只衡量已观察的运营维度；请同时查看覆盖率与安全检查缺口。", "",
              "## 逐仓库证据与建议", ""]
    for repo in report["repositories"]:
        a = repo["analysis"]
        lines += ["### " + cell(repo["nameWithOwner"]), "",
                  "健康状态：%s；发展价值下一步：%s" % (
                      a["health"]["state"], a["developmentValue"]["nextExperiment"]), ""]
        lines += ["- %s：%s（%s）" % (e["dimension"], cell(e["summary"]), e["source"]) for e in a["evidence"]]
        lines += ["", "风险：", ""]
        lines += ["- [%s] %s：%s 下一步：%s" % (
            r["severity"], r["title"], r["detail"], r["action"]) for r in a["risks"]] or ["- 未观察到明确风险；继续复核 unknown 项。"]
        lines += ["", "快速改进：", ""]
        lines += ["- %s（%s）" % (w["action"], w["effort"]) for w in a["quickWins"]] or ["- 无自动生成项。"]
        lines += ["", "安全覆盖：", ""]
        lines += ["- %s：%s" % (k, v["status"]) for k, v in repo["security"].items()]
        lines += ["", "归档评估：%s；依据：%s；待复核：%s。" % (
            a["archiveAssessment"]["status"], a["archiveAssessment"]["reason"] or "尚无退役依据",
            ", ".join(a["archiveAssessment"]["blockers"]) or "已提供人工复核记录"), ""]
    lines += ["## 30 天维护计划", ""]
    lines += ["- Day %s · %s：%s" % (p["day"], p["repository"], p["action"]) for p in report["thirtyDayPlan"]]
    lines += ["", "## Issue / PR 回复草稿（未发送）", ""]
    for repo in report["repositories"]:
        for draft in repo["analysis"]["replyDrafts"]:
            lines += ["- %s · %s\n\n  > %s\n" % (
                repo["nameWithOwner"], draft["target"], cell(draft["draft"]))]
    lines += ["", "## 建议归档候选（仅建议）", ""]
    lines += ["- " + name for name in report["summary"]["archiveCandidates"]] or ["- 无满足退役证据和人工复核要求的候选。"]
    lines += ["", "## Profile 审计与 README 草案", "",
              "Profile 状态：" + report["profileAudit"]["status"], "",
              "以下是待 Agent 核对和润色的本地草案：", ""]
    lines += ["    " + line for line in report["profileAudit"]["readmeDraft"].splitlines()]
    lines += ["", "## 数据边界", ""]
    lines += ["- " + item for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def write_outputs(report, output, fmt):
    if fmt == "both":
        if not output:
            raise ValueError("--output directory is required for --format both")
        root = Path(output).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        write_outputs(report, str(root / "github-gardener-report.md"), "markdown")
        write_outputs(report, str(root / "github-gardener-report.json"), "json")
        (root / "profile-readme-draft.md").write_text(report["profileAudit"]["readmeDraft"], encoding="utf-8")
        return
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if fmt == "json" else render_markdown(report)
    if not output:
        print(text, end="")
    else:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
