# Agent 执行指引

本页供 Agent 安装、配置和调用 Skill。用户入口是 [README](../README.md) 中的安装 Prompt 与自然语言需求；Agent 自行执行下列步骤，向用户交付结果与必要决策。

## 安装与环境准备

1. 确认当前宿主支持 Agent Skills，检查已有安装及 `gh`、`jq`、`python3`；Python 需 3.9+。依赖缺失时，在当前安装请求范围内使用可用的包管理或安装能力准备，遵守宿主的权限要求。
2. 获取 `https://github.com/yayapao/github-gardener` 中的 Skill。优先使用宿主已有的 Skill 安装能力；Codex 也可获取源码后使用本仓库安装器：

   ~~~bash
   git clone --depth 1 https://github.com/yayapao/github-gardener.git
   cd github-gardener
   bash scripts/install.sh
   ~~~

   默认安装到 `${CODEX_HOME:-~/.codex}/skills/github-gardener`。可用 `--destination /absolute/path/skills/github-gardener` 指定宿主的实际 Skill 目录，不假定所有 Agent 都使用 Codex 路径。

3. 已有同名 Skill 时先核对来源与版本。更新本仓库安装副本时，获取最新源码后执行 `bash scripts/install.sh --force`；旧版本备份到 Codex 根目录下的 `skill-backups/`。保留无关来源的同名内容，不盲目覆盖。
4. 核验实际安装目录中的 `SKILL.md`、脚本、参考文件及其引用，确认依赖命令可用。宿主需要新会话才能发现 Skill 时告知用户；文件安装完成不等于当前会话已加载。
5. 使用 `gh auth status` 检查本机授权，不输出凭证。首次联网任务需要登录时，引导用户通过 GitHub 授权页面完成 `gh auth login`；不要索取聊天中的 Token。普通扫描只需相应读取权限，不申请删除权限。

安装请求只准备环境和 Skill，不自动发起仓库审计或远程变更。安装后按用户目标选择下面的调用方式；命令从 Skill 目录运行，或使用脚本绝对路径。扫描输出放在本次任务目录，避免把用户报告混入 Skill 源码。

## 扫描与离线分析

以下命令从 Skill 目录运行。在其他目录调用时，改用脚本绝对路径。

~~~bash
gh auth status
jq --version
python3 scripts/github_gardener.py scan --owner YOUR_LOGIN \
  --format both --output ./report --snapshot-out ./report/snapshot.json
~~~

输出 Markdown、JSON、独立 Profile 草案，以及可选的原始快照。默认公开、非 Fork、未归档；最多 100 个仓库、每个分页连接最多 5 页。达到上限会标记数据不完整，不伪装全量审计。

自定义范围：

~~~bash
python3 scripts/github_gardener.py scan --owner YOUR_LOGIN \
  --include 'agent-*' --exclude '*-scratch' \
  --config config.example.json --format both --output ./report
bash scripts/quick_inventory.sh YOUR_LOGIN
~~~

include/exclude 使用仓库短名或 OWNER/NAME 的 glob，exclude 优先。在线、离线和 Profile 全部遵守；命令行同名参数覆盖配置值。私有范围必须明确开启 --include-private，且 owner 是当前认证用户。

重新分析 scan 命令保存的快照：

~~~bash
python3 scripts/github_gardener.py analyze \
  --snapshot ./report/snapshot.json \
  --config config.example.json --format both --output ./report
~~~

旧快照缺少分页与新安全检查证据时，置信度会降低。

## 三种判断各回答一个问题

| 判断 | 回答 | 不应推导的结论 |
| --- | --- | --- |
| 维护状态 | 活跃、稳定、休眠或待判断 | 最后提交久就该删除 |
| 健康风险 | 安全告警、CI、响应积压、说明缺口 | 高分就安全 |
| 发展价值 | 需求、差异化、可实现性与你的投入意愿 | Star 多就值得继续 |

决策分类保留活跃、稳定维护、需关注、休眠、建议归档；证据不足额外显示“待判断”。活跃项目也可以同时需关注。

健康分按已观察维度计算，和覆盖率一起展示。Profile、文档项目不因缺少 CI 或安装章节被扣分。发展价值证据不足时给待验证实验，不生成伪精确的投资分数。

## 安全检查覆盖

读取可见的 Dependabot、Secret scanning、代码扫描告警和 Actions 默认权限；保存来源、采集时间、分页完整性与失败原因。Secret scanning 返回的密钥值会被丢弃，只保留数量、级别和告警链接。

代码扫描接口不意味着已经配置 CodeQL；空告警不意味着扫描全面。工作流代码、Action 固定版本、依赖过时情况与历史密钥扫描会标记为未检查，交给 Agent 按需读文件复核。脚本不安装仓库依赖、不执行 README 命令、不触发 Actions。

## 记录用户意图和发展证据

config.example.json 展示 repository_context：项目类型、stable/retired 意图、目标用户、展示顺序，以及带来源的需求/差异化/可实现性证据。

归档需满足长期无多维活动、完整采集且无开放工作项、明确退役原因与来源，以及外部引用、Release 资产、迁移说明三项人工复核。不要复制示例中的 true 冒充实际复核。安静的成熟工具可标为 stable，普通扫描不会自动建议删除。

## 审阅后提交

先读当前文件与默认分支 SHA，在本地制作候选：

~~~bash
python3 scripts/prepare_change.py plan \
  --repo YOUR_LOGIN/my-tool --base-sha 0123456789012345678901234567890123456789 \
  --current-dir ./current --proposed-dir ./proposed \
  --file README.md --file docs/quickstart.md --output ./change
python3 scripts/prepare_change.py verify --plan ./change/plan.json \
  --current-dir ./current --proposed-dir ./proposed
~~~

该工具只生成 diff 和内容哈希，拒绝路径越界、符号链接、二进制和删除。哈希可检测本地内容变化，不能替代对话中的用户授权。

一组明确的文档 diff 可一次批准建分支、提交和开 PR。仓库设置单独确认；归档、删除、关闭、评论、合并、发布、改名和可见性变更分别确认。细节见 [安全变更流程](../references/safe-change-workflow.md)。
