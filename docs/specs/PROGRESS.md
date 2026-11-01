# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.4（验收测试已启用，实现未开始）
- 当前分支：feat/v0.4-npc01-generation（自标签 v0.3 切出）
- 最近一次完整检查：v0.4 基线（2026-11-02）：后端 pytest 因 5 个验收集文件收集期失败中断
  （缺 `backend.infrastructure.llm_client`、`backend.application.memory`、`backend.application.conversation`
  等待实现模块，既有 382 项未运行）；ruff format/check 通过（修掉随测试带入的 4 处 I001，
  见 docs/specs/v0.4/test-amendments.md）；`alembic check` 无差异。前端 `format:check`、
  `typecheck`、`lint`、`build` 通过；`npm test` 25 过 3 败（新 generation.test.ts）。
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

1. T15 配置与网关：`Settings` 增加 llm_* 字段（`SecretStr` 密钥；`llm_enabled` 为真时校验
   base_url/model/api_key 非空，否则启动失败）；`httpx2` 从 dev 组移到运行依赖并更新锁文件；
   `infrastructure/llm_client.py` 实现 `LLMGateway.generate`（第 3 节错误分类表、最多一次请求、
   deadline 分块读取、64 KiB 上限、usage 校验、json_schema 输出）；
   让 `test_llm_gateway.py`、`test_llm_boundary.py` 转绿。
2. T16 授权上下文与回复检查：模板 `backend/assets/prompts/npc_system.v1.txt`（prompt_version=npc-1）；
   `application/memory.py` 的 `build_context` 按 4.1/4.2/4.3（授权条目、四角色两两隔离、
   历史轮选择、预算从最旧整轮丢弃、`ContextOverBudget`）；`application/conversation.py` 的
   `load_guard`/`check_reply` 五类原因码；让 `test_npc_context.py`、`test_reply_guard.py` 转绿。
3. T17 生成编排与持久化：迁移 0004（`llm_attempt`、`conversation.active_attempt_id` 复合外键与
   部分 unique 索引、`game_session.llm_budget_json` 回填）；`app.state.llm_gateway` 与
   `generation_dispatcher` 注入点（有界线程池，可替换）；6.3 一轮状态机（受理/任务 1～6、
   额度结算、fallback_reason 映射）、6.4 失效/忙碌/中断/过期清理、6.5 reply-retries 端点、
   第 7 节 API 变化；让 `test_generation.py` 转绿。
4. T18 前端与交付：PREPARING/GENERATING 时 1.5 秒轮询与终态停止、`retry-reply` 按钮、
   `fallback-notice` 提示、`SessionView.pending_conversations`；让 generation.test.ts 转绿；
   真实样本评测按第 8 节执行（无凭据则交付记录如实写"未执行"）；docs/20-v0.4-delivery.md、
   README"启用模型"小节；打 v0.4 标签。

## 阻塞与需要人处理的事项

- 推送、开 PR、合并 main 未获授权：v0.3 的本地提交与标签 `v0.3` 待推送。
- 人工预期仍待真人复核：`case.json`、`full_case_verdicts.json`、`full_case_paths.json`
  （`review_status=pending_human_review`），以及 W1 遗留的 `week_one_verdicts.json` 13 组评分预期。
  不阻塞 v0.4 实现。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

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
