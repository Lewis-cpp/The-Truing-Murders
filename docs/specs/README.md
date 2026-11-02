# 分阶段实现规格

本目录把 [一人开发计划](../16-development-roadmap.html) 中的 v0.3～v1.0 拆成可直接实施的规格。
每个阶段一个 `spec.md`，另附该阶段的验收测试（`tests/`），供实现者（人或编码 Agent）按顺序完成。
截至 2026-11-02，各阶段规格实现与本地自动化验收已完成；发布状态与未执行项见 [实现进度](PROGRESS.md)。

设计依据仍是 `docs/01～15`；本目录只做两件事：

1. 在设计文档留有选择余地的地方**定下唯一做法**，包括 JSON 结构、函数签名、HTTP 字段和测试钩子；
2. 写明每个阶段的完成定义、验收命令和不做的事。

两者冲突时，以本目录的阶段规格为准，并在该阶段交付记录中说明差异。

## 阶段与门槛

| 阶段 | 规格 | 任务 | 门槛（不过不进下一阶段） |
| --- | --- | --- | --- |
| v0.3 完整案件，固定回复 | [v0.3/spec.md](v0.3/spec.md) | T10～T14 | 全案固定模式三结局、无招供正确路径、12 证据可达全部通过，打 `v0.3` 标签 |
| v0.4 单角色 AI | [v0.4/spec.md](v0.4/spec.md) | T15～T18 | 沈砚一人接入模型；假传输覆盖全部故障；业务结果与固定模式一致 |
| v0.5 四角色 + Memory | [v0.5/spec.md](v0.5/spec.md) | T19～T21 | 四角色隔离、100 轮有界、承认不回退、额度耗尽可结案 |
| v0.6 完整 MVP | [v0.6/spec.md](v0.6/spec.md) | T22～T24 | FR-01～19 有证据；浏览器 E2E；5 会话 P95 记录；可部署 |
| v1.0 美化与发布 | [v1.0/spec.md](v1.0/spec.md) | T25～T27 | 可访问性、全新环境复现、P0 矩阵全过、报告真实 |

编码 Agent 的启动与续跑提示词见 [agent-prompt.md](agent-prompt.md)；跨会话进度记在 [PROGRESS.md](PROGRESS.md)。
全案正式配置 `backend/assets/cases/case_001/v1/case.json` 已随规格提供，它与各阶段的 expected 文件同属人工预期。

## 验收测试的存放与启用

验收测试按**最终落点的相对路径**存放在 `docs/specs/<阶段>/tests/` 下，例如
`docs/specs/v0.3/tests/backend/tests/domain/test_full_case_rules.py` 最终位于
`backend/tests/domain/test_full_case_rules.py`。

启用一个阶段时：

```bash
# 在仓库根目录执行；cp -r 会覆盖同名文件（例如 backend/tests/player.py）
cp -r docs/specs/v0.3/tests/. .
git add backend/tests frontend/tests
git commit -m "Add v0.3 acceptance tests"
```

规则：

- **先提交测试、再写实现**。这对应路线图的“人工预期早于实现提交”。
- 验收测试是需求，不是草稿。实现者不能为了通过而改断言、删用例、加 `skip`/`xfail`。
  确认测试本身写错（与本规格或设计文档矛盾）时，可以修，但必须在同一提交里写明原因，
  并追加到该阶段的 `docs/specs/<阶段>/test-amendments.md`。
- 已有测试（v0.1/v0.2）依赖切片专有结构的，按阶段规格要求移植。只有被新验收测试完整覆盖时才能删除，
  删除时在 `test-amendments.md` 里写明由哪个新用例覆盖。
- 后一阶段的验收测试不提前放进 `backend/tests`/`frontend/tests`，避免把 CI 弄红。

## 通用约定（所有阶段）

- 分层沿用 `api / application / domain / infrastructure`，依赖方向见 [第 15 篇](../15-development-plan.md)。
  domain 不导入 SQLAlchemy、FastAPI 或任何模型 SDK。
- 每次写请求一个短事务；幂等、版本、阶段校验的顺序沿用 v0.2 的 `GameService._execute`。
- 公开响应只走 allowlist 投影（`application/views.py` 与 `api/schemas/responses.py`）。
  任何响应都不能包含：精确 pressure/trust、阈值、谎言层 ID、链 ID、未来说法、`truth`、评分条件、
  `is_key`（除非案件允许并经 `key_badge` 投影）、Prompt 原文、模型原始候选。
- 默认 CI 不访问网络模型。真实模型评测只在 `RUN_LIVE_LLM_TESTS=1` 且标记 `live_llm` 时运行。
- 每个阶段结束都要：干净环境按 README 启动 → 跑全部检查 → 写交付记录
  `docs/19-v0.3-delivery.md`、`docs/20-v0.4-delivery.md`…（沿用 17、18 的格式）→ 打标签。
- 每个阶段的完成检查命令（在对应子目录内）：

```bash
cd backend
uv run ruff format --check src tests
uv run ruff check src tests
uv run pytest -q
uv run alembic check

cd ../frontend
npm run format:check
npm run typecheck
npm run lint
npm test
npm run build
```
