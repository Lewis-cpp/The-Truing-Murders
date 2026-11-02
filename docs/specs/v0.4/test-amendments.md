# v0.4 测试修订记录

按规格第 9 节记录本阶段对验收测试的修改。目前仅一处机械格式修订，无断言、用例或测试数据变化。

## 2026-11-02：验收测试文件的导入排序

- 修改：`tests/agent_eval/test_npc01_live.py`、`tests/application/test_npc_context.py`、
  `tests/application/test_reply_guard.py`、`tests/infrastructure/test_llm_gateway.py`
  四个文件的 import 块按 isort 规则重排（`ruff check --fix`，规则 I001）。
- 原因：仓库的 lint 门槛（AGENTS.md、规格门槛清单）要求 `ruff check src tests` 通过，
  而随测试提供的文件导入块未排序，4 处 I001 使检查无法全绿。
- 依据：`docs/specs/agent-prompt.md` 门槛清单（`uv run ruff check src tests` 必须通过）；
  修改仅移动 import 语句，不涉及断言、用例、skip 或任何测试数据。
- 改成：同一批导入按字母序与分组重排；修改后四个文件仍以相同方式在收集期失败
  （缺失 `backend.infrastructure.llm_client` 等待实现模块），行为完全不变。
