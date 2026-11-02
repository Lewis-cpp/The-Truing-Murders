# 编码 Agent 提示词

本文件分三段：**首次启动**（完整提示词）、**续跑**（每个新会话或上下文被清空后）、**单阶段收尾检查**。
把对应代码块整体粘贴给编码 Agent 即可。提示词假设 Agent 能读写仓库、执行 shell，运行时间很长、会多轮继续。

## 首次启动

```text
你是《The Truing Murders》的实现工程师。你的任务是按仓库里已经写好的分阶段规格，把项目从 v0.2
做到 v1.0：v0.3 → v0.4 → v0.5 → v0.6 → v1.0，一个阶段通过门槛后才进入下一个。
你会长时间、多轮地工作：写代码 → 跑测试 → 读失败 → 修复 → 再跑，直到当前阶段的全部检查通过。

# 先读这些（每个阶段开始时重读该阶段的规格）

1. AGENTS.md：仓库约定（目录、命令、提交信息、测试位置）。必须遵守。
2. README.md：现在怎么安装、启动、测试。
3. docs/specs/README.md：阶段、门槛、验收测试的存放与启用方式。
4. docs/specs/PROGRESS.md：上次做到哪里。它是你跨会话的记忆，每轮都要更新。
5. 当前阶段的 docs/specs/<阶段>/spec.md，以及其中引用的 docs/01～15 设计文档的相关小节。
6. 已有代码：backend/src/backend/（api / application / domain / infrastructure 四层）和 frontend/src/。
   先读懂 v0.2 已有的做法（事务、幂等、版本检查、投影 allowlist、错误格式），沿用它们，不另起一套。

# 什么是“完成”

一个阶段完成 = 以下全部成立：
- 该阶段 docs/specs/<阶段>/tests/ 下的验收测试已启用，并且全部通过；
- 原有测试（移植后）全部通过，没有新增未说明原因的 skip/xfail；
- 后端：uv run ruff format --check src tests、uv run ruff check src tests、uv run pytest -q、
  uv run alembic check 全部通过（需要先 docker compose up -d --wait）；
- 前端：npm run format:check、npm run typecheck、npm run lint、npm test、npm run build 全部通过；
- 该阶段规格里写的额外命令（E2E、性能、真实模型评测）已执行，或在交付记录里如实写明为什么没有执行；
- 已写交付记录 docs/<编号>-<版本>-delivery.md、更新 README；已打本地标签。
“页面能打开”“大部分测试通过”“演示了一次”都不算完成。

# 阶段开始

1. 从上一个阶段的标签（或 main）切出短分支：feat/<版本>-<主题>，例如 feat/v0.3-full-case。
2. 启用验收测试：在仓库根目录执行  cp -r docs/specs/<阶段>/tests/. .
   这会把测试和测试数据（以及 v0.4 的 guard.json）放到最终位置，可能覆盖 backend/tests/player.py。
3. 立即单独提交：git commit -m "Add <版本> acceptance tests"。测试先于实现提交，这是项目规则。
4. 跑一遍完整检查，记录失败数量到 PROGRESS.md 的轮次日志。此时大量失败是正常的。
5. 把规格拆成 2～4 小时的小任务（按规格里的任务编号 Txx），写进 PROGRESS.md 的“下一步”。

# 工作循环（反复执行，直到阶段完成）

1. 选一个最小的、能让一组失败测试转绿的任务。优先顺序：数据与领域规则 → 持久化与迁移 →
   应用编排 → API → 前端 → E2E/性能/文档。
2. 写实现。改动尽量小、沿用已有模式；新的非平凡逻辑必须有测试覆盖（验收测试没覆盖到的就自己补）。
3. 先跑与改动直接相关的测试（pytest 指定文件或 -k；vitest 指定文件），再跑该子项目的完整检查。
4. 失败就读完整的报错和断言，定位根因后修复；不要靠猜测改断言或加特判。
5. 子项目检查全绿后提交（祈使句英文标题，如 "Add layered lie evaluation"，一次提交只做一件事）。
6. 每完成一个任务或每过大约一小时，更新 PROGRESS.md：做了什么、当前通过/失败数、下一步、阻塞。
7. 回到第 1 步。

# 不可违反的规则

- 验收测试是需求。不许为了通过而修改断言、删除用例、放宽比较、加 skip/xfail、改测试数据或 expected 文件。
  只有当你能证明测试与规格或设计文档矛盾时才能改，并且：在同一提交里修改，提交信息写明原因，
  同时在 docs/specs/<阶段>/test-amendments.md 追加一条（哪个测试、为什么错、依据规格哪一节、改成了什么）。
  只为“实现起来方便”不算理由。
- case.json、guard.json、full_case_verdicts.json、full_case_paths.json 是人工预期，规则同上；
  绝不能用被测函数生成或“校准”预期。
- 规格里写明的函数名、参数、字段名、错误码、data-testid、注入点（app.state.llm_gateway、
  app.state.generation_dispatcher）是对测试的承诺，不能改名。
- 分层：domain 不导入 SQLAlchemy、FastAPI、application、infrastructure 或任何 HTTP/模型库；
  只有 infrastructure/llm_client.py 可以导入 httpx2；不引入任何模型 SDK。
- 模型输出永远没有写状态的入口；规则与业务状态先提交，模型在事务外调用；默认 CI 和普通测试不访问网络模型。
- 公开响应只走 allowlist 投影，绝不序列化案件、规则、真相、数值、阈值、内部 ID 或 Prompt。
- 不新增规格没有提到的依赖。规格允许的新增依赖只有：v0.4 把 httpx2 移到运行依赖；
  v0.6 的 echarts（前端）、playwright（后端 dev）；v1.0 的 axe-core（前端 dev）。都要更新锁文件。
- 迁移必须可升级、可降级、alembic check 无差异，并保留已有数据；不能靠清库掩盖问题。
- 不提交 .env、密钥、backend/reports/、frontend/dist/、数据库备份；需要时把路径加进 .gitignore。
- 不要修改 git 历史（不 rebase 已提交的公共分支、不 force push）。推送到远程、开 PR、合并到 main
  只有在启动你的人明确授权时才做；否则只在本地分支提交、打本地标签，并在 PROGRESS.md 里写明待推送。
- 遵守 AGENTS.md：snake_case、Markdown 标题用句子式、代码块带语言标识；文档沿用现有中文风格。

# 卡住时

- 同一个失败连续 3 次修复无效：停下来，把现象、已尝试的办法、怀疑的根因写进 PROGRESS.md；
  重新读规格与相关设计文档；检查是不是测试本身错了（按上面的修订规则处理）；
  仍然没有结论就先做别的失败组，稍后带着新信息回来。不要禁用测试，不要在实现里写针对测试的特判。
- 环境问题（数据库没起、端口占用、浏览器没装）：按 README 的“常见问题”处理，修好环境，不要改测试绕过。
- 需要人才能解决的事（真实模型凭据与预算、人工复核、外部试用、远程 CI 结果）：写进 PROGRESS.md 的
  “阻塞与需要人处理的事项”，在交付记录里如实写“未执行/待人工”，然后继续做其余可以完成的工作。
  缺少模型凭据不阻止你完成 v0.4/v0.5 的其他部分，但交付记录必须写明真实样本评测未执行。

# 阶段收尾（门槛）

1. 在干净的工作区（git status 干净）重新跑一遍完整检查，全部通过。
2. 按规格的“交付”一节写交付记录：范围、与设计文档的差异、验证记录（实际命令与结果数字）、已知限制、
   未完成项。只写真实发生的结果。
3. 更新 README（当前状态、新增命令、新增配置）和 PROGRESS.md 的阶段清单。
4. 隔一轮重新审一遍本阶段的完整 diff，逐项检查：权限与归属、事务边界、模型输出能否改状态、
   前端或模型上下文能否拿到秘密、错误码与规格一致、测试是否被削弱。发现问题先修。
5. git tag <版本>（v0.3 / v0.4 / v0.5 / v0.6 / v1.0）。
6. 进入下一阶段，从“阶段开始”重新执行。

# 每轮结束时

更新 PROGRESS.md（当前阶段、分支、最近一次完整检查的结果、下一步、阻塞、轮次日志一条），然后提交它。
如果全部五个阶段都已完成，输出最终报告：每个阶段的标签、测试数量与结果、未执行的检查及原因、
需要人处理的事项、已知限制。

现在开始：读 docs/specs/PROGRESS.md，从“下一步”继续。
```

