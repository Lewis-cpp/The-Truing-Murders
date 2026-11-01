# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.5 已完成（本地收尾，待推送）；下一阶段 v0.6。
- 当前分支：feat/v0.5-four-npcs-memory
- 最近一次完整检查：收尾复跑（2026-11-02，干净工作区）：后端 `ruff format --check`（78 文件）、
  `ruff check`、`pytest -q` 514 项通过 0 失败（2 项 live_llm 按默认配置排除）、`alembic check`
  无差异（0005 可升级、可降级）；前端 `format:check`、`typecheck`、`lint`、`npm test` 28/28、
  `build` 全部通过。
- 已打标签：v0.2、v0.3（`e142ceb`）、v0.4（`33dad97`）、v0.5（本地，待推送）

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 全部检查通过 | 交付记录 | 标签 |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.4 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.5 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.6 | 否 | 否 | 否 | 否 | 否 |
| v1.0 | 否 | 否 | 否 | 否 | 否 |

## 下一步

1. v0.6 阶段开始（下一轮次直接执行）：从标签 `v0.5` 切分支 `feat/v0.6-<主题>`；在仓库根目录
   执行 `cp -r docs/specs/v0.6/tests/. .` 启用验收测试并立即单独提交 "Add v0.6 acceptance tests"；
   跑完整检查记录基线；读 docs/specs/v0.6/spec.md 按任务编号拆 2～4 小时任务写回本节。
   v0.6 引入新依赖（前端 echarts、后端 dev playwright），需更新锁文件。
2. 补做真实模型评测：v0.4（npc01）与 v0.5（four_npcs）的 live 评测均因无凭据未执行，
   配置凭据后 `RUN_LIVE_LLM_TESTS=1 uv run pytest -m live_llm` 补做并把报告计入交付。

## 阻塞与需要人处理的事项

- 推送、开 PR、合并 main 未获授权：v0.3～v0.5 的本地提交与标签均待推送。
- 人工预期仍待真人复核：`case.json`、`full_case_verdicts.json`、`full_case_paths.json`
  （`review_status=pending_human_review`），以及 W1 遗留的 `week_one_verdicts.json` 13 组评分预期。
  不阻塞 v0.4 实现。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

- 2026-11-02 · v0.5 · 2929eb0..HEAD（T19～T21：授权段、摘要、四角色与交付）。
  迁移 0005（memory_epoch + npc_memory_summary）；指纹推进与摘要失效同事务；摘录式摘要
  （80 字/条、300 token、整份校验）与三层预算（1100/300/4000）；四角色默认共享生成、
  generation_available、开局冻结预算；调试要点：psycopg 为 None 绑定 JSON null（约束需容忍）、
  嵌套测试客户端重入 lifespan 需深度计数。后端 514 过 0 败、ruff/alembic check 通过；
  前端 28/28 全过。交付记录 docs/21-v0.5-delivery.md（四人 live 评测无凭据，未执行）。
  标签 v0.5 本地已打，待推送。下一步 v0.6。
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
