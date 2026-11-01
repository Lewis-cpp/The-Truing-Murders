# v0.6 测试修订记录

按规格第 8 节记录本阶段对验收测试的修改。目前仅一处测试管线（harness）修订，断言与演练意图零变化。

## 2026-11-02：故障演练 1 的访客 Cookie 同步时点

- 修改：`tests/integration/test_recovery_drills.py::test_a_presentation_failing_after_its_round_is_written_leaves_nothing`
  中把 `tolerant.cookies = client.cookies` 从"创建 tolerant 客户端时"移到
  `player.client = tolerant` 之后（加注释说明），其余一行未动。
- 原因：httpx 在赋值 Cookie jar 时做拷贝。原语句执行时 `player.start()` 还没运行，
  jar 为空；交换客户端后演练请求缺少访客 Cookie，得到 401 `VISITOR_AUTH_REQUIRED`
  而不是被测的故障注入响应——演练本体（触发器注入、503 `PERSISTENCE_UNAVAILABLE`、
  原子回滚、原键重试）完全无法被执行。
- 依据：规格第 4 节对该演练的期望（出示事务失败后全部不落库、原键重试成功且只生效一次）；
  修订只修 harness 时点，全部断言保持原样。
- 改成：在演练请求发出前重新同步 Cookie（此时开局已完成，jar 非空）。修订后
  演练通过：503、零残留、404 查询、原键重试只生效一次全部按规格成立。

## 2026-11-02：前端 UI 驱动测试迁移到 v0.6 表单契约

- 修改：`frontend/tests/interrogation.test.ts` 中三处测试的"驱动方式"：
  1. `points out a contradiction`：出示下拉框被 `present-{id}` 按钮取代后，
     `findAllComponents(ElSelect)` 的下标从 `[, cited, against]` 改为 `[cited, against]`。
  2. `warns about irrelevant moves…`：旧"选择证据 + 出示按钮"两步改为点击
     `data-testid="present-E03"`。
  3. `starts a restarted game…`：旧"选择证据 + 出示"与 ElPopconfirm 确认，改为
     `present-E03` 按钮存在性断言与 `restart-game` → `confirm-restart` 两步确认。
- 原因：v0.6 规格第 3 节明确"为浏览器 E2E 固定表单控件（替换 v0.3 的实现细节）"，
  出示下拉与重启 Popconfirm 属于被替换的实现细节；这些测试按组件内部结构
  （ElSelect/ElPopconfirm 实例）驱动，替换后必须改用新的 `data-testid` 契约。
- 依据：`docs/specs/v0.6/spec.md` 第 2、3 节（组件 testid 与表单契约）。
- 改成：只改驱动方式与控件定位；全部业务断言（请求载荷、版本头、提示文案、
  状态断言）保持原样，无一放宽。
