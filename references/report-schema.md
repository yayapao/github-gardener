# JSON 契约 2.0

顶层：schemaVersion、reportType、generatedAt、owner、readOnly、scope、summary、repositories、risks、quickWins、thirtyDayPlan、profileAudit、limitations。

scope 同时保留采集范围和分析范围；listingComplete、repositoryLimitReached、analysisLimitReached 使截断可见。离线过滤只会缩小已有快照，不能补出未采集内容。

repositories 每项包含元数据、readme、community、activity、releases、issues、pullRequests、ci、dependencies、security、sources、analysis。

## 数据来源

~~~json
{
  "endpoint": "repos/USER/REPO/dependabot/alerts?state=open&per_page=100&page=1",
  "fetchedAt": "2026-11-02T00:00:00Z",
  "status": "unknown",
  "reason": "forbidden",
  "httpStatus": 403
}
~~~

成功来源 status=ok，未知来源 unknown；没有捕获精确状态码时不伪造 200。数据集合保留 available 和 complete，失败不能写 openCount=0。fetchedAt 是真实读取时间；generatedAt 是分析年龄基准。

## analysis

~~~json
{
  "projectType": "code",
  "maintenanceStatus": "active",
  "category": "needs_attention",
  "categoryLabel": "需关注",
  "needsAttention": true,
  "healthScore": 72,
  "health": {
    "state": "needs_attention",
    "coverage": 0.8,
    "components": [{"dimension": "ci", "weight": 15, "value": 0, "reason": "..."}]
  },
  "confidence": 0.75,
  "developmentValue": {
    "status": "insufficient_evidence",
    "confidence": 0.3,
    "evidence": {"demand": [], "differentiation": [], "feasibility": []},
    "userInterest": "unknown",
    "missing": ["demand", "differentiation", "feasibility"],
    "nextExperiment": "..."
  },
  "archiveCandidate": false,
  "archiveAssessment": {
    "status": "insufficient_evidence",
    "reason": null,
    "source": null,
    "blockers": ["external_usage_reviewed", "release_assets_reviewed", "migration_ready"]
  },
  "evidence": [],
  "risks": [],
  "quickWins": [],
  "oldUnansweredIssues": [],
  "stalePullRequests": [],
  "replyDrafts": [],
  "promotion": {"draftOnly": true}
}
~~~

healthScore 只按已知维度归一化，未知 component.value=null；不适用维度不进入 components。maintenanceStatus=active/stable/dormant/unknown；category 额外支持 needs_attention、suggested_archive。

evidence 每项是 dimension、summary、source。risk 是 severity、title、detail、evidence、action；跨仓库索引再加 repository。计划包含 day、repository、action，风险计划附带 evidence。

## security

dependabot、secretScanning、codeScanning 的 status 为 findings/no_visible_alerts/unknown/not_checked；同时保存 complete、severityCounts、alertCount、urls、sources。结果不含密钥值、告警原始 body 或仓库凭据。

workflowPermissions 保存实际默认权限或 unknown。workflowContentReview.status=not_checked，除非另有 Agent 的专项检查；dependencies.outdatedVersions=not_checked。不要把 API 无告警解释为完成全面安全审计。

## Profile

status=observed/outside_scope/not_observed/not_public/skipped；未观察到不能证明不存在。recommendedRepositories 是候选列表，readmeDraft 是公开内容草案，draftOnly=true。不把私有项目、私有 Profile 内容、内部健康分或风险标签写入草案。

## 向后兼容与授权

可读取 1.0 快照，但缺失 provenance 和 complete 时不假定完整。JSON 报告升级为 2.0，不兼容旧健康分的横向比较。

报告、archiveCandidate=true 和 Change plan 文件都不是执行授权。调用方必须结合当前会话中的用户确认，且写前核对目标的新状态。
