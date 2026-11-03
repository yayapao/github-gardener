# 参与开发

修改仓库中的源码和设计文档；本地 Codex 安装目录是运行副本，不作为维护入口。

## 本地验证

需要 Python 3.9+、gh 和 jq。自动测试不需要 gh 登录，使用模拟快照与 mock 传输：

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/github_gardener.py analyze \
  --snapshot tests/fixtures/snapshot-v2.json \
  --config tests/fixtures/context.json --format both --output ./demo
python3 -B scripts/package_skill.py --output ../github-gardener.skill
```

修改采集或分析逻辑时，用最小模拟场景覆盖实际行为与边界；不要使用真实 Token、真实告警正文或个人仓库报告做测试夹具。只更新文案时检查引用和示例是否仍可用，不添加仅匹配标题或原文的脆弱测试。

## 设计与 Agent 验收

- 维护、风险和发展价值保持独立，缺失数据不等于安全。
- Profile 产物需根据事实和用户方向取舍，不能把固定模板冒充项目理解。
- 测试发布授权时只用模拟状态；真实写入须获得目标和动作的明确授权。
- 新增场景写入 `evals/evals.json`，记录实际产物和已运行的验证；没有执行的验收不标为通过。

方法和职责见 [设计文档](docs/design.md)。PR 说明具体行为变化、验证结果与尚未覆盖的范围。更新本机副本使用 `bash scripts/install.sh --force`，安装器会保留旧版本备份。
