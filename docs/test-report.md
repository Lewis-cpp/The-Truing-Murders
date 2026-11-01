# v1.0 测试报告

版本：代码 `ebb38b9`（分支 feat/v1.0-polish-release）；案件 `case_001 3-full`；规则执行版本 `full-1`；迁移 `0005`；模型输出协议 `npc-1`（真实模型评测未执行，见下）。

范围：第 14 篇 P0 矩阵全部 101 行（U-01～13、R-01～32、SM-01～14、AG-01～22、IT-01～20），逐行给出状态与覆盖。实际展开用例：后端 pytest 535 项（含参数化展开）、前端 35 项、浏览器 E2E 13 项（4 路径 + 5 可访问性 + 4 v0.6 路径）、性能 1 项。

状态口径：**通过** = 由下列自动化套件在真实 PostgreSQL 18 与真实浏览器上执行并断言；**不适用（部分）** = 该行内依赖的子能力按规格"不做"而未实现，其余子项已通过；**未执行** = 无。真实模型评测（live 套件）因无凭据未执行，属矩阵之外的补充评测，记录于 v0.4/v0.5/v1.0 交付记录。

| 编号 | 摘要 | 状态 | 覆盖 |
| --- | --- | --- | --- |
| U-01 | 合法案件、重复 ID/JSON 键、未知字段、缺固定回复、跨版本引用、内容摘要不符 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-02 | all/any 证据依赖的空集合、缺一项、全满足 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-03 | 条件树 all/any、未知 type、混合节点、深度 8/9、节点 128/129 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-04 | 数值边界 0/100，负增量、溢出、95 加 10 减 20 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-05 | pressure 39/40/69/70，trust 29/30，及 0/100 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-06 | 核心集合为空、部分层承认、全部核心承认、仅非核心承认 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-07 | 重复证据/效果来源、同键同效果、同键矛盾效果 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-08 | 隐藏证据、单端已持有关联、未披露关系、隐藏关键标记 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-09 | EXACT/RANGE/UNKNOWN、跨日/负分钟、同起点和矛盾证词 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-10 | 幂等载荷对象键顺序、集合顺序、过程顺序、目标/版本/文本变化 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-11 | 原状态对象与同一事件重复计算 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-12 | 指控空值、重复引用、未知选项、步骤证据不在所选集合 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| U-13 | 可知但不可说、可说但来源缺失、承认与 Discovery 不一致 | 通过 | backend/tests/domain/（规则与投影单元）：test_full_case_rules.py、test_case_v3_validation.py、test_rules.py |
| R-01 | 缺 E01 或 E03，S02 可调查 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-02 | 已持有 VERIFIED E07，尚未出示 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-03 | 未持有、其他版本同名证据、错误当前 NPC、锁定场景 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-04 | 合法持有但无关材料；或 E07 可信度不符 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-05 | F-VIDEO，反证为空 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-06 | F-VIDEO，反证齐全，L01 已 BROKEN | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-07 | F-VIDEO 初值 20/40 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-08 | 接 R-07 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-09 | 接 R-07 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-10 | F-LAYERS，持有两证据 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-11 | F-LAYERS 初始状态 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-12 | F-LAYERS，只承认行踪 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-13 | 任意已 ADMITTED 层 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-14 | 同证据匹配两个层；其中一层前置未满足 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-15 | NPC 已达数值上限 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-16 | pressure=95，同事件合法 +10、-20 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-17 | 同互斥组多条条件满足 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-18 | EVENT 获得新证据，PROGRESS 可据此解锁 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-19 | 同步批量承认、披露互相依赖 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-20 | 同效果键不同增量、相冲可信度、错误阶段动作 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-21 | 模型输出新证据、grant_evidence JSON、规则树、SQL 或工具调用 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-22 | 依赖死环、any 存在外部入口、数值不可达、反证仅靠本层承认取得 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-23 | F-MVP，全模型关闭 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-24 | J-GOLD-01，未触发招供 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-25 | J-GOLD-02/04/08 及关闭否决的版本 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-26 | J-GOLD-03/05/06/07 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-27 | 相同结构化答案；不同 explanation、评论、NPC 文本与承认状态 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-28 | 仅持有未引用、未核验证据、合法错误配对、伪造引用 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-29 | exact 与 ordered_subsequence 配置、重复步骤政策、阈值上下界、小数权重 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-30 | 已进入 REVIEW/FINISHED | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-31 | 空反证条件、any(always) 绕过、下一层缺前层守卫、空链、跨角色披露 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| R-32 | 同版本、同快照、同规范事件，不同系统时间和模型输出 | 通过 | backend/tests/domain/ 与 backend/tests/api/（规则、评分与 API 闭环）：test_full_case_rules.py、test_full_case_flow.py、test_interrogation.py |
| SM-01 | 合法创建；初始化各步骤分别失败 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-02 | 六个稳定状态 × 第 7.1 节全部操作 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-03 | I 中取得深入调查资格；T 中取得同一资格 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-04 | 无深入调查解锁；有解锁；证据分支两个集合均空 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-05 | I/D 开始审讯，T 切人/切同人/结束 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-06 | I/D/T 无证据、无承认时进入 A，再取消 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-07 | A 提交合法正确或错误指控；评分/保存异常 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-08 | R 完成复盘，再用新键重复完成 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-09 | R/F 尝试调查、改草稿、重新评分、向旧阶段倒退 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-10 | 构造 T 无当前 NPC、非 T 有 NPC、R 无判定、A 有正式判定等坏快照 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-11 | 发送内部事件名、phase 补丁；模型请求转移或招供 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-12 | 调查→审讯→切人→指控→取消→重入→结案→结束→重开 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-13 | 相同旧请求在 R/F/重开后重放，再用新键重做 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| SM-14 | PREPARING/GENERATING/FALLBACK 时切人、退出、进入 A 或重开 | 通过 | backend/tests/application/test_game.py、backend/tests/domain/test_phase_matrix.py、backend/tests/integration/test_database.py、test_save_and_constraints.py |
| AG-01 | 对 4 个 NPC 的每个有向角色对，另一人私密正文放唯一标记 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-02 | 混入他局、他角色、其他模板、Host/Review 的状态、历史或摘要 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-03 | 本人秘密未解锁、BROKEN、部分承认、完整授权 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-04 | 背包已持有但未出示、聊天声称持有、合法出示无关材料 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-05 | NPC02 证词作为预设证据合法出示给 NPC01；玩家直接粘贴秘密 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-06 | 伪造 SYSTEM/管理员、切 Host、要求忘记承认；注入放在问题/历史/摘要 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-07 | 假模型返回“我就是凶手”“获得新凶器”“压力已改为 100” | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-08 | JSON 残缺、重复 text、未知 actions、null/数值/空白 text、围栏、尾随文本、NaN、工具调用 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-09 | 合法 JSON 但泄密/翻供；合法预设谎言；长度 1200/1201、外壳超 64 KiB、截断/拒绝标记 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-10 | 连接/池等待、持续小块响应、整轮超时、上游 429/5xx/401、主备共配额 | 不适用（部分） | 备用路由"主备共配额"子项不适用：备用路由按 v0.4/v0.5 规格"不做"未实现；deadline、小块响应、429/5xx/401 子项由 test_llm_gateway.py 通过 |
| AG-11 | 部分承认后模型漏说、否认、超时或预算耗尽 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-12 | 合法 2,000 字符问题、必需授权超预算、主备窗口不同 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-13 | 预算不足、发出后未知、负数/错误类型 usage、迟到可靠 usage | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-14 | 初次失败后显式重试 1/2/3 次；内容违规后重试；旧 attempt 晚到 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-15 | 共用 Client 同时处理两个会话/两个 NPC | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-16 | 6/10/14 轮和稀疏 seq、当前轮、未完成/STALE/拒绝候选混入 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-17 | 60/100 轮中先承认一层，再换话题、裁剪、删除摘要、重启 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-18 | 授权变化、另一 NPC 不在场时披露变化、只改压力、切走再切回 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-19 | 摘要计算期间承认、并发维护、旧轮回复被重试替换 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-20 | 较早轮表达重试，后面已有普通聊天且业务版本相同 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| AG-21 | 请求 Review 未结案，Host 读取隐藏守卫，Judge 路径生成 | 不适用（部分） | Judge 路径生成子项不适用：评分零 LLM 为规格要求；Review 拒绝与 Host 守卫子项通过 |
| AG-22 | 响应/日志/Polling/可访问性播报中埋测试秘密、Prompt 和凭据标记 | 通过 | backend/tests/application/（test_npc_context、test_reply_guard、test_memory）与 backend/tests/infrastructure/test_llm_gateway.py、backend/tests/api/（test_generation、test_four_npcs、test_long_conversation） |
| IT-01 | Game → Rules → Database → Conversation | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-02 | 取证、出示、承认、epoch 和投影 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-03 | 写证据后、写效果键前 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-04 | 写 NPC、披露、请求、对话占位、版本过程中 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-05 | COMMIT 已成功，HTTP 响应丢失 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-06 | 同访问者同键相同输入并发 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-07 | 同键异输入；不同键同旧版本的两个有效变更 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-08 | 新键重复出示、另一新条件随后满足 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-09 | 普通聊天不改业务版本，同局并发聊天/出示/重试 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-10 | 两个正式指控并发；判定写入中断 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-11 | 重开过程失败；成功重开后旧响应晚到 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-12 | 持久化存档、发布新版、下架旧版、缺失/不兼容定义 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-13 | 复合外键、唯一键、CHECK、运行账号权限 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-14 | 额度预留与派发竞态 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-15 | 已派发后进程中断、表达落库失败、旧 attempt 晚到 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-16 | LLM 事务外等待、连接池/锁等待/死锁、DB 不可用 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-17 | 恢复跨多个表读取时另一连接提交变更 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-18 | 摘要 CAS 与业务事务 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-19 | 幂等记录、效果、消息、计量跨重启保留 | 通过 | backend/tests/integration/（test_recovery_drills、test_concurrency、test_database）与 backend/tests/e2e/ |
| IT-20 | 一致性逻辑备份和真实恢复 | 通过（手动演练） | 自动化测试因 PATH 无 pg_dump 18 按规格 skip（原因已写明）；演练命令与结果见 docs/22-v0.6-delivery.md |

## 汇总

- 通过：99 行（其中 1 行为手动演练，自动化部分因无 pg_dump 18 按规格 skip）
- 不适用（部分）：2 行（AG-10、AG-21 的备用路由与 Judge 生成子项，规格"不做"；其余子项通过）
- 未通过：0 行；未执行：0 行（真实模型评测在矩阵之外，未执行并如实记录于 v0.4/v0.5/v1.0 交付记录）

## 执行环境

- 本机：Linux x86_64（20 核）、Python 3.12.15、Node.js 24、PostgreSQL 18.6（Docker）。
- 命令：后端 `uv run ruff format --check src tests && uv run ruff check src tests && uv run pytest -q && uv run alembic check`；前端 `npm run format:check && npm run typecheck && npm run lint && npm test && npm run build`；`uv run pytest tests/e2e -m e2e`、`uv run pytest tests/performance -m performance`。

各版本的详细验证记录见 docs/19～22 的交付记录与 docs/23-v1.0-delivery.md。
