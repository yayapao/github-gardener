# Hi, I'm Garden Demo

我关注应用 Agent 和可复用 Skills，希望让工具、上下文与界面更好地协作。这是我的个人主页，主要记录作品与当前探索。

我喜欢写能解决具体问题的工具，也喜欢把一个想法做成完整的小应用。最近的重点是 Agent 开发，尤其是在真实应用里连接业务工具、会话和人工审批。

## Navigation

[关于我](#关于我) · [精选项目](#精选项目) · [当前关注](#当前关注) · [技术栈](#技术栈) · [交流](#交流)

## 关于我

我的工作围绕应用 Agent 和可复用 Skills 展开。我关心一个 Agent 是否能理解任务、调用合适的工具，并让使用者看清进度与结果。

## 精选项目

### agent-toolkit

[项目仓库](https://github.com/garden-demo/agent-toolkit)

为现有应用接入工具、流式对话与人工审批的工具包。可以替换模型和存储，也可以注册应用自己的工具。适合已经有应用、希望逐步加入 Agent 能力的开发者。

[探索项目](https://github.com/garden-demo/agent-toolkit) · [集成 Skill](https://github.com/garden-demo/agent-toolkit/blob/main/SKILL.md)

### product-starter

[项目仓库](https://github.com/garden-demo/product-starter)

从 Next.js 开始用 coding agent 构建产品的模板。包含工具接入指南，也可加入桌面壳，适合从小想法开始尝试完整产品的人。它不提供云端部署服务。

[开始使用](https://github.com/garden-demo/product-starter) · [Agent 指南](https://github.com/garden-demo/product-starter/blob/main/docs/agent-guide.md)

### boardgame-skill

[项目仓库](https://github.com/garden-demo/boardgame-skill)

一个兴趣驱动的 Python Skill，用于检索棋局记录与棋手数据。它使用标准库访问公开 API，需要用户提供棋手 ID，并将结果输出为 JSON，方便 Agent 使用。

[查看项目](https://github.com/garden-demo/boardgame-skill) · [Skill 定义](https://github.com/garden-demo/boardgame-skill/blob/main/SKILL.md)

## 当前关注

- 工具接入：让应用已有能力成为 Agent 能理解和调用的接口。
- 上下文：把任务与应用中的对象联系起来。
- 人工审批：让使用者了解动作，并在需要的时候做决定。
- 复用：将具体工作流整理成其他 Agent 也能使用的 Skill。

## 技术栈

我主要使用 TypeScript、React、Next.js 与 Python，也会根据项目需要选择合适的工具。

## 交流

如果你也在研究应用 Agent 或可复用 Skills，可以在项目 Issue 中交流。让工具、上下文与界面协作，是我正在探索的方向。
