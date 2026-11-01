# v0.6 规格：完整 MVP 与可部署性

任务 T22～T24，约 40 小时。前置：`v0.5` 标签（T22 只依赖 v0.3，可以先做）。
依据：第 11 篇（1.5、5、7）、第 13 篇第 6～7 节、第 14 篇第 11～12 节、需求 FR-01～19、NFR-06。

## 1. 目标

补齐关系图、时间线和恢复交互；部署一套“静态前端 + 单个后端进程 + PostgreSQL”；
用浏览器跑通三结局、无招供与恢复路径；测出 5 会话非 AI 操作的 P95。结束时**冻结新增玩法**。

### 不做

SSE/WebSocket、第二案件、拖拽推理板、多进程或多实例部署、Redis、对象存储、视觉美化（v1.0）。

## 2. 关系图与时间线（T22）

依赖：安装 `echarts`（固定到锁文件）；不安装 Vue Router（仍是单页）。图表只吃后端投影，不读任何别的数据。

- `frontend/src/composables/relationshipGraph.ts` 导出纯函数 `graphOption(graph: RelationshipGraph): EChartsOption`：
  `series[0].type = 'graph'`，`data` 恰好是 `graph.nodes`（`id = character_id`，`name = name`），
  `links` 恰好是 `graph.edges`（`source`/`target` 为两端 ID，`value` 为关系类型，`lineStyle.type` 对
  `TESTIMONY` 或 `UNVERIFIED` 用 `'dashed'`，否则 `'solid'`）；不能加入任何 API 没给的节点或边。
- `frontend/src/composables/timeline.ts` 导出 `timelineRows(timeline: TimelineView): TimelineRow[]`，
  `TimelineRow = {id, title, timeLabel, badge, conflicts: string[]}`：
  保持后端顺序；`timeLabel` 对 `EXACT`/`RANGE` 用 `time_label`，对 `UNKNOWN` 用 `「时间未知：」+ time_label`；
  `badge` 为 `已核验`（FACT+VERIFIED）、`证词`（TESTIMONY）或 `存疑`（其他）；`conflicts` 为
  `known_conflicts` 中条目的标题（只取同一视图里存在的条目）。不合并、不消除矛盾的条目。
- 组件：`data-testid="relationship-graph"`（ECharts，`renderer: 'svg'`）始终伴随 v0.3 的等价文字列表
  `relationship-list`；时间线 `timeline-list` 每行显示 `timeLabel`、`badge` 文字和冲突提示（不能只靠颜色）。
- 与指控联动：在 `ACCUSATION` 阶段，来源为 `EVIDENCE` 的关系边和时间线条目旁显示
  `data-testid="cite-{evidence_id}"` 按钮，点击把该证据加入表单的引用证据（已持有才显示）。
- 复盘联动：复盘面板列出真相步骤，对每个步骤显示玩家关联的证据与 `missing_evidence_ids`。

## 3. 指控表单的测试契约

为浏览器 E2E 固定表单控件（替换 v0.3 的实现细节，`save-draft`、`confirm-accusation`、`submit-accusation` 保留）：

| `data-testid` | 控件 |
| --- | --- |
| `option-{id}` | 凶手、凶器、动机候选，各组单选 |
| `step-{id}` | 过程步骤复选，**按勾选先后**组成顺序；取消勾选从顺序中移除 |
| `cite-check-{evidence_id}` | 引用证据复选（只列已持有证据） |
| `link-{step_id}-{evidence_id}` | 步骤与证据关联复选；只在步骤已选且证据已引用时出现 |
| `accusation-explanation` | 解释文本框 |

E2E 另外依赖下列控件（页面其余部分沿用 v0.3/v0.4 的 `data-testid`）：

| `data-testid` | 控件 |
| --- | --- |
| `start-game` | 大厅里开始所选案件；已有存档时为 `restart-game`（需二次确认 `confirm-restart`） |
| `action-{id}` | 调查按钮；完成后带属性 `data-completed="true"` |
| `talk-{npc_id}` | 人物卡片中的“审讯”按钮 |
| `present-{evidence_id}` | 审讯面板中出示该证据 |
| `chat-input`、`chat-send` | 聊天输入框与发送按钮 |
| `leave-interrogation`、`open-accusation`、`cancel-accusation`、`finish-review` | 对应阶段动作 |
| `verdict-category`、`verdict-score` | 复盘中的类别中文名（正确/部分正确/错误）与分数（如 `100.00`） |
| `phase` | 当前阶段的中文名（调查/深入调查/审讯/指控/复盘/已结束） |

## 4. 恢复交互与故障演练（T23）

前端：

- 写请求的结果不确定（断网、超时、5xx）时，先用原 `Idempotency-Key` 查 `GET /requests/{id}`；
  找到 `COMMITTED`/`NOOP` 就按成功刷新，`REJECTED` 按原错误提示，404 时提供“重试同一操作”（原键原载荷）。
  这条链路 v0.2 已有，本阶段补齐聊天、出示、草稿、重试回复这些新写入口。
