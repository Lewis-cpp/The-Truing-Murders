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
