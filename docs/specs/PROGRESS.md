# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.5（验收测试已启用，实现未开始）
- 当前分支：feat/v0.5-four-npcs-memory（自标签 v0.4 切出）
- 最近一次完整检查：v0.5 基线（2026-11-02）：后端 pytest 因 `tests/application/test_memory.py`
  收集期失败中断（缺 `MemorySummary` 等待实现名字）；单跑新验收集：
  test_four_npcs 4 败 2 过、test_long_conversation 1 败、concurrency 1 败；
  ruff format/check 通过（77 文件）、`alembic check` 无差异。前端 28/28、build 通过（无新前端验收）。
- 已打标签：v0.2、v0.3（2026-11-02 打在 `e142ceb`）、v0.4（2026-11-02 打在 `33dad97`；均本地，待推送）

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 全部检查通过 | 交付记录 | 标签 |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.4 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.5 | 是 | 否 | 否 | 否 | 否 |
| v0.6 | 否 | 否 | 否 | 否 | 否 |
| v1.0 | 否 | 否 | 否 | 否 | 否 |

## 下一步

1. T19 授权段与迁移 0005：`authorization_fingerprint`（当前说法+本人已披露知识 ID+出示且持有的
   证据 ID，规范 JSON sha256；压力/信任/情绪/回避不参与）；迁移 0005（`npc_state.memory_epoch`、
   `npc_memory_summary` 表按 12 篇 6.2）；业务事务结束前比较全部可审讯人物前后指纹，
   变化者 `memory_epoch += 1` 并失效摘要（`summary_revision += 1` 清内容与游标）；
   `conversation.response_plan_json` 冻结该轮 `memory_epoch`；`HistoryRound` 增加
   `player_message_id`/`npc_message_id`；`build_context` 只取 `memory_epoch` 等于当前值的历史。
2. T20 摘要与预算：`SummaryItem`/`MemorySummary`/`message_hash`/`summarize`/`summary_is_valid`
   （摘录不归纳、每条 ≤80 字、从最新往前取到 `max_tokens=300`、`covered_through_seq` 不进最近 6 轮、
   篡改整份丢弃）；`npc_memory_summary` 读→验→条件更新（失败不重试；表坏照常生成）；
   摘要作为紧跟 system 的第一条 user 消息；`ContextBudget` 增 `max_history_tokens=1100`、
   `max_summary_tokens=300` 与三层丢弃顺序。让 `test_memory.py` 全绿。
3. T21 四角色与交付：`llm_enabled_npcs` 默认四人；`SessionView.session.generation_available`；
   额度耗尽全员受理即 FALLBACK `GENERATION_BUDGET_EXHAUSTED`、重试 429、调查/指控照常；
   前端提示"已切换为固定回复"。让 `test_four_npcs.py`、`test_long_conversation.py`、
   `test_shared_gateway_concurrency.py` 转绿。真实评测（第 5 节）无凭据则交付记录写"未执行"；
   docs/21-v0.5-delivery.md、README 增补；干净工作区全检查；打 v0.5 标签。

## 阻塞与需要人处理的事项

- 推送、开 PR、合并 main 未获授权：v0.3 的本地提交与标签 `v0.3` 待推送。
- 人工预期仍待真人复核：`case.json`、`full_case_verdicts.json`、`full_case_paths.json`
  （`review_status=pending_human_review`），以及 W1 遗留的 `week_one_verdicts.json` 13 组评分预期。
  不阻塞 v0.4 实现。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

- 2026-11-02 · v0.5 · v0.4..2929eb0（阶段开始：6 个验收文件入库，1900 行）。
  基线：后端 pytest 因 test_memory.py 收集错误中断（缺 MemorySummary 等）；单跑：
  test_four_npcs 4 败 2 过、test_long_conversation 1 败、concurrency 1 败；
  ruff 与 alembic check 通过；前端 28/28 不变。下一步 T19。
- 2026-11-02 · v0.4 · e83f0a8..HEAD（T18：前端轮询与交付收尾）。页面每 1.5 秒轮询待定轮次、
  终态/离开审讯/卸载停止，fallback-notice 与 retry-reply 按钮（新幂等键，至多两次）。
  交付记录 docs/20-v0.4-delivery.md（真实样本评测无凭据，如实写"未执行"）；README"启用模型"
  小节、接口概览补 reply-retries。干净工作区复跑：后端 491 过 0 败、ruff/alembic check 通过；
  前端 28/28、format/typecheck/lint/build 通过。标签 v0.4 本地已打，待推送。下一步 v0.5。
- 2026-11-02 · v0.4 · d0e3d41..e83f0a8（T17：生成编排与持久化）。迁移 0004（llm_attempt、
  conversation.active_attempt_id + 部分唯一索引、llm_budget_json 回填、message.attempt_id）；
  application/generation.py 任务管线（预留/派发/结算、STALE 复核、额度 KNOWN/UNKNOWN/NOT_SENT）；
  受理侧忙碌与过期清理、切换/离开/指控同事务失效、reply-retries 端点、main.py 注入点。
  调试要点：attempt.request_action_id 必须用触发本次尝试的请求（重试有自己的请求），
  否则唯一约束回滚被任务吞掉。后端 491 过 0 败、ruff/alembic check 通过。
  下一步 T18。
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