- `SAVE_VERSION_UNSUPPORTED`、`SESSION_NOT_CURRENT`、`STATE_VERSION_CONFLICT` 都给出可操作的提示，不清空未保存的表单。

后端演练（`backend/tests/integration/test_recovery_drills.py`）：

| 演练 | 期望 |
| --- | --- |
| 出示事务在写完对话轮次后失败 | 503 `PERSISTENCE_UNAVAILABLE`；证据出示、数值、对话轮次全部没有落库；原键重试成功且只生效一次 |
| COMMIT 后客户端断线 | `GET /requests/{id}` 为 `COMMITTED` 且结果与原响应一致；原键重发返回原结果；不重复加压 |
| 模型派发后进程崩溃 | v0.4 已覆盖：用量 `UNKNOWN`，轮次 `GENERATION_INTERRUPTED`，不自动重发 |
| 重开后旧局的迟到回复 | 旧轮次 `STALE`，只结算用量；新局看不到旧局任何对话 |
| 备份与恢复 | `pg_dump -Fc` 备份 → 删库重建 → `pg_restore` → 未结案存档可继续、版本与证据一致 |

备份恢复演练需要与服务端同主版本（18）的 `pg_dump`/`pg_restore`。本机或 CI 没有时，该测试以写明原因的
`skip` 跳过，并在交付记录中写上手动演练的命令与结果；其余演练必须在 CI 运行。

## 5. 部署（T24）

- `backend/Dockerfile`：Python 3.12 slim，`uv sync --locked --no-dev`，以非 root 用户运行
  `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1`。镜像不含 `.env`、测试和报告。
- `backend/deploy/compose.yaml`：`db`（与开发相同的固定摘要镜像、命名卷）、`api`（上面的镜像，迁移与导入作为
  一次性命令 `docker compose run --rm api ...` 执行，启动时不自动导入）、`web`（固定版本 nginx，挂载
  `../../frontend/dist`，`/api/v1/` 反向代理到 `api:8000`，其余路径回退到 `index.html`）。只暴露 `web` 的端口。
- `backend/deploy/nginx.conf`、`backend/deploy/.env.example`（不含真实密钥，`ALLOWED_ORIGINS` 指向部署地址，
  `COOKIE_SECURE` 说明 HTTP 演示环境的取舍）。
- README 增加“部署与备份”：构建前端、启动、迁移、导入、健康检查、`pg_dump`/`pg_restore` 命令。

## 6. 浏览器 E2E 与性能（T24）

- 依赖：后端 dev 组加入 `playwright`（Python 同步 API，不用 pytest 插件）。浏览器安装命令写进 README 与 CI。
- 默认 `addopts` 增加 `not e2e`；运行方式 `uv run pytest tests/e2e -m e2e`。fixture 用测试库启动
  `uvicorn`（127.0.0.1:8000，`LLM_ENABLED=false`）和 `npm run preview`（4173，需先 `npm run build`），
  测试结束后关闭进程。
- E2E 覆盖：无招供正确 100 分；部分正确与错误各一条；含沈砚两层承认的路径；刷新后继续；结案后复盘与“结束本局”。
- 性能：`backend/tests/performance/test_non_ai_p95.py`（标记 `performance`），启动真实 uvicorn，5 个线程各开一局，
  走完“开局 → 12 次调查 → 审讯 → 4 次出示 → 指控 → 结案”，记录每个请求的服务端往返时间。
  断言 P95 ≤ 1.0 秒，并把样本数、P50/P95/最大值、CPU 核数、Python 与 PostgreSQL 版本写到
  `backend/reports/performance/`（不入库）。
- CI 新增 `e2e` 任务（PostgreSQL 服务 + 前端构建 + Playwright Chromium）。性能测试不进 CI，在交付记录中给出本机结果。

## 7. 需求追踪

`docs/traceability.md`：FR-01～FR-19 与 NFR-01～NFR-11 每条一行，列出实现位置、自动化测试文件
（必须真实存在）、手动验收记录或“未完成”。`backend/tests/test_traceability.py` 检查每个 FR 都有一行且引用的
测试文件存在。

## 8. 验收测试

| 文件 | 覆盖 |
| --- | --- |
| `frontend/tests/graph-timeline.test.ts` | `graphOption`、`timelineRows`、图表伴随文字列表、引用联动 |
| `frontend/tests/recovery.test.ts` | 新写入口的不确定结果先查原请求、404 后原键重试、冲突不清空表单 |
| `backend/tests/integration/test_recovery_drills.py` | 第 4 节 |
| `backend/tests/e2e/conftest.py`、`backend/tests/e2e/test_browser_paths.py` | 第 6 节 E2E |
| `backend/tests/performance/test_non_ai_p95.py` | 第 6 节性能 |
| `backend/tests/test_traceability.py` | 第 7 节 |

## 9. 交付

`docs/22-v0.6-delivery.md`：部署步骤与实测、演练记录（含备份恢复）、E2E 与 P95 结果和环境、FR 追踪表链接、
未完成的验收。时间不够时这就是可交付版本，但未完成项必须列明，不宣称已达到 v1.0。打 `v0.6` 标签，冻结新增玩法。
