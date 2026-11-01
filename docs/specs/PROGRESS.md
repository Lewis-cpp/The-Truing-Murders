# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.4 已完成（本地收尾，待推送）；下一阶段 v0.5。
- 当前分支：feat/v0.4-npc01-generation
- 最近一次完整检查：收尾复跑（2026-11-02，干净工作区）：后端 `ruff format --check`（72 文件）、
  `ruff check`、`pytest -q` 491 项通过 0 失败（1 项 live_llm 按默认配置排除）、`alembic check`
  无差异；前端 `format:check`、`typecheck`、`lint`、`npm test` 28/28、`build` 全部通过。
- 已打标签：v0.2、v0.3（2026-11-02 打在 `e142ceb`）、v0.4（本地，待推送）

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 全部检查通过 | 交付记录 | 标签 |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.4 | 是 | 是 | 是 | 是 | 是（本地，待推送） |
| v0.5 | 否 | 否 | 否 | 否 | 否 |
| v0.6 | 否 | 否 | 否 | 否 | 否 |
| v1.0 | 否 | 否 | 否 | 否 | 否 |

## 下一步

1. v0.5 阶段开始（等启动者指示后进行）：从标签 `v0.4` 切分支 `feat/v0.5-<主题>`；在仓库根目录
   执行 `cp -r docs/specs/v0.5/tests/. .` 启用验收测试并立即单独提交 "Add v0.5 acceptance tests"；
   跑完整检查记录基线；读 docs/specs/v0.5/spec.md 按任务编号拆 2～4 小时任务写回本节。
2. 推送与人工事项见下节：v0.3/v0.4 的本地提交与标签待推送；真实模型评测（v0.4 第 8 节）
   需凭据后补做。

## 阻塞与需要人处理的事项

- 推送、开 PR、合并 main 未获授权：v0.3 的本地提交与标签 `v0.3` 待推送。
- 人工预期仍待真人复核：`case.json`、`full_case_verdicts.json`、`full_case_paths.json`
  （`review_status=pending_human_review`），以及 W1 遗留的 `week_one_verdicts.json` 13 组评分预期。
  不阻塞 v0.4 实现。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

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
