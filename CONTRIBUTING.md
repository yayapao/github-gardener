# 参与开发

修改仓库中的源码和设计文档；本地 Codex 安装目录是运行副本，不作为维护入口。

## 维护与打包

需要 Python 3.9+、gh 和 jq。修改完成后检查入口、文档链接和分发包内容：

```bash
python3 -B scripts/package_skill.py --output ../github-gardener.skill
```

## 内容与行为边界

- 维护、风险和发展价值保持独立，缺失数据不等于安全。
- Profile 产物需根据事实和用户方向取舍，不能把固定模板冒充项目理解。
- 真实写入须获得目标和动作的明确授权。
- 记录实际产物和核验范围；没有执行的部分不声称通过。

方法和职责见 [设计文档](docs/design.md)。PR 说明具体行为变化、验证结果与尚未覆盖的范围。更新本机副本使用 `bash scripts/install.sh --force`，安装器会保留旧版本备份。
