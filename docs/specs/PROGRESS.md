# 实现进度

编码 Agent 每轮开始先读本文件，每轮结束前更新它。只写事实：做了什么、哪些检查通过或失败、下一步、阻塞。
新会话从“下一步”接着做，不重做已提交的工作。

## 当前状态

- 当前阶段：v0.3（实现中）
- 当前分支：feat/v0.3-full-case
- 最近一次完整检查：基线（2026-11-02）：后端收集 205 项通过（不含 v0.3 验收集，收集期即失败）；
  v0.3 验收集因缺 `AccusationDraft` 等新名字在收集期失败；前端 25 项中 19 过 6 败（新 full-case.test.ts）。
- 已打标签：v0.2

## 阶段清单

| 阶段 | 验收测试已启用 | 实现 | 全部检查通过 | 交付记录 | 标签 |
| --- | --- | --- | --- | --- | --- |
| v0.3 | 否 | 否 | 否 | 否 | 否 |
| v0.4 | 否 | 否 | 否 | 否 | 否 |
| v0.5 | 否 | 否 | 否 | 否 | 否 |
| v0.6 | 否 | 否 | 否 | 否 | 否 |
| v1.0 | 否 | 否 | 否 | 否 | 否 |

## 下一步

1. T10：`domain/models.py` 换成 schema 3（characters/scenes/evidence/knowledge/lies/lie_chains/
   relationships/timeline/interrogation/deep_unlock），`GameState.npcs`、`AccusationDraft`；
   `application/case.py` 的 `validate_case` 按 2.2 全部拒绝规则重写；`default_case_path`、
   force-include 指向 case.json，删除 slice.json。
2. T10 移植：v0.2 旧测试（test_rules/test_case_validation/test_game 等）改写到新结构；
   `week_one_verdicts.json` 与切片专属用例被验收测试覆盖后删除，记入 test-amendments.md。
3. T11：`rules.py`（open_scenes/multi-npc present 四步求值/ask_topic/contradict/save_draft/judge）、
   `state_machine.py`（display_state/admission_progress）、`evidence.py`（current_statement）。
4. T12：迁移 0003（relationship、timeline_event、conversation、conversation_message、
   character 新列、scene.unlock、evidence.kind/is_key、lie 的链信息）；case_repository 双向映射；
   session_repository 多 NPC 存取；草稿存 state_json["accusation_draft"]。
5. T13：application/sessions.py 新命令与投影；api 新 GET 端点（scenes/evidence/npcs/relationships/
   timeline/accusation-options/accusation-draft/conversations）；前端 GameView 按 data-testid 契约改版。
6. T14：CLI 改读 case.json；README 更新；交付记录 docs/19-v0.3-delivery.md；打 v0.3 标签。

## 阻塞与需要人处理的事项

- （无）

## 轮次日志

<!-- 每轮追加一条：日期、阶段、提交范围、通过/失败数量、要点。最新的在最上面。 -->

- 2026-11-02 · v0.3 · d3341a2..58d79f7（specs+case.json 入库；启用 v0.3 验收测试）。
  基线：后端 205 收集通过、验收集收集期失败；前端 19 过 6 败。下一步 T10。
