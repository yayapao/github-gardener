# Github Gardener

让 Agent 帮你经营 GitHub 项目：有证据地盘点风险与维护价值，改进 README，设计个人主页，再按授权提交变更。

**默认只读 · 通过 gh 使用本机登录态 · Python 标准库 · MIT**

## 能做什么

- **盘点项目**：公开、非 Fork、未归档仓库起步，支持排除列表、自定义范围和明确授权的私有扫描。
- **给出判断**：维护状态、健康风险、发展价值分别说明，提供证据、置信度、快速改进和 30 天计划。
- **处理积压**：找未回复 Issue、待审 PR 和失败 CI，准备具体行动与回复草稿。
- **经营内容**：完善描述、Topics 和 README；为 Profile 选择项目、编排文案、制作静态横幅与预览，支持按比例精简。
- **审核后修改**：先完整 diff，再按授权建分支、提交和 PR；危险动作分别确认。

低 Star 或长期没提交不等于应该删除。未知数据不算无风险，健康分也不代表全面安全审计。

## 安装到 Codex

准备 [GitHub CLI](https://cli.github.com/)、jq 和 Python 3.9+，再克隆安装：

```bash
git clone https://github.com/yayapao/github-gardener.git
cd github-gardener
bash scripts/install.sh
```

默认安装到 `${CODEX_HOME:-~/.codex}/skills/github-gardener`。已安装时运行 `bash scripts/install.sh --force`，旧版本会备份到 Codex 的 `skill-backups/`，不进入 Skill 发现目录。也可用 `--destination /absolute/path/skills/github-gardener` 指定目标。

开启新的 Codex 会话，即可使用 `$github-gardener` 或自然语言调用。联网扫描前执行 `gh auth login`；不把 Token 写进配置或聊天。扫描只需相应读取权限，不要为普通扫描申请删除权限。

更新源码与本机安装副本：

```bash
git pull --ff-only
bash scripts/install.sh --force
```

## 在 Agent 里直接说

```text
$github-gardener 扫描我的项目，找安全风险、值得继续开发的项目和快速改进，先只读。
```

```text
$github-gardener 以 Agent 开发为重点设计我的 Profile，保持简洁，先给预览和 diff。
```

```text
$github-gardener 优化 my-tool 的 README、描述和 Topics，依据真实代码写，修改前展示差异。
```

还可以要求“文案减少 50%”“给待回复 Issue 写草稿”或“生成 30 天维护计划”。自动扫描提供事实，Agent 负责理解和编辑；后台不会自行修改仓库。

## 无需 Token 的离线体验

```bash
python3 -B scripts/github_gardener.py analyze \
  --snapshot tests/fixtures/snapshot-v2.json \
  --config tests/fixtures/context.json --format both --output ./demo
```

生成 Markdown、JSON 和 Profile 事实草案。示例数据与退役记录都是虚构的，不代表真实账号。完整参数、私有扫描与配置见 [使用指南](docs/usage.md)。

## 设计与验证

- [设计与能力边界](docs/design.md)：Agent 与脚本分工、证据模型、安装与维护方式。
- [Profile 设计与编排](references/profile-design.md)：定位、项目选择、原创视觉、精简、预览和上线。
- [审计方法](references/audit-method.md) · [内容经营](references/editorial-workflow.md) · [安全变更流程](references/safe-change-workflow.md) · [报告契约](references/report-schema.md)。
- [参与开发](CONTRIBUTING.md)：离线测试与 Agent 场景验收。

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/package_skill.py --output ../github-gardener.skill
```

`.skill` 是可解压的 ZIP 包，包含可安装 Skill、设计指南、模拟数据与测试。安装和打包使用相同的文件清单，排除 Git 元数据、CI 配置与本地工作报告。CI 运行离线单元测试、分析和打包；`evals/evals.json` 的 Agent 行为题需单独执行，不能把单元测试通过等同于设计或授权行为验收。

源码入口为 [SKILL.md](SKILL.md)，本仓库是唯一维护源，本地安装目录是运行副本。

## 许可证

[MIT](LICENSE) © yayapao
