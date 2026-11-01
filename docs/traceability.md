# 需求追踪

FR-01～FR-19 与 NFR-01～11 逐条列出实现位置、自动化测试（路径真实存在，由
`backend/tests/test_traceability.py` 校验）与手动验收记录。需求全文见
[需求分析](02-requirements-analysis.md)。浏览器路径（`tests/e2e`）与性能样本的运行结果
随各版本交付记录更新。

## 功能需求

| 编号 | 需求 | 实现位置 | 自动化测试 | 手动验收 |
| --- | --- | --- | --- | --- |
| FR-01 | 载入并验证固定版本案件，拒绝不完整配置 | `backend/src/backend/application/case.py`（`validate_case`） | `backend/tests/domain/test_case_v3_validation.py`、`backend/tests/domain/test_case_validation.py` | 案件文件导入命令在 README；损坏文件拒绝开局由测试覆盖 |
| FR-02 | 创建、继续和重开独立会话 | `backend/src/backend/application/sessions.py`（`create_session`） | `backend/tests/api/test_game_flow.py`、`backend/tests/application/test_game.py`、`backend/tests/e2e/test_browser_paths.py` | 浏览器重开需二次确认（`confirm-restart`），见 e2e |
| FR-03 | 按阶段限制操作 | `backend/src/backend/domain/state_machine.py`（`ALLOWED`） | `backend/tests/domain/test_phase_matrix.py` | 页面按 `available_actions` 渲染可用操作 |
| FR-04 | 四场景与预设调查动作、按规则解锁 | `backend/src/backend/domain/rules.py`（`investigate`、`open_scenes`） | `backend/tests/domain/test_full_case_rules.py`、`backend/tests/api/test_full_case_flow.py` | e2e 走通 12 次取证解锁路径 |
| FR-05 | 12 条证据与背包详情 | `backend/src/backend/application/views.py`（`evidence_view`） | `backend/tests/api/test_read_endpoints.py` | 背包点击证据显示详情与来源（v0.3 浏览器演示） |
| FR-06 | 4 个 NPC 的审讯与角色隔离 | `backend/src/backend/application/memory.py`（`build_context`） | `backend/tests/application/test_npc_context.py`、`backend/tests/api/test_four_npcs.py` | 四人评测题集就位（live 评测待凭据） |
| FR-07 | 出示持有证据的操作校验 | `backend/src/backend/domain/rules.py`（`present`）、`backend/src/backend/domain/evidence.py` | `backend/tests/api/test_interrogation.py`、`backend/tests/domain/test_full_case_rules.py` | 未持有/伪造出示被拒由 API 测试覆盖 |
| FR-08 | 情绪、压力、信任与一次性收益 | `backend/src/backend/domain/rules.py`（effects 与 `consumed_effects`） | `backend/tests/domain/test_rules.py`、`backend/tests/domain/test_full_case_rules.py` | 界面不显示数值（前端测试断言） |
| FR-09 | 三条谎言链的反证、击破与承认 | `backend/src/backend/domain/rules.py`（链推进与承认门槛） | `backend/tests/domain/test_full_case_rules.py`、`backend/tests/api/test_interrogation.py` | e2e 覆盖沈砚两层承认路径 |
| FR-10 | 展示已知人物关系图 | `backend/src/backend/application/views.py`（`relationship_graph`）、`frontend/src/composables/relationshipGraph.ts` | `frontend/tests/graph-timeline.test.ts`、`backend/tests/api/test_read_endpoints.py` | 图表伴随等价文字列表（同上测试） |
| FR-11 | 展示案件时间线 | `backend/src/backend/application/views.py`（`timeline_view`）、`frontend/src/composables/timeline.ts` | `frontend/tests/graph-timeline.test.ts`、`backend/tests/api/test_read_endpoints.py` | 未知精度、矛盾提示均保留（同上测试） |
| FR-12 | 结构化指控草稿、返回调查与最终提交 | `backend/src/backend/domain/evidence.py`（`validate_draft`/`validate_accusation`） | `backend/tests/api/test_accusation_draft.py`、`backend/tests/application/test_game.py` | 表单契约由前端测试固定（`option-*`/`step-*`/`cite-check-*`） |
| FR-13 | 固定规则的三类判定 | `backend/src/backend/domain/rules.py`（`judge`） | `backend/tests/domain/test_full_case_rules.py`、`backend/tests/api/test_full_case_flow.py`、`backend/tests/e2e/test_browser_paths.py` | e2e 覆盖三结局与无招供 100 分 |
| FR-14 | 逐项复盘与完整真相 | `backend/src/backend/application/views.py`（`review_view`） | `backend/tests/api/test_full_case_flow.py`、`frontend/tests/full-case.test.ts` | 复盘面板列出真相步骤与缺失证据 |
| FR-15 | 权威状态、事件与草稿持久化 | `backend/src/backend/infrastructure/database/repositories/session_repository.py` | `backend/tests/integration/test_database.py`、`backend/tests/infrastructure/test_save_and_constraints.py` | 重启续玩由 API 测试与 e2e 覆盖 |
| FR-16 | 会话内上下文与历史读取范围 | `backend/src/backend/application/memory.py`（预算与 `memory_epoch` 过滤） | `backend/tests/application/test_memory.py`、`backend/tests/api/test_long_conversation.py` | 100 轮长对话输入有界（验收测试） |
| FR-17 | 模型超时、限流、无效输出与额度耗尽 | `backend/src/backend/application/generation.py`、`backend/src/backend/infrastructure/llm_client.py` | `backend/tests/api/test_generation.py` | 降级原因在页面以 `fallback-notice` 展示（前端测试） |
| FR-18 | 输入校验、权限、幂等与版本冲突 | `backend/src/backend/application/sessions.py`（`_replay`/`_execute`） | `backend/tests/api/test_protocol.py`、`backend/tests/integration/test_recovery_drills.py` | 原键重试与冲突提示由演练覆盖 |
| FR-19 | 调用次数、用量与失败记录 | `backend/src/backend/infrastructure/llm_client.py`（usage 校验）、`llm_attempt` 表 | `backend/tests/infrastructure/test_llm_gateway.py`、`backend/tests/api/test_generation.py` | 未知用量不记零由验收断言 |

