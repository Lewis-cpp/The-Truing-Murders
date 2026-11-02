# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.3～v1.0 规格实现与本地自动化验收已完成；发布记录见下方 PR 与标签。
- 发布分支：`feat/v1.0-polish-release`；合并入口：[PR #7](https://github.com/Lewis-cpp/The-Truing-Murders/pull/7)。
- 最近一次完整检查：2026-11-02，代码 `6f25d7f`（含 v1.0 标签后的超时、轮询与关系图修复）。
  后端 Ruff 格式（85 文件）、lint、`alembic check` 通过；`pytest -q` 538 通过、1 跳过、14 排除。
  跳过项是备份恢复自动演练（缺少 PostgreSQL 18 客户端，历史手动演练见 v0.6 交付记录）；
  排除项分别为 E2E 11、真实模型 2、性能 1，E2E 与性能已单独运行通过，真实模型未执行。
  前端格式、类型、lint、构建全部通过，测试 39/39；浏览器 E2E 11/11；
  5 会话、105 请求的非 AI 性能 P95 为 121.5ms（门槛 1000ms）。详见 [测试报告](../test-report.md)。
- 发布：v0.3～v1.0 的提交已通过当前分支推送，五个标签已推送，保留原指向。
  `v1.0` 指向 `c934781`；其后的缺陷修复与文档更正通过 PR #7 交付到 `main`。
  远程检查与合并结果见 PR #7；v0.2 文档收尾 [PR #6](https://github.com/Lewis-cpp/The-Truing-Murders/pull/6) 已合并。

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 本地检查通过 | 交付记录 | 标签（已推送） |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 是 | 是 | 是 | 是 | `e142ceb` |
| v0.4 | 是 | 是 | 是 | 是 | `33dad97` |
| v0.5 | 是 | 是 | 是 | 是 | `261c9f9` |
| v0.6 | 是 | 是 | 是 | 是 | `cc1c098` |
| v1.0 | 是 | 是 | 是 | 是 | `c934781` |

真实模型评测不包含在上述本地自动化通过结论内；各阶段的未执行项仍见交付记录。

## 下一步

1. 真实模型评测与 AI 开启模式通关：v0.4（npc01）与 v0.5（four_npcs）套件已就位，待凭据与预算；
   `RUN_LIVE_LLM_TESTS=1 uv run pytest -m live_llm`，结果计入对应交付记录。
2. 玩家试用（T26，可选）：未进行。
3. 真人复核：案件、评分与路径预期、`guard.json` 仍待审阅。

## 阻塞与需要人处理的事项

- 发布、推送、开 PR 与合并 `main` 已由用户于 2026-11-02 授权，授权不再是阻塞。
- 模型服务凭据与预算缺失，真实模型通关、措辞质量、泄密与成本尚未实测。
- `case.json`、`full_case_verdicts.json`、`full_case_paths.json` 的
  `review_status=pending_human_review`，以及 `guard.json`，仍需真人复核。
  W1 的 `week_one_verdicts.json` 已随 v0.3 退役，当前评分与路径预期以全案文件为准。

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

以下日志保留各轮当时的状态；当前发布状态以上方汇总为准。

- 2026-11-02 · 发布收尾 · `6f25d7f` 及文档更正：修复 E2E 的前端工作目录和数据库环境，
  CI 仅由分支与 PR 触发，避免历史标签重复运行旧工作流；合并 PR #6，推送当前分支与五个阶段标签，
  修正干净 CI 发现的 4 处测试导入排序（未改断言）；建立 PR #7；校正 README、进度、测试报告和 v1.0 交付记录，删除重复的未完成阶段行。
  完整本地复验：后端 538 通过、1 跳过，前端 39/39，E2E 11/11，性能 P95 121.5ms；
  格式、lint、类型、构建与迁移检查通过。远程 CI 与合并结果见 PR #7。

- 2026-11-02 · v1.0 · 85aa9bc..HEAD（T25～T27：主题与响应式、可访问性、发布总验收）。
  theme.css（动效开关/对比度/焦点）、三栏到单栏标签布局、role 播报与证据详情焦点管理；
  axe-core 入 dev 组并修复全部严重对比度违规（含动画中段测色的根因：颜色不再过渡）；
  发布卫生与 traceability 全过；全新克隆按 README 复现安装与 AI 关开局（浏览器通关由
  e2e 在新建 schema 覆盖）；AI 开通关与 live 评测无凭据未执行（如实记录）。
  收尾复跑：后端 537 过 0 败、e2e 11/11、性能 P95 78ms、前端 35/35、hygiene 全过。
  交付记录 docs/23-v1.0-delivery.md 与 docs/test-report.md；标签 v1.0 本地已打，待推送。
  规格阶段全部完成。
- 2026-11-02 · v1.0 · v0.6..HEAD（阶段开始：3 个验收文件入库，264 行）。
  基线：后端 534 过 3 败 1 跳过（hygiene：README 缺 2 条命令、23 号交付与 test-report 未建；
  deselect 含 5 项 a11y e2e）；前端 34 过 1 败（theme.css）。ruff/alembic check 通过。
  下一步 T25。
- 2026-11-02 · v0.6 · 3ab58c6..HEAD（T22～T24：图表/表单契约、恢复演练、部署、E2E 与性能）。
  echarts 图表+时间线 composable（纯投影）、指控表单契约与全部页面 testid、恢复演练 4 项
  （演练 1 修订 cookie 时点，记入 test-amendments）、备份演练手动执行（dump 149674B → 重建 →
  存档一致且可继续）；Dockerfile/deploy compose/nginx 部署实测（含 alembic.ini 补 COPY、
  浏览器开局与调查）；playwright 入 dev 组、CI 增 e2e；traceability 30 行。
  收尾复跑：后端 518 过 0 败、e2e 4/4、性能 P95 78ms、前端 33/33。
  交付记录 docs/22-v0.6-delivery.md；标签 v0.6 本地已打，待推送。下一步 v1.0。
- 2026-11-02 · v0.6 · v0.5..HEAD（阶段开始：7 个验收文件入库 + pytest 切 importlib 模式）。
  基线：后端 516 过 2 败 1 跳过（演练 1 管线缺陷、traceability 未建；备份演练 skip 待 pg_dump 18；
  deselect：e2e 4、live 2、performance 1）；前端 28 过 2 败（graph-timeline、recovery）。
  ruff 与 alembic check 通过。下一步 T22。
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
