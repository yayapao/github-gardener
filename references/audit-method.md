# 审计方法

## 事实与覆盖

每个 REST/GraphQL 来源保存 endpoint、fetchedAt、status，失败时记录 reason/httpStatus。分页连接保存 complete；达到 max_pages、响应错误或 cursor 缺失时为 false。提交计数使用默认分支 since=90 天查询，按真实提交时间统计，分页不完整时是下限。

Release 是最新 10 条的有界样本，忽略 draft，按可见 published_at 取最新值。CI 只检查默认分支最近 recent_runs 条，在样本中按 workflow 取最新运行；一个工作流成功不会掩盖另一个失败。样本之外的工作流仍未覆盖。

1.0 快照可读取，但缺少完整性证据的维度保持不完整。采集时间是分析基准，重放同一快照不会因当天变化而改变年龄。

## 维护状态

- active：提交活动、近期公开 Release、维护者回复这三个独立信号中至少两类成立。30 天与 90 天提交不是两类证据。
- stable：用户明确设置 maintenance_intent=stable；或近期有活动、License/使用说明可见、开放 Issue/PR 完整可见，体现保守维护迹象。
- dormant：多来源活动都超过 dormant_days，且提交、Release、开放工作项都有完整性证据。
- unknown：不足以判断，保留事实和需要补充的信息。

维护状态不受安全告警或健康分覆盖；活跃与需关注可同时成立。外部贡献者更新 Issue 不等于维护者仍在维护，因此使用 maintainer response 时间。

## 健康风险与评分

| 维度 | 权重 | 判断 |
| --- | ---: | --- |
| 元数据 | 15 | description、Homepage、Topics 是否有值 |
| 文档入口 | 20 | 安装与使用线索；Profile/文档只看说明是否可见 |
| License | 10 | 代码项目是否有可识别许可证 |
| 安全披露 | 5 | SECURITY.md 是否可见 |
| CI | 15 | 默认分支样本是否通过 |
| 开放工作积压 | 15 | 未回复 Issue 与真正待审 PR |
| 可见安全告警 | 20 | 三类告警都完整可读时计入 |

Profile/docs 不适用 License、安全披露和 CI 权重；总权重按适用项归一化。分数只按观察到的项计算，coverage=已观察权重/适用权重。unknown 不给“安全分”，也不直接当坏分；coverage<1 时标为 incomplete，真实风险存在时仍标 needs_attention。

无可见告警不是“已证明安全”。代码扫描 API 只是告警来源，不能据此宣称 CodeQL 已配置或已扫描所有路径。

置信度是证据覆盖启发式，不是统计概率：README、提交完整性、Release、Issue、PR、CI、告警完整性与用户意图分别贡献。不同判断保留不同证据，发展价值另有独立置信度。

## Issue 与 PR

Issue 超过 issue_stale_days，且评论为零或完整评论样本中没有 OWNER/MEMBER/COLLABORATOR 回复，列为未回复候选；维护者自己创建的 Issue 不要求对自己回复。评论被截断且无法确定时 responseStatus=unknown。

PR 必须非 Draft、待审、最近更新超过 pr_stale_days。APPROVED、CHANGES_REQUESTED 不当作待审，后者可能在等作者。review 样本 last:20，有界样本不是完整历史响应测量。

草稿必须在真正评论前重新读全文。脚本只生成安全的上下文引导语，Agent 应使用已有复现信息、当前阻塞点和可验证下一步改写，避免泛泛索要已有信息或承诺排期。

## 归档

全部成立才显示 suggested_archive：

1. dormant 的完整性证据成立，活动超过 archive_candidate_days。
2. 用户明确 maintenance_intent=retired，并提供 archive_reason 与 archive_evidence_source。
3. Issue/PR 都完整采集且开放数量为零。
4. 无已知 high/critical 风险。
5. archive_review 中 external_usage_reviewed、release_assets_reviewed、migration_ready 都是人工确认后的 true。

仅有退役意图但缺少复核，显示 needs_owner_review；长期安静但无退役依据，显示 insufficient_evidence。不得按 Star、最后提交时间或空 Issue 列表自动推荐删除。

## 发展价值

repository_context 支持 demand、differentiation、feasibility，每项都需要 summary 和 source。再结合 user_interest：

- 有三类证据且兴趣 high：continue_candidate，建议两周实验，不承诺成功。
- 意图 stable：maintain。
- 意图 retired：retire_review。
- 证据不足：insufficient_evidence，列出缺口与下一步。

需求证据可来自真实用户问题、使用记录或用户访谈；差异化可来自可核验对比；可实现性可来自代码范围和可验收里程碑。Agent 收集后写入本次本地上下文，用户主观判断应明确标注来源。不得把示例复核记录当事实。

## 文档与内容

README 时间超过阈值只产生复核建议，不判“内容已过期”。字符长度不参与评分。是否过期须对照当前接口、安装流程、Release、截图与链接核对。扫描不执行第三方命令；确需跑 quickstart 时另行确认其运行范围与环境。

## 组合分类

兼容字段 category：满足归档条件时 suggested_archive；否则有明确风险时 needs_attention；其他情况取 maintenanceStatus。额外 unknown 避免数据缺失时强行五选一。