## 非功能需求

| 编号 | 需求 | 实现位置 | 自动化测试 | 手动验收 |
| --- | --- | --- | --- | --- |
| NFR-01 | 确定性 | `backend/src/backend/domain/rules.py`（`RULE_EXECUTION_VERSION`） | `backend/tests/domain/test_full_case_rules.py`、`backend/tests/api/test_full_case_flow.py` | 相同输入同评分由 13 组人工预期断言 |
| NFR-02 | 存档可靠性 | `backend/src/backend/infrastructure/database/repositories/session_repository.py`（事务与回滚） | `backend/tests/integration/test_recovery_drills.py`、`backend/tests/integration/test_database.py` | 备份/恢复演练见 v0.6 交付记录（命令与结果） |
| NFR-03 | 故障可用性 | `backend/src/backend/application/generation.py`（固定降级） | `backend/tests/api/test_generation.py`、`backend/tests/api/test_full_case_flow.py` | 无招供 100 分路径不依赖模型 |
| NFR-04 | 权限与知识隔离 | `backend/src/backend/application/memory.py`、`backend/src/backend/api/schemas/responses.py`（allowlist 投影） | `backend/tests/api/test_no_leaks.py`、`backend/tests/application/test_npc_context.py` | 结案前响应无秘密由验收断言 |
| NFR-05 | 输入与输出安全 | `backend/src/backend/application/conversation.py`（`check_reply`）、`backend/src/backend/infrastructure/llm_client.py` | `backend/tests/application/test_reply_guard.py`、`backend/tests/infrastructure/test_llm_gateway.py` | 玩家文本只进 user 消息（上下文测试） |
| NFR-06 | 性能（5 会话 P95 ≤ 1s） | `backend/tests/performance/test_non_ai_p95.py`（真实 uvicorn + 5 线程） | `backend/tests/performance/test_non_ai_p95.py` | 结果写入 `backend/reports/performance/`，见 v0.6 交付记录 |
| NFR-07 | 模型等待与成本 | `backend/src/backend/infrastructure/llm_client.py`（deadline）、`backend/src/backend/application/generation.py`（额度） | `backend/tests/infrastructure/test_llm_gateway.py`、`backend/tests/api/test_generation.py` | 30 秒超时与单局硬预算由配置与测试固定 |
| NFR-08 | 可用性与可访问性 | `frontend/src/components/interrogation/InterrogationPanel.vue`（占位与降级提示）、`frontend/src/components/reasoning/CaseBoard.vue`（badge 文字） | `frontend/tests/generation.test.ts`、`frontend/tests/graph-timeline.test.ts` | 情绪/证词/错误均带文字或图标，不仅靠颜色 |
| NFR-09 | 可测试性 | `backend/tests/support/fakes.py`（假网关与手动派发器） | `backend/tests/api/test_generation.py`、`backend/tests/application/test_reply_guard.py` | 全部规则/权限/降级测试离线运行 |
| NFR-10 | 可维护性 | `backend/assets/cases/case_001/v1/case.json`（案件与语言分离）、`backend/src/backend/application/case.py`（版本校验） | `backend/tests/domain/test_case_v3_validation.py`、`backend/tests/test_cli.py` | 案件与规则版本随事件与判定落库 |
| NFR-11 | 可观测性与数据保护 | `backend/src/backend/main.py`（trace-id）、`backend/src/backend/infrastructure/llm_client.py`（密钥不出现在结果与异常） | `backend/tests/api/test_health.py`、`backend/tests/infrastructure/test_llm_gateway.py` | 密钥与完整 messages 不进日志由测试断言 |
