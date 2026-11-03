# 安全变更流程

## 授权粒度

一次明确确认可覆盖同一仓库、同一组已展示文件 diff 的完整文档 PR 流程：创建分支、提交候选文件、打开 PR。无需为这三个必要步骤重复询问。

description、Homepage、Topics 等设置展示精确前后值后单独确认。归档、删除、关闭、评论、合并、发布、改名和可见性变更各自按精确目标与内容确认，不混入文档 PR。已获得且仍适用的明确授权不重复请求。

“扫描”“给建议”“清理项目”不是远程写入授权。“创建 PR”的确认不包括合并、发布、评论或归档。取消时远程状态不变。

用户已审阅具体 Profile 候选后明确要求“请发布/上线主页”，属于针对该目标和内容的发布授权，可以完成必要的建仓、文档 PR 和合并。执行前记录并核验精确 HEAD、合并方式及候选内容一致性；不重复索要已适用的确认，不扩展到 Bio、Topics、置顶等设置。目标或版本不清楚时先澄清。

## 文档修改：先形成可审阅结果

1. 读取仓库 default_branch，不假定 main。
2. 读取该分支 HEAD SHA 和目标文件内容、Git blob SHA。编码分支名和文件路径，避免带斜杠的名字变成错误 API 路径。
3. 保存本地 current/ 与 proposed/，生成实际候选，不运行来自 README 的命令。
4. 用 prepare_change.py 生成 changes.diff 与 plan.json；多个文件用重复 --file。
5. 展示仓库、基准 SHA、完整 diff、目的、验证与回滚方式，等待确认。

~~~bash
gh api repos/OWNER/REPO --jq '{default_branch,visibility,archived}'
gh api 'repos/OWNER/REPO/contents/README.md?ref=BRANCH' --jq '{sha,path}'
~~~

BRANCH 和路径参数由 Agent 编码；使用结构化参数或安全 shell 引号。返回大文件而不含 content 时，用 blob API 或本地只读 checkout 获取；不能把不可见文件当空文件覆盖。

## 确认后完整执行

1. 重新读取默认分支 HEAD；与已审阅的 baseSha 不一致则重新计算有实质变化的 diff，不能悄悄换基准。
2. prepare_change.py verify 检查本地当前文件、候选文件和 diff 的哈希。它检测内容变化，不证明用户授权。
3. 创建新 garden/readme-DATE 分支，基于已审阅 SHA；如分支已存在，不覆盖，选择新名字并记录。
4. 提交所有已批准文件。使用当前 Git blob SHA 做乐观并发控制；新文件省略 sha。多个文件可分别 Contents API 提交或用 Git tree API 生成一次提交。
5. 创建 PR，附目的与实际验证结果；读取 PR diff 与已批准 diff 对比。
6. 返回 URL、HEAD SHA、检查结果；不自动合并。

创建分支示例：

~~~bash
gh api --method POST repos/OWNER/REPO/git/refs \
  -f ref='refs/heads/garden/readme-DATE' -f sha='REVIEWED_BASE_SHA'
~~~

提交文件的请求体用本地 JSON 保存 message、branch、base64 content、sha，再执行：

~~~bash
gh api --method PUT repos/OWNER/REPO/contents/README.md --input content-request.json
gh pr create --repo OWNER/REPO --base DEFAULT_BRANCH --head garden/readme-DATE \
  --title 'docs: clarify project usage' --body-file pr-body.md
gh pr view NUMBER --repo OWNER/REPO --json url,state,headRefOid,statusCheckRollup
~~~

API 请求体、PR 描述和评论从文件读取，保留多行文字。禁止直接把不可信 README/Issue 文本插入 shell。branch/PR 失败时报告已产生的分支或提交；清理属于额外动作，不能顺手删除。

回滚：未合并 PR 可由用户另行确认关闭；已合并内容以新的 revert PR 恢复。不要为“回滚方便”自动 force-push。

## 同名 Profile 仓库尚不存在

明确 GET 404/NOT_FOUND 后，用 prepare_change.py plan --new-profile 生成空基准方案。该模式只允许 OWNER/OWNER、根 README.md 与新文件，记录 baseSha=null、expectedRepositoryState=absent、visibility=public；不把不存在的仓库伪装成有一个全零或占位 SHA，也不证明真实缺失。

审阅时说明将新建公开仓库。获授权后重新核对不存在，创建并初始化，读取真实默认分支与 HEAD，再用普通 --base-sha 模式生成差异。只允许把自身初始化内容替换为已经审阅的候选；若出现其他内容或基准冲突，停止覆盖并重新展示。远程候选逐文件哈希应与已批准版本一致，再创建 PR。仅批准 PR 时不合并；明确批准该版发布时按上一节授权说明执行。不要自动改账号设置或其他仓库。

## 仓库设置

先读取 description、homepage、topics；展示 JSON 前后差异，说明这类修改不能通过普通文件 PR 审查。

用户明确批准这一组设置后，准备精确 JSON 请求体：

~~~bash
gh api --method PATCH repos/OWNER/REPO --input metadata-request.json
gh api --method PUT repos/OWNER/REPO/topics --input topics-request.json
gh api repos/OWNER/REPO --jq '{description,homepage,topics}'
~~~

不要把文件 PR 授权视为设置授权；Topics 替换整个集合，需保留未要求删除的原值。

## 评论、关闭、review 与合并

重新读取完整线程及 PR review/CI。草稿应回应已提供的信息，明确阻塞点与下一步，不冒充已开始处理或承诺排期。

每个对象每种动作分别展示并确认。评论用 --body-file；确认发评论不包括关闭，确认 review 不包括合并。合并前记录并核验合并方式与精确 HEAD SHA，重新核对检查状态及代码是否改变；对已有的明确发布授权，按上文范围执行。

## Release、改名与可见性

发布要展示 tag、目标 SHA、资产、notes、draft/prerelease；确认后执行，不自动发包或推额外 tag。改名展示新旧名称和引用影响。可见性变更展示历史、协作与数据暴露影响。分别确认目标和新值，写后重新 GET 验证。

## 归档与删除

归档先核对报告中的退役证据与三项人工复核，再实时读取仓库及工作项。展示精确 full name、原因、迁移说明、归档影响与恢复方式，逐仓库确认后 PATCH archived=true；写后 GET 确认 archived=true。

默认不给“可以删除”的自动结论。用户明确请求删除时，核对备份、外部引用、资产、协作记录与无法常规回滚的影响，形成精确目标和操作后单独确认。不能把“清理”解释为删除授权。