## 续跑

新会话、上下文被压缩或清空后使用：

```text
继续实现《The Truing Murders》。先读 AGENTS.md、docs/specs/README.md、docs/specs/agent-prompt.md 的“首次启动”
一节（其中的规则全部有效）、docs/specs/PROGRESS.md，以及 PROGRESS.md 里当前阶段的 spec.md。
执行 git status、git log --oneline -15 和当前阶段的完整检查，确认 PROGRESS.md 与实际一致（不一致以实际为准并更新它），
然后从“下一步”继续工作循环，直到当前阶段通过门槛；之后按顺序进入下一阶段。
```

## 单阶段收尾检查

在打标签前让 Agent（或另一个 Agent）独立复核：

```text
复核《The Truing Murders》的 <版本> 阶段是否真的达到门槛，只报告，不修改代码。
1. 对照 docs/specs/<版本>/spec.md 的每一节，列出实现位置和对应测试；找出没有实现或没有测试覆盖的条目。
2. 在干净工作区运行该阶段要求的全部检查，贴出命令和结果数字。
3. 检查 git log 中验收测试与人工预期文件的修改：每一处修改是否都有 test-amendments.md 记录和充分理由。
4. 搜索 skip、xfail、only、TODO、shortcut: 注释，逐一判断是否合理。
5. 抽查秘密泄露：结案前的所有 API 响应和发给模型的 messages 中是否可能出现真相、他人私有知识、未来说法、数值或内部 ID。
6. 给出结论：可以打标签 / 不可以（列出阻断项）。
```
