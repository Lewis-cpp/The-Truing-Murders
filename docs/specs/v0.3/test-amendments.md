# v0.3 测试修订记录

按规格第 8 节记录本阶段对既有测试的移植与删除。v0.3 验收测试本身未做任何修改。

## 2026-11-02：切片时代测试的移植与删除

依据：`docs/specs/v0.3/spec.md` 第 8 节（“v0.2 已有测试中依赖 `case.npc`、`case.lie`、`state.npc`、
`S01` 固定场景的，移植到新结构；`week_one_verdicts.json` 与切片专属用例在被上表覆盖后删除，
并记入本文件”）。

- 删除 `backend/tests/data/expected/week_one_verdicts.json`（13 组切片评分预期）。
  覆盖它的验收测试：`backend/tests/domain/test_full_case_rules.py::test_hand_written_verdicts`
  与 `backend/tests/api/test_full_case_flow.py::test_hand_written_verdicts_over_http`
  （数据源为 `full_case_verdicts.json` 的 13 组全案人工预期）。
- `backend/tests/domain/test_rules.py`：切片专属用例（六种出示顺序、无关与回避、话题、矛盾、
  情绪边界、评分样例、最坏代价）已被验收测试覆盖，删除；保留并移植验收测试未覆盖的行为：
  未核验证据不产生效果也不击破、仅信任门槛的承认路径、代价在 0 处截断且键被消费、
  承认与出示记录跨审讯保留、数值上限不替代反证。
- `backend/tests/domain/test_case_validation.py`：切片案件的发布校验用例被
  `test_case_v3_validation.py`（2.2 全部拒绝规则）覆盖，删除；保留并移植
  `Dependency.all_of/any_of` 语义、加载与当前目录无关、非法 JSON 拒绝、缺文件报错。
- `backend/tests/application/test_game.py`：移植到多场景多人物结构（阶段原子性、
  非法目标、指控取消、非法提交、关联校验、结案冻结、独立开局、重复授予、视图不含隐藏内容）。
- `backend/tests/test_cli.py`：移植到 `case.json` 全案（离线通关 100 分、取消与纠错、
  话题矛盾与回避、EOF 安全、入口与坏案件文件）。
- `backend/tests/player.py`：由验收测试自带版本覆盖（v0.3 注释为“scenes are resolved from
  the action ID”），属于规格提供的替换，不是断言修改。
