# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.4（T15、T16 已完成；T17 生成编排未开始）
- 当前分支：feat/v0.4-npc01-generation（自标签 v0.3 切出）
- 最近一次完整检查：2026-11-02（T16 提交后）：后端 `pytest -q` 468 过 23 败
  （失败全部在 `tests/api/test_generation.py`，属 T17 编排范围；382 项旧测试无回归）；
  ruff format/check 通过；`alembic check` 无差异（迁移 0004 未写）。前端与基线相同
  （25 过 3 败，generation.test.ts 属 T18）。
- 已打标签：v0.2、v0.3（2026-11-02 打在 `e142ceb`；本地，待推送）

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 全部检查通过 | 交付记录 | 标签 |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.4 | 是 | 否 | 否 | 否 | 否 |
| v0.5 | 否 | 否 | 否 | 否 | 否 |
| v0.6 | 否 | 否 | 否 | 否 | 否 |
| v1.0 | 否 | 否 | 否 | 否 | 否 |

## 下一步

1. T17 生成编排与持久化（从上一会话接着做，先读 docs/specs/v0.4/spec.md 第 6～7 节与
   tests/api/test_generation.py 的失败清单）：迁移 0004（`llm_attempt` 按 09 篇 6.6 建表、
   `conversation.active_attempt_id` 复合外键与 PREPARING/GENERATING 的部分 unique 索引、
   `game_session.llm_budget_json` 回填默认值，可升级可降级）；`app.state.llm_gateway` 与
   `generation_dispatcher` 注入点（生产为 `llm_concurrency` 有界线程池，启动时按 `llm_enabled`
   创建，测试可在启动后替换）；6.3 一轮状态机（受理 PREPARING/任务 1～6、额度结算
   KNOWN/UNKNOWN/NOT_SENT、fallback_reason 公开映射）；6.4 失效（切换/离开/指控/重开置 STALE）、
   409 GENERATION_BUSY、过期占位清理（绝不自动重发）；6.5 reply-retries 端点与 `can_retry_reply`；
   第 7 节 API 变化（ConversationView 状态取值、pending_conversations、出示 201 仍即时返回
   固定结果）。提交后让 `test_generation.py` 转绿（当前 23 败）。
2. T18 前端与交付：PREPARING/GENERATING 时 1.5 秒轮询与终态停止、`retry-reply` 按钮、
   `fallback-notice` 提示、`SessionView.pending_conversations`；让 generation.test.ts 转绿；
   真实样本评测按第 8 节执行（无凭据则交付记录如实写"未执行"）；docs/20-v0.4-delivery.md、
   README"启用模型"小节；干净工作区重跑全部检查；打 v0.4 标签。

## 阻塞与需要人处理的事项

- 推送、开 PR、合并 main 未获授权：v0.3 的本地提交与标签 `v0.3` 待推送。
- 人工预期仍待真人复核：`case.json`、`full_case_verdicts.json`、`full_case_paths.json`
  （`review_status=pending_human_review`），以及 W1 遗留的 `week_one_verdicts.json` 13 组评分预期。
  不阻塞 v0.4 实现。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

- 2026-11-02 · v0.4 · 5dc86ac..d0e3d41（T15～T16：配置+网关、授权上下文+回复检查）。
  T15：Settings 增 llm_* 字段（启用时校验三配置）、httpx2 移入运行依赖、
  `infrastructure/llm_client.py`（错误分类、单次请求、deadline 分块读取、64 KiB、严格 JSON 协议）；
  T16：npc_system.v1.txt 模板、`application/memory.py` build_context（授权条目/历史/预算）、
  `application/conversation.py` check_reply 五类原因码、wheel 映射 guard.json 与模板。
  现状：后端 468 过 23 败（全在 test_generation.py，T17 范围），ruff 与 alembic check 通过。
  下一步 T17。
- 2026-11-02 · v0.4 · v0.3..5dc86ac（阶段开始：验收测试入库 + 导入排序修订）。
  基线：后端 pytest 5 个验收集文件收集期失败（缺 llm_client/memory/conversation 等模块，
  既有 382 项未运行）、ruff 通过、alembic check 无差异；前端 25 过 3 败（generation.test.ts）、
  format/typecheck/lint/build 通过。下一步 T15。
- 2026-11-02 · v0.3 · 58d79f7..HEAD（T10～T14 全案实现与收尾）。后端 382 过 0 败、
  ruff 与 alembic check 通过；前端 25/25、format/typecheck/lint/build 通过；浏览器走通演示路径
  （收集 12 证据 → 审讯沈砚双层承认 → 指控存档版本 21 → 复盘 100/100 → 刷新后续玩）。
  交付记录 docs/19-v0.3-delivery.md；测试修订记入 docs/specs/v0.3/test-amendments.md。
  标签 v0.3 本地已打，待推送。下一步 v0.4 阶段开始。
- 2026-11-02 · v0.3 · d3341a2..58d79f7（specs+case.json 入库；启用 v0.3 验收测试）。
  基线：后端 205 收集通过、验收集收集期失败；前端 19 过 6 败。下一步 T10。
