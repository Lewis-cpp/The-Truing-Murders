# FastAPI REST API 设计

本文依据 [项目范围](01-project-scope.md)、[需求分析](02-requirements-analysis.md)、[总体架构](03-architecture-design.md)、[领域模型](04-domain-model.md)、[状态机](05-state-machine.md)、[证据引擎](06-evidence-engine.md)、[Agent 设计](07-agent-design.md)、[谎言机制](08-lie-system.md) 和 [数据库设计](09-database-design.md)。这是接口契约设计，不代表后端已经实现。

**API 按案件、游戏会话、调查、NPC 交互和指控等业务资源组织。程序提交权威结果后再生成表达，前端通过普通 HTTP 读取结果；Agent、规则执行器和数据库表不直接成为玩家 API。**

## 1. 设计基线与命名

| 项目 | 约定 |
| --- | --- |
| 基础路径 | `/api/v1`；本文最后的 API 表全部使用完整路径 |
| 路径命名 | 小写英文名词；多词资源使用连字符，如 `evidence-presentations`；集合通常用复数 |
| 单例资源 | `interrogation`、`accusation-draft`、`accusation`、`review` 等在一个会话中最多一份，使用单数；`evidence` 为不可数名词 |
| JSON 与参数 | 字段使用 `snake_case`；枚举使用大写，如 `INTERROGATION`、`VERIFIED` |
| 读取 | GET 无请求体，不执行业务规则、不自动保存草稿、不发起模型调用 |
| 创建业务记录 | POST 创建会话、调查记录、对话轮次、证据出示记录或正式指控 |
| 设置单例 | PUT 完整设置当前审讯、指控准备状态或草稿；不是任意状态补丁 |
| 结束临时活动 | DELETE 当前审讯或指控准备资源；不删除历史、NPC 进度或已保存草稿 |
| 标识 | 会话、请求、对话、消息使用 UUID 字符串；案件、场景、NPC、证据和选项 ID 使用版本内业务标识 |
| 时间 | 审计时间使用 UTC 的 RFC 3339 字符串，例如 `2026-09-22T14:00:00Z`；案件时间线另用案内相对分钟 |
| 响应类型 | JSON 使用 `application/json`；响应采用本文明确的 DTO，不直接序列化 ORM 或完整案件定义 |
| MVP 通信 | 普通 HTTP、对话结果轮询；不增加 WebSocket、SSE、Redis 或通用任务平台 |

对外统一使用 `npc_id`，应用层映射到领域和数据库中的 `character_id`。受害者等非可审讯人物可出现在关系图节点中，但不能通过 NPC 交互接口审讯。

游戏阶段以第 05 篇为准，物理存储和时间字段以第 09 篇为准。初始化与判定瞬态不出现在可读取的会话状态中。接口资源不要求新增同名表，例如调查记录与证据出示记录复用 `action_request`、`game_event_log`，指控准备状态由 `phase` 表示。

## 2. HTTP 与通用契约

### 2.1 匿名身份与会话归属

MVP 使用同源匿名访问者 Cookie，不引入注册、登录和账号体系。

1. 前端先调用 `POST /api/v1/visitors`，请求体为 `{}`。无有效凭据时签发高熵令牌，设置 `HttpOnly; Secure; SameSite=Lax; Path=/` Cookie；数据库仅保存令牌摘要。
2. 已有有效 Cookie 时返回同一访问者的当前入口，不轮换令牌、不创建新会话。新建访问者返回 201，复用返回 200。响应只含 `current_session_id`，不在 JSON 返回令牌或摘要。
3. 除案件列表、公开案件简介及初始化访问者外，所有接口必须认证。服务端用 Cookie 查归属，不接受请求体中的 `visitor_id` 代替认证。
4. 所有写请求校验同源 `Origin`。初始化访问者也执行该校验；来源缺失或不在允许范围内返回 `403 ORIGIN_NOT_ALLOWED`。
5. 已认证但目标属于其他访问者时，与目标不存在返回相同的 404。子资源同时校验会话、NPC 和案件版本归属。
6. 每个访问者只有一个 `current_session_id`。旧局仍可读取；新的业务写入必须针对当前局，否则返回 `409 SESSION_NOT_CURRENT`。

访问者初始化是唯一不使用业务幂等键的写入口：它发生在访问者身份建立之前，也不创建游戏、消耗模型额度或改变调查状态。首次响应连同 Cookie 丢失时，重试可能留下一个没有游戏的访问者记录；前端取得 Cookie 后才能提交开局请求，避免把这种不确定性带入游戏创建。

匿名凭据丢失后不能凭 `session_id` 找回旧局。受保护响应使用 `Cache-Control: no-store`，不得通过共享缓存暴露存档。

### 2.2 请求头与输入约束

| 输入 | 适用范围 | 约束 |
| --- | --- | --- |
| `Content-Type: application/json` | 有 JSON 请求体的写接口 | DELETE 不带请求体，版本和幂等信息走请求头 |
| `Idempotency-Key` | 除访问者初始化外的所有 POST、PUT、DELETE | 客户端生成 UUID，对应内部 `request_id`；一次用户操作固定一个值 |
| `X-Expected-State-Version` | 所有已有会话的写操作，包括聊天与表达重试 | 正十进制整数，对应内部 `expected_state_version`；必须等于锁内当前版本 |
| 新局版本头 | 首次创建会话 | 不发送；创建事务生成初始版本 1 |
| 重开版本头 | 创建请求带 `replaces_session_id` | 必须发送，校验被替换的旧局版本；不是新局的版本 |
| `X-Trace-ID` | 每个 HTTP 响应 | 服务端生成，仅用于排障；与业务幂等键不同 |

采用独立版本头是为了避免在 DELETE 中携带 JSON，也避免把游戏状态计数误当成整个 HTTP 表示的 ETag：普通聊天和表达更新不会递增 `state_version`。

请求模型拒绝未知字段。全局 UUID 参数必须可解析；版本内 ID 为 1～64 个 ASCII 字母、数字、下划线或连字符，大小写敏感；`case_version` 为 1～32 个安全版本字符，允许字母、数字、点、下划线和连字符。JSON 整数不接受布尔值、字符串或浮点数。

聊天 `message` 为 1～2,000 个 Unicode 字符且不能全为空白；出示附言 `comment` 为 0～1,000 字符；指控 `explanation` 为 0～5,000 字符。单个 JSON 请求体上限暂定 64 KiB，超限返回 413。字符限制是输入协议，不等于模型 token 预算；输入合法但上下文放不下时使用固定回复，不截断玩家文字。

### 2.3 成功响应与分页

不再增加 `success: true`、`code: 0` 等重复 HTTP 状态的外层。读取资源直接返回本文 DTO；会话子资源统一使用：

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "state_version": 8,
  "data": {
    "items": []
  }
}
```

下文记为 `View<T>`：`data` 的类型为 T，`state_version` 表示本次读取的一致快照。不是要求新建一个通用查询框架。

- 案件列表以及每局少量场景、证据、NPC、关系、时间事件直接全量返回，空集合为 `[]`。
- NPC 对话历史使用 `limit`，默认 20、范围 1～50；`before_seq` 为可选正整数，读取该 NPC 且 `conversation_seq < before_seq` 的最近若干完整轮次。
- 首次读取最近一页，各页的 `items` 按 `conversation_seq` 升序返回，便于聊天显示；还有更早记录时 `next_before_seq` 为本页最小序号，否则为 null。
- `conversation_seq` 是整局严格递增序号，同一 NPC 的序号可以不连续。分页不以 `state_version` 或时间戳作为轮次顺序。
- 每个聚合读取使用一致的只读快照。多个 HTTP 响应版本不同，前端不得拼成一份权威快照；需要整体刷新时读取会话详情。

### 2.4 统一错误响应

```json
{
  "error": {
    "code": "STATE_VERSION_CONFLICT",
    "message": "游戏进度已更新，请刷新后重试。",
    "details": {
      "expected_state_version": 7,
      "current_state_version": 8
    },
    "retryable": false,
    "trace_id": "00000000-0000-4000-8000-000000000099"
  }
}
```

下文 `ApiError` 指 `error` 内部的对象；失败 HTTP 响应统一为 `{"error": ApiError}`，`RequestRecord.error` 直接使用该内部对象。`code` 是稳定机器码，前端按它处理；`message` 是可本地化提示。`details` 只返回已授权字段，例如当前阶段、版本及表单错误位置，不包含隐藏条件、正确选项、秘密 ID、Prompt、SQL、堆栈或供应商原始响应。

422 的字段错误形状为 `details.fields: [{"path":"body.message","code":"TOO_LONG","message":"最多输入 2000 个字符。"}]`。不回显完整非法输入。`retryable=true` 只表示可按第 3 节重试同一请求，绝不表示可以换一个幂等键盲目再执行。

## 3. 幂等、并发与生成语义

### 3.1 请求幂等

幂等唯一键为 `(visitor_id, request_id)`，保存于第 09 篇的 `action_request`，有效存档期间保留。摘要包含 HTTP 方法、规范路径及原目标、预期版本和校验后的规范化业务载荷；补齐模型默认值，对集合规范排序，保留作案步骤顺序及文本内容，不包含 Cookie 和 Trace ID。

| 场景 | 处理 |
| --- | --- |
| 相同键、相同输入，原请求成功 | 返回原成功状态码与固定结果；只允许关联对话的表达状态更新，不重复执行规则或生成 |
| 相同键、不同路径、目标、版本或载荷 | `409 IDEMPOTENCY_KEY_CONFLICT` |
| 已记录的拒绝请求再次提交 | 返回同一拒绝；修改内容或解决阶段、版本冲突后，使用新键发起新操作 |
| 相同请求并发到达 | 锁内再次查重，依靠唯一约束保证只提交一份；后到者读取已提交结果 |
| 事务尚未提交，结果查询找不到 | 返回 `404 REQUEST_NOT_FOUND`；不代表已证明原请求不会提交，重发仍使用原键与原载荷 |
| 网络断开或 5xx，提交结果不确定 | 先查原请求；仍未知时以原键原载荷重试，不能自行宣布未保存 |
| 已成功请求在结案、重开后重发 | 归属验证后返回原结果，不重新按新阶段拒绝，也不切回旧局入口 |

认证、归属与基本结构检查之后，**幂等查询先于当前入口、版本、阶段和生成忙碌检查**。这些后续限制只判断新的业务操作。响应固定部分保存于 `result_json`；原 HTTP 状态码应一并保存，查询时不靠当前状态猜测。

`GET /api/v1/requests/{request_id}` 只在当前访问者的命名空间中查找，覆盖首次创建尚未取得 `session_id` 的断线恢复。返回 `RequestRecord`，查询本身始终为 200；原请求失败通过记录内的 `status=REJECTED`、`original_http_status` 和 `error` 表达。

输入结构、认证失败等在业务受理前拒绝的请求可无 `action_request`；通过结构与归属校验后的领域拒绝保存为 `REJECTED`。幂等键冲突不覆盖原记录。临时数据库失败不保存一个永久拒绝结果。

### 3.2 业务效果去重与版本

请求去重不能替代业务效果去重。新键再次调查或出示已持有证据，仍按当前状态重新求值；`rule_effect` 和持有唯一键阻止重复发放与重复加压。不能把“已经出示过”当成整条谎言以后都不再检查。

| 操作结果 | `state_version` |
| --- | --- |
| 开局成功 | 从 0 建立为 1 |
| 阶段、当前 NPC、草稿、证据、已知信息或规则输入发生有效变化 | 一个业务事务只加 1 |
| 首次向该 NPC 合法出示证据，即使没有匹配谎言 | 加 1，因为 NPC 已见材料的范围发生变化 |
| 普通问答、表达保存、额度结算、读取、纯重复且无新效果 | 不变 |

同一会话写入先取得数据库行锁，锁内比较版本并计算结果；重开统一按 visitor → session 的顺序取锁。并发不同请求即使各有幂等键，也不能跳过版本校验。普通问答另受生成占位约束，不能只靠不会变化的 `state_version` 限制并发。

### 3.3 业务提交和 NPC 回复分别完成

聊天与出示证据均在业务事务提交后立即返回 **201**：表示一轮交互及其固定结果已经创建，不表示模型已经回答。`Location` 指向本局 `/conversations/{conversation_id}`，前端轮询该资源，不重发聊天 POST。

`ActionResult<T>` 的固定字段如下：

| 字段 | 类型与含义 |
| --- | --- |
| `request_id`、`session_id` | 本次业务请求 UUID、所属或新建会话 UUID |
| `business_status` | `COMMITTED` 或 `NOOP`；普通聊天创建新轮次属于 COMMITTED，纯重复业务效果可为 NOOP |
| `state_changed` | 是否改变游戏状态；不能通过 COMMITTED 推断版本一定增加 |
| `state_version_before`、`result_state_version` | 本次提交前后版本；创建前为 0 |
| `phase_after`、`active_npc_id_after` | 本次提交后的阶段与当前 NPC，可为空的仅是 NPC ID |
| `saved_at` | 本次结果对应的业务保存时间；无游戏状态变化时保留原值 |
| `data` | 当前端点明确定义的固定业务结果 T |
| `conversation` | NPC 交互附带的 `ConversationView`，其他端点为 null；重放时可读取该轮最新表达 |

业务状态与生成状态采用两个独立枚举：

| `generation_status` | 可展示内容 | 前端行为 |
| --- | --- | --- |
| `PREPARING` | 已保存固定结果与 `fixed_reply` | 显示“回复准备中”，可继续读数据 |
| `GENERATING` | 已保存固定结果与 `fixed_reply` | 轮询当前对话 |
| `COMPLETED` | 通过验证的 NPC 回复 | 停止轮询 |
| `FALLBACK` | 与本轮权限一致的固定回复 | 停止轮询；按 `can_retry_reply` 决定是否提供显式重试 |
| `STALE` | 历史固定结果；已通过验证的历史消息可保留 | 停止轮询，不将迟到候选当作当前回复；不能重试旧上下文 |

业务请求没有公开的长期 `PROCESSING` 状态，生成占位位于 `conversation`。MVP 可以在应用内继续执行已登记任务，但恢复依靠数据库记录与截止时间；进程中断后不能自动重发可能已计费的模型调用。

前端建议每 1～2 秒查询当前对话，离开页面即停止；轮询不续期、不扣模型额度。超过截止时间时返回 `deadline_exceeded=true` 和固定回复，前端停止轮询；服务端维护流程在独立短写事务内将过期轮次降级，不让 GET 重新派发生成。

同局已有未过期 NPC 生成时，新的聊天、出示和表达重试在任何规则效果提交之前返回 `409 GENERATION_BUSY`。受理新生成前可在会话锁内清理已过期占位，按原尝试状态保留未知用量，再判断是否可受理；不能因进程曾中断而永久忙碌。切换 NPC、退出审讯、进入指控、重开仍可执行，并在相应事务中使旧生成失效。释放逻辑占位不等于取消上游计费。

### 3.4 表达失败与重试

`POST /sessions/{session_id}/conversations/{conversation_id}/reply-retries` 创建一条业务重试记录，返回 201，`Location` 指向本次 `/requests/{request_id}`，响应关联原 `conversation_id`。它只补充该 NPC 轮的表达，不重新调查、出示、承认或评分。

新重试必须满足：原轮属于本局 NPC、状态为 FALLBACK、当前局和当前 NPC 未变、阶段仍为 INTERROGATION、原 `source_state_version` 等于当前版本、无其他生成占位、额度允许。成功回答不允许反复抽取新版本；STALE 或仅在读取时发现过期而尚未完成清理的轮次不可直接重试。

模型超时、上游限流、输出违规或额度耗尽，不把已提交的聊天或出示改成 HTTP 失败：返回/查询既有成功资源，`generation_status=FALLBACK`。显式申请新生成而已知额度不足时，才在受理前返回 `429 GENERATION_BUDGET_EXHAUSTED`。固定回复、调查、指控和复盘继续可用。

## 4. Session 状态合法性

缩写仅用于文档：I = `INVESTIGATION`，D = `DEEP_INVESTIGATION`，T = `INTERROGATION`，A = `ACCUSATION`，R = `REVIEW`，F = `FINISHED`；S 表示这六个持久化状态的集合。

所有写操作先遵循第 3 节的旧请求重放规则，再校验当前会话入口和下表。任何没有声明的转换默认拒绝，不能通过请求体提交 `phase` 或 `target_phase`。

| 业务能力 | 合法当前状态 | 结果与守卫 |
| --- | --- | --- |
| 加载会话、读取已知信息、历史、原请求 | S，包括自己的旧局 | 只读；不重放规则、不切换当前入口 |
| 调查场景 | I、D | 场景开放、动作存在且可执行；首次成功动作同时登记 visited |
| 设置当前审讯 NPC | I、D、T | NPC 可接触；进入 T 或切换目标；同一目标为 NOOP |
| 结束当前审讯 | T；I、D 可重复结束 | T 返回 I/D 并清空目标；已在 I/D 为 NOOP |
| 聊天、出示证据、回复重试 | T | URL 中 NPC 必须等于 active_npc_id；重试另检查原轮版本和状态 |
| 进入指控准备 | I、D、T；A 可重复进入 | 转 A、清空当前 NPC，保留或建立空草稿；不要求证据或招供 |
| 读取指控候选与草稿 | S | 只返回公开候选与本局已有草稿；读取不进入 A |
| 保存草稿 | A | 字段可以不完整，但已填写的引用必须合法 |
| 退出指控准备 | A；I、D 可重复退出 | 返回 I/D，保留草稿；不自动回到之前的审讯 |
| 提交正式指控 | A | 字段完整、引用合法、明确确认；同步判定并原子进入 R |
| 查看正式指控、完整复盘 | R、F | 正式记录与阶段必须一致；不得为未结案局披露真相 |
| 标记复盘完成 | R；F 可重复完成 | R → F；只改完成时间、阶段和版本，F 为 NOOP |
| 明确重开 | 当前旧局为 S | 创建独立新局并切换入口；旧局数据保留，旧生成失效 |

返回 I 或 D 由已保存的深入调查里程碑决定，客户端不能指定。首次解锁深入调查时，I 自动进入 D；T 中只登记里程碑，不中断审讯。所有 GET，包括场景详情，都不记录 visited；本版将它定义为“已实际执行成功调查”，不另做页面浏览写接口。

R/F 已冻结调查数据与判定。API 没有将结案局恢复为调查、修改分数、重置谎言或直接授予证据的入口。`PUT /review-completion` 重复读取式提交也必须带当前版本；同幂等键重放则返回原结果。

## 5. 玩家可见响应模型

### 5.1 案件、会话与加载

| DTO | 字段与边界 |
| --- | --- |
| `VisitorView` | `current_session_id: UUID\|null` |
| `CaseSummary` | `case_id`、`case_version`、`title`、不剧透的 `synopsis`；每案只列服务端当前允许新开的已发布版本 |
| `CaseList` | `items: CaseSummary[]`，按服务端展示顺序稳定返回 |
| `SessionSummary` | `session_id`、`case_id`、`case_version`、`title`、`phase`、`state_version`、`active_npc_id`、`is_current`、`created_at`、`saved_at`、`closed_at`、`finished_at`、`available_actions`；未发生时间为 null |
| `SessionView` | `session: SessionSummary`、`intro_text`、`scenes: SceneView[]`、`evidence: EvidenceView[]`、`npcs: NpcView[]`、`known_information: KnownInformation[]`、`relationships: RelationshipGraph`、`timeline: TimelineView`、`accusation_draft: AccusationContent`、`pending_conversations: ConversationView[]` |
| `CurrentSessionView` | `current_session_id`、`session: SessionView\|null`；没有当前局时两者均为 null，仍为 200 |
| `RequestRecord` | `request_id`、`status: COMMITTED/NOOP/REJECTED`、`original_http_status`、`result: ActionResult\|null`、`error: ApiError\|null`；成功只有 result，拒绝只有 error |

`SessionView` 是整体加载的安全投影，不是数据库快照导出。对话历史另外分页读取，正式结果与完整真相通过专用结案资源读取。旧局 `is_current=false`，`available_actions=[]`；GET 不把它重新激活。底层草稿为 null 时，所有读取均投影成第 6 节的空字段和空集合对象，不因此写库；草稿单例从开局起即可读取。

`available_actions` 只使用业务能力枚举：`INVESTIGATE`、`SET_INTERROGATION`、`END_INTERROGATION`、`CHAT`、`PRESENT_EVIDENCE`、`OPEN_ACCUSATION`、`SAVE_ACCUSATION_DRAFT`、`CANCEL_ACCUSATION`、`SUBMIT_ACCUSATION`、`FINISH_REVIEW`、`RESTART`。它按当前权限筛选，用于展示入口，不携带隐藏条件；调用实际接口时仍重新校验。具体场景动作另见 `SceneView.actions`。

案件下架不改变旧局绑定版本，兼容的旧存档仍可加载。缺失定义、快照不兼容或记录不一致时明确拒绝，不偷偷换成最新版。

### 5.2 场景、证据与 NPC

| DTO | 字段与边界 |
| --- | --- |
| `SceneView` | `scene_id`、`name`、授权 `description`、`visited`、`actions: InvestigationOption[]` |
| `InvestigationOption` | `action_id`、`label`、`completed`、`enabled`、`disabled_reason: string\|null`；只列已公开动作，禁用原因不披露隐藏前置证据 |
| `InvestigationResult` | `scene_id`、`action_id`、`outcome: PlayerOutcome` |
| `EvidenceView` | `evidence_id`、`name`、`kind`、`content`、`source: PublicSource`、`credibility`、`discovered_at`、`key_badge: boolean`、`known_conflicts: InformationRef[]`、`links: EvidenceLinkView[]` |
| `EvidenceLinkView` | `link_id`、`from_evidence_id`、`to_evidence_id`、`relation: SUPPORTS/CONTRADICTS/CORROBORATES`、`description`；两端均持有且关联已披露 |
| `NpcView` | `npc_id`、`name`、`public_identity`、`is_contactable`、`is_active`、`is_evading`、`emotion`、`admission_progress`、`display_state`、`known_statements: KnownInformation[]`、`topics: TopicView[]` |
| `TopicView` | `topic_id`、`label`、`asked`；只列本角色的预设话题，标签不剧透回答 |
| `KnownInformation` | `information_ref`、`content`、`assertion_kind`、`source`、`credibility`、`discovered_at`、`known_conflicts`；仅本局已登记且允许玩家查看的条目 |
| `PublicSource` | `kind: SCENE/NPC/EVIDENCE/PUBLIC`、`id: string\|null`、`label`；只引用已公开来源，不能暴露隐藏对象或规则 |
| `InformationRef` | `kind: EVIDENCE/KNOWLEDGE/RELATIONSHIP/TIMELINE_EVENT/EVIDENCE_LINK`、`id`；只输出已知目标 |

`kind` 的证据枚举沿用 `PHYSICAL / DOCUMENT / TESTIMONY / DIGITAL`；可信度沿用 `UNVERIFIED / VERIFIED / DISPUTED / REFUTED`；`assertion_kind` 为 `FACT / TESTIMONY`。`key_badge` 只有案件允许展示且确属关键证据时为 true；不返回内部 `is_key_internal`。

NPC 情绪为 `CALM / DEFENSIVE / NERVOUS / PRESSURED`，承认进度为 `NONE / PARTIAL_CONFESSION / CONFESSION`，`display_state` 按第 05 篇派生；当前审讯的角色回避时 `is_evading=true`、`display_state=EVADING`。公开接口不返回精确 pressure、trust、阈值、未解锁层数、链 ID、反证条件或未来说法；完整交代标签不代表该 NPC 有罪。

场景集合仅返回已开放场景；NPC 集合仅返回玩家已知人物。已知但暂不可接触的 NPC 可以保留公开档案，`is_contactable=false`。未持有与不存在的证据详情统一返回 `404 EVIDENCE_NOT_FOUND`，不借错误响应暴露隐藏证据名称。

### 5.3 业务固定结果与对话

`PlayerOutcome` 在调查和证据出示时返回：

| 字段 | 类型与含义 |
| --- | --- |
| `reason_code` | `PROGRESS_UPDATED`、`NO_NEW_INFORMATION`、`ALREADY_COMPLETED`、`EVIDENCE_RECORDED`、`TESTIMONY_RECORDED`、`CONTRADICTION_CONFIRMED`、`IRRELEVANT_MOVE`、`NPC_EVADING` 等公开反馈，不是隐藏规则失败节点 |
| `summary` | 程序产生的固定反馈，不取自模型回复 |
| `new_evidence`、`updated_evidence` | 新获得、可信度或公开关联变化的 EvidenceView 数组，允许为空 |
| `disclosed_information` | 本次新披露的 KnownInformation，含固定承认证词；不保证每份证词都是事实 |
| `unlocked_scenes` | 本次新开放的 SceneView 数组 |
| `npc` | 相关 NPC 的更新后 NpcView，纯场景调查可为 null |
| `relationships_changed`、`timeline_changed` | 布尔值，提示重读相应只读资源；不携带隐藏条目数量 |

不另设 `POST /evidence` 或 `POST /evidence/{id}/claim`。调查或合法出示命中固定规则后，在同一事务把证据加入背包，并由 `new_evidence` 返回；前端再读取背包即可。普通聊天中出现“获得证据”不产生此结果。

`ConversationView` 字段如下，聊天创建、单轮查询和历史分页复用它：

| 字段 | 含义 |
| --- | --- |
| `conversation_id`、`conversation_seq` | 一轮交互的 UUID 与整局轮序号 |
| `session_id`、`npc_id`、`request_id` | 本轮绑定对象与首次业务请求，回复重试不改写这些身份 |
| `interaction_type` | `CHAT` 或 `EVIDENCE_PRESENTATION`，从原业务请求派生 |
| `source_state_version` | 本轮获准表达所依据的已提交游戏版本 |
| `generation_status`、`generation_deadline_at` | 第 3.3 节状态与可为空的截止时间 |
| `deadline_exceeded` | 按读取时刻派生，不改变数据库中的游戏状态 |
| `fixed_reply` | 本轮安全固定回复；独立于是否已有模型消息 |
| `messages` | 最多两个槽位，按 sequence_no 排序；生成中可只有玩家消息 |
| `fallback_reason` | 公开降级码或 null，见第 9.2 节 |
| `can_retry_reply` | 按第 3.4 节守卫派生，不是客户端可提交的授权标志 |
| `created_at`、`completed_at` | UTC 时间；尚未完成时 completed_at 为 null |

消息含 `message_id`、`sequence_no`、`speaker: PLAYER/NPC`、`content`、`origin: PLAYER/LLM/FIXED`、`validity: VALID/STALE`、`created_at`、`updated_at`。出示材料的玩家消息由程序根据证据和附言构造，不能由客户端伪造 speaker。失败重试可替换回复槽，前端按 message_id 更新，不能追加成另一轮。

`ConversationPage` 含 `items: ConversationView[]`、`next_before_seq: integer|null`。被拒候选、迟到未通过的候选、内部 Prompt、ResponsePlan、用量明细和模型思考过程不进入玩家历史。模型内容按普通文本渲染。

### 5.4 人物关系图与案件时间线

`RelationshipGraph` 含 `nodes`、`edges`：

- 节点：`character_id`、`name`、`role`、公开身份；只能出现玩家已知人物。
- 边：`relationship_id`、`from_character_id`、`to_character_id`、`relationship_type`、`directed`、`description`、`assertion_kind`、`source`、`credibility`、`discovered_at`、`known_conflicts`。
- 只返回已披露且端点可见的边；同一对人物可以有多条带不同来源的关系，不能合并成一条“官方真相”。图布局由前端处理。

`TimelineView` 含 `origin_label` 和 `items: TimelineItem[]`。每项包含 `timeline_event_id`、`title`、`description`、`scene_id: string|null`、`participant_ids`、`time_precision`、`time_start_minutes`、`time_end_minutes`、`time_label`、`assertion_kind`、`source`、`credibility`、`discovered_at`、`known_conflicts`。

| 时间精度 | 起止值 | 显示规则 |
| --- | --- | --- |
| `EXACT` | 两个非空整数相等 | 按作者给出的精确分钟显示 |
| `RANGE` | 两个非空整数，开始不大于结束 | 保留区间；允许跨日及负分钟 |
| `UNKNOWN` | 两者都为 null | 保留 time_label，不猜测起止时间 |

已知时间项按开始分钟、结束分钟、ID 稳定排序，未知时间置后按 ID 排序；这种排序不宣称重叠区间具有确定先后。案内分钟相对 `origin_label`，例如“案发当日 00:00”，不能转换成玩家操作时间。两个互相矛盾的证词保留为两个条目。

### 5.5 指控与复盘

| DTO | 字段与约束 |
| --- | --- |
| `AccusationOptions` | `suspects`、`weapons`、`motives`、`process_steps` 四个候选数组；各项为 `id`、`label`；另含 `process_constraints: {min_steps,max_steps,allow_repeated_steps}`，只描述输入形状 |
| `AccusationContent` | 见第 6 节；草稿与正式指控使用相同业务字段，空值限制不同 |
| `AccusationView` | `content`、`submitted_at`、`submitted_state_version`、`case_version`、`rules_version`、`verdict` |
| `Verdict` | `category: CORRECT/PARTIALLY_CORRECT/INCORRECT`、`score`、`max_score`、`criteria`、`fixed_explanation` |
| `CriterionResult` | `criterion_id`、`label`、`matched`、`score`、`max_score`、`explanation`、`missing_evidence_ids` |
| `ReviewView` | `accusation: AccusationView`、`truth: TruthReview`、`evidence_chain: ReviewEvidence[]`、`missed_evidence: ReviewEvidence[]`、`fixed_review` |
| `TruthReview` | 正确的 `suspect_character_id`、`weapon_option_id`、`motive_option_id`、`ordered_process_step_ids`、对应选项的可读标签，以及审核过的 `explanation` |
| `ReviewEvidence` | `evidence_id`、`name`、`content`、公开来源、`explanation`、`was_discovered`；仅在结案复盘授权下可包含遗漏证据 |

候选包含干扰项，不含 `is_correct`、推荐答案、评分权重、过程匹配模式或隐藏证据需求。候选在开局前经过不剧透审核；进入指控无需先发现全部候选，也不以缺少证据禁止填写。

分数使用十进制定点字符串，例如 `"12.50"`，避免 JSON 浮点累计误差；`max_score` 从固定评分配置派生，不擅自设为 100。逐项依据只在正式判定保存后开放。

复盘的完整真相是专用投影，不输出原始 `truth_json`、规则树或 NPC 私有 Prompt。遗漏证据通过 `was_discovered=false` 展示，不补写背包或改动招供状态。MVP 使用已保存固定复盘，暂不增加可选 AI 润色入口；以后启用时应使用业务资源与独立幂等生成记录，GET 仍只读。

## 6. 写请求模型

所有表中请求均继承第 2.2 节请求头。空对象写为 `{}`，DELETE 无请求体。未知字段返回 422，包括 `pressure`、`truth`、`rule_id`、`state_patch`、`agent_id`、`system_prompt`、`model` 等非本契约字段。

| Request | JSON 字段 | 业务校验 |
| --- | --- | --- |
| `CreateSessionRequest` | `case_id: string`、`case_version: string`、`replaces_session_id: UUID\|null = null`、`confirm_restart: boolean = false` | 首次无当前局时不替换；已有当前局时必须明确指向它并 confirm_restart=true，附带旧局版本头 |
| `SetInterrogationRequest` | `npc_id: string` | NPC 属于本局固定案件且当前可接触；同目标为 NOOP |
| `InvestigateRequest` | `action_id: string` | 动作 ID 在 URL 的 scene_id 内存在；不能用其他场景同名动作替代 |
| `ChatRequest` | `message: string` | 只表示玩家文本；不自动解析成证据出示、情绪操作或阶段转换 |
| `PresentEvidenceRequest` | `evidence_id: string`、`comment: string = ""` | 检查本局持有；每次一条证据；附言不产生规则效果 |
| `AskTopicRequest` | `topic_id: string` | 话题属于当前审讯的角色；回答登记为该角色的未核验证词，重复追问为 NOOP |
| `PointContradictionRequest` | `knowledge_id: string`、`evidence_id: string` | 证词必须是本局已记录的该角色证词，证据必须持有；只按预设矛盾表判定，不成立按无关出示计 |
| `SaveAccusationDraftRequest` | `content: AccusationContent` | 全量替换，所有 content 字段都必须出现；允许相应空值 |
| `SubmitAccusationRequest` | `content: AccusationContent`、`confirm: boolean = false` | 提交完整内容快照，不默默使用可能过期的草稿；业务校验要求 confirm=true，否则 CONFIRMATION_REQUIRED |
| `EmptyRequest` | `{}` | 进入指控准备、标记复盘完成、回复重试使用；不存在客户端 target_phase |

`AccusationContent` 的准确字段如下。领域文档的 `evidence_links` 在此统一命名为 `step_evidence_links`，映射第 09 篇的 `step_evidence_links_json`，与官方 EvidenceLink 区分。

| 字段 | 草稿 | 正式提交 |
| --- | --- | --- |
| `suspect_character_id` | 合法候选 ID 或 null | 合法非空候选 ID |
| `weapon_option_id` | 合法候选 ID 或 null | 合法非空候选 ID |
| `motive_option_id` | 合法候选 ID 或 null | 合法非空候选 ID |
| `ordered_process_step_ids` | 合法步骤 ID 数组，可为空 | 非空，并符合公开的最少/最多步骤数与重复限制；不要求答案正确 |
| `cited_evidence_ids` | 本局持有证据 ID 的无重复数组 | 同左，允许空数组，证据不足由评分处理 |
| `step_evidence_links` | `{step_id,evidence_id}` 的无重复配对数组 | 同左；step_id 必须出现在本次步骤中，evidence_id 必须在本次引用集合中 |
| `explanation` | 字符串，可为空 | 同左，不参与评分 |

集合大小受本案件公开候选数量约束；过程数组最多 50 项作为接口防护上限，案件发布时保证 `max_steps <= 50`。证据引用和关联数组不接受重复值后静默覆盖；返回 422。正式字段缺失、非法选项与错误引用是输入错误；合法但推理错误正常返回 201 并结案。

首次开局只接受案件列表当前展示的版本；版本已切换返回 `409 CASE_VERSION_CHANGED`，已下架返回 `409 CASE_UNAVAILABLE`。重开可以重新选择公开案件版本，但不能复制旧局状态。旧当前局不匹配返回 `409 CURRENT_SESSION_CONFLICT`，创建失败保留原入口。

正式提交不强制先保存同内容草稿；事务内以本次 content 为准，并同步冻结草稿为该内容、正式指控、评分输入与判定。这样重载后草稿和正式内容不会矛盾，提交仍只递增一次版本。

## 7. 关键请求与响应示例

示例 ID、证据和文字仅说明契约，不代表正式案件内容。请求头中的预期版本必须来自前一次读取或提交结果，不能照抄示例常量。

### 7.1 开始与加载游戏

```http
POST /api/v1/sessions HTTP/1.1
Content-Type: application/json
Idempotency-Key: 00000000-0000-4000-8000-000000000101
Origin: https://game.example
Cookie: visitor_token=<browser-managed>

{"case_id":"CASE01","case_version":"1.0.0"}
```

成功返回 `201 ActionResult<SessionView>`，`Location: /api/v1/sessions/{新session_id}`，初始 `phase_after=INVESTIGATION`、`result_state_version=1`，并在同一事务更新当前入口。重开使用同一端点，增加 `replaces_session_id`、`confirm_restart=true` 和旧局预期版本头。

继续游戏调用 `GET /api/v1/sessions/current`；已知 ID 时调用 `GET /api/v1/sessions/{session_id}`。不存在 `/load` 写命令，也不从浏览器上传 `state_json` 覆盖存档。

### 7.2 调查并获得证据

```http
POST /api/v1/sessions/00000000-0000-4000-8000-000000000001/scenes/S01/investigations HTTP/1.1
Content-Type: application/json
Idempotency-Key: 00000000-0000-4000-8000-000000000102
X-Expected-State-Version: 1
Origin: https://game.example

{"action_id":"INSPECT_DESK"}
```

返回 `201 ActionResult<InvestigationResult>`，`Location` 指向本次 `/requests/{request_id}`。获得 E01 时，其完整安全 EvidenceView 出现在 `data.outcome.new_evidence`，新版本为 2；随后 GET 背包能读取同一条记录。

已公开且允许执行的动作没有命中取证条件时，返回正常固定反馈 `NO_NEW_INFORMATION`，不返回隐藏条件树，也不把该动作永久标为完成。首次成功调查才记录 visited/completed；纯重复无新进展为 NOOP、版本不变。再次尝试可能因新前置证据得到结果，不能由前端永久禁用所有已执行动作。

### 7.3 选择 NPC 与聊天

先调用 `PUT /sessions/{session_id}/interrogation`，请求为 `{"npc_id":"NPC01"}`。成功进入 T 后，使用新版本创建问答：

```http
POST /api/v1/sessions/00000000-0000-4000-8000-000000000001/npcs/NPC01/conversations HTTP/1.1
Content-Type: application/json
Idempotency-Key: 00000000-0000-4000-8000-000000000103
X-Expected-State-Version: 3
Origin: https://game.example

{"message":"案发当晚你在哪里？"}
```

响应为 `201 ActionResult<ChatReceipt>`，其中 `ChatReceipt` 只含 `conversation_id`；完整轮次放在统一的 `conversation` 字段。普通问答 `state_changed=false`，前后版本同为 3。将用户示例中的 `/chat` 统一建模为“创建一轮 conversations”，不再维护含义重复的 `/chat` 别名。

### 7.4 出示证据与表达降级

```http
POST /api/v1/sessions/00000000-0000-4000-8000-000000000001/npcs/NPC01/evidence-presentations HTTP/1.1
Content-Type: application/json
Idempotency-Key: 00000000-0000-4000-8000-000000000104
X-Expected-State-Version: 7
Origin: https://game.example

{"evidence_id":"E07","comment":"请解释录像中的这段行踪。"}
```

返回 `201 ActionResult<PresentationResult>`；`PresentationResult` 含 `npc_id`、`evidence_id`、`outcome: PlayerOutcome`。业务事务先保存合法出示、一次性效果、固定披露与对话占位，随后调用模型。

假设本轮已提交版本 8，后续查询该对话可能返回：

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "state_version": 8,
  "data": {
    "conversation_id": "00000000-0000-4000-8000-000000000201",
    "conversation_seq": 6,
    "session_id": "00000000-0000-4000-8000-000000000001",
    "npc_id": "NPC01",
    "request_id": "00000000-0000-4000-8000-000000000104",
    "interaction_type": "EVIDENCE_PRESENTATION",
    "source_state_version": 8,
    "generation_status": "FALLBACK",
    "generation_deadline_at": "2026-09-22T14:00:30Z",
    "deadline_exceeded": false,
    "fixed_reply": "这份记录与我先前的说法不一致。",
    "messages": [
      {
        "message_id": "00000000-0000-4000-8000-000000000301",
        "sequence_no": 1,
        "speaker": "PLAYER",
        "content": "出示录像：请解释录像中的这段行踪。",
        "origin": "PLAYER",
        "validity": "VALID",
        "created_at": "2026-09-22T14:00:00Z",
        "updated_at": "2026-09-22T14:00:00Z"
      },
      {
        "message_id": "00000000-0000-4000-8000-000000000302",
        "sequence_no": 2,
        "speaker": "NPC",
        "content": "这份记录与我先前的说法不一致。",
        "origin": "FIXED",
        "validity": "VALID",
        "created_at": "2026-09-22T14:00:30Z",
        "updated_at": "2026-09-22T14:00:30Z"
      }
    ],
    "fallback_reason": "MODEL_TIMEOUT",
    "can_retry_reply": true,
    "created_at": "2026-09-22T14:00:00Z",
    "completed_at": "2026-09-22T14:00:30Z"
  }
}
```

`deadline_exceeded` 仅在仍处于 PREPARING/GENERATING 且已过截止时间时为 true；已完成降级不再表示“待清理超期”。已经生效的证据、矛盾识别和承认固定卡片仍从原请求结果读取，不能因 MODEL_TIMEOUT 回滚或再次出示来补生成。

### 7.5 提交最终推理

先 PUT `accusation-preparation` 进入 A。可以 PUT 保存草稿，也可以直接提交完整内容：

```http
POST /api/v1/sessions/00000000-0000-4000-8000-000000000001/accusation HTTP/1.1
Content-Type: application/json
Idempotency-Key: 00000000-0000-4000-8000-000000000105
X-Expected-State-Version: 12
Origin: https://game.example

{
  "content": {
    "suspect_character_id": "NPC01",
    "weapon_option_id": "W02",
    "motive_option_id": "M03",
    "ordered_process_step_ids": ["STEP02", "STEP01", "STEP04"],
    "cited_evidence_ids": ["E01", "E07"],
    "step_evidence_links": [
      {"step_id":"STEP02","evidence_id":"E07"}
    ],
    "explanation": "录像和现场材料支持这一作案过程。"
  },
  "confirm": true
}
```

成功返回 `201 ActionResult<AccusationView>`，`Location` 指向 `/sessions/{session_id}/accusation`，进入 R、版本变为 13。数据库事务内完成固定评分，不等待 Judge Agent 或复盘文本生成；推理错误仍返回 201，结果类别可以是 INCORRECT。

原键重发返回原判定；使用新键再次提交，版本一致时返回 `409 ACCUSATION_ALREADY_SUBMITTED`，不重新评分。GET `review` 读取固定复盘；PUT `review-completion` 记录体验结束并进入 F，之后仍可 GET 复盘。

## 8. 客户端恢复顺序

1. 进入应用先建立或复用匿名凭据，再读取案件和当前会话。
2. 用户发起操作前，保存幂等键、完整业务载荷、原目标和预期版本；只有明确进入新的用户操作才换键。
3. 收到成功响应后展示固定结果。关联对话仍在生成时只轮询；不能因 HTTP 201 把等待状态当成失败。
4. 断线、超时或提交结果未知，使用原 request_id 查询。404 后仍沿用原键重试；找到记录后按 COMMITTED、NOOP 或 REJECTED 处理。
5. 409 版本或阶段冲突后刷新会话，保留尚未保存的表单。用户重新确认新的操作时使用新键和最新版本，不自动覆盖别的页面已经保存的草稿。
6. 重放响应中的 `result_state_version` 可能早于当前版本。它用于确认历史提交，不能直接回填覆盖更高版本页面；随后 GET 当前会话。
7. 重开成功后切换到新 session_id；旧局响应只属于旧局。重开失败保留旧入口；不清空本地表单后再假定服务器成功。

## 9. Status code 与 Error code

### 9.1 HTTP 错误目录

| HTTP | Error code | 适用情况与恢复方式 |
| --- | --- | --- |
| 400 | `MALFORMED_JSON` | JSON 语法错误；修正请求，不执行任何业务 |
| 400 | `IDEMPOTENCY_KEY_REQUIRED`、`INVALID_IDEMPOTENCY_KEY` | 业务写入缺少键或键不是 UUID |
| 400 | `INVALID_STATE_VERSION_HEADER` | 版本头无法解析为正整数，或首次开局错误地携带旧局版本 |
| 401 | `VISITOR_AUTH_REQUIRED` | 访问者凭据缺失、失效或被撤销；不能用 session_id 绕过 |
| 403 | `ORIGIN_NOT_ALLOWED` | 写请求来源校验失败 |
| 404 | `CASE_NOT_FOUND` | 无可公开访问的案件 |
| 404 | `SESSION_NOT_FOUND` | 会话不存在或不属于当前访问者 |
| 404 | `SCENE_NOT_FOUND`、`NPC_NOT_FOUND` | 目标不存在、未公开或不属于本局 |
| 404 | `EVIDENCE_NOT_FOUND` | 证据详情不存在或未持有，统一反馈 |
| 404 | `CONVERSATION_NOT_FOUND`、`REQUEST_NOT_FOUND` | 轮次或请求不存在，或不在调用者的访问范围内 |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | 同一键对应不同规范化请求；不能覆盖原记录 |
| 409 | `STATE_VERSION_CONFLICT` | 已有局的预期版本过期；返回已授权的当前版本 |
| 409 | `SESSION_NOT_CURRENT` | 旧局的新写请求；旧请求重放与只读仍允许 |
| 409 | `CURRENT_SESSION_EXISTS`、`CURRENT_SESSION_CONFLICT` | 已有当前局但未明确重开，或重开目标已不是当前入口 |
| 409 | `CASE_UNAVAILABLE`、`CASE_VERSION_CHANGED` | 不能对该版本新开局；重新读取案件列表 |
| 409 | `ACTION_NOT_ALLOWED` | 阶段不允许该业务；返回当前阶段，不返回隐藏守卫 |
| 409 | `ACTION_UNAVAILABLE` | 已公开的调查动作当前禁用；给出安全提示 |
| 409 | `NPC_UNAVAILABLE` | 已知 NPC 当前不可接触 |
| 409 | `ACTIVE_NPC_MISMATCH` | 请求 NPC 不是当前审讯目标 |
| 409 | `GENERATION_BUSY` | 已有未完成 NPC 生成；附可访问的 conversation_id，等待或结束当前审讯 |
| 409 | `REPLY_RETRY_NOT_ALLOWED` | 原轮成功、失效、来源版本改变或生成策略禁止重试 |
| 409 | `ACCUSATION_ALREADY_SUBMITTED` | 新请求企图再次正式指控 |
| 409 | `REVIEW_NOT_AVAILABLE` | 尚未结案，请求正式指控或完整复盘 |
| 409 | `SAVE_VERSION_UNSUPPORTED` | 定义、规则执行或快照版本不兼容；保留存档，由服务端升级处理。`details` 含 `session_id`、`state_version`，客户端可在玩家确认后据此开新局替换当前存档 |
| 413 | `PAYLOAD_TOO_LARGE` | 请求体超过 64 KiB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 有请求体但不是约定的 JSON 类型 |
| 422 | `VALIDATION_ERROR` | 字段缺失、未知字段、错误类型、格式、长度、重复集合或无效分页参数 |
| 422 | `INVALID_ACTION_REFERENCE` | action_id 不属于 URL 中当前已开放场景 |
| 422 | `EVIDENCE_NOT_OWNED` | 出示或指控引用不在本局持有集合中；不存在、跨版本和未持有统一处理，不确认隐藏定义 |
| 422 | `INVALID_ACCUSATION_OPTION` | 非公开候选、无效过程结构或步骤证据配对；不判断推理正误 |
| 422 | `ACCUSATION_INCOMPLETE` | 正式提交缺少所需非空内容；草稿允许相应空值 |
| 422 | `CONFIRMATION_REQUIRED` | 正式提交未确认，或明确替换旧局却未确认重开 |
| 428 | `STATE_VERSION_REQUIRED` | 已有局写入或重开缺少预期版本头 |
| 429 | `RATE_LIMITED` | API 请求过于频繁，附 Retry-After；查询和固定业务不占模型额度，但仍可受 HTTP 限流 |
| 429 | `GENERATION_BUDGET_EXHAUSTED` | 显式表达重试无法预留新额度；不阻断固定回复和调查 |
| 500 | `CASE_CONFIGURATION_ERROR` | 案件配置损坏、引用缺失或规则冲突；事务回滚 |
| 500 | `SAVE_INTEGRITY_ERROR` | 存档关联、阶段与正式记录不一致；不猜测修复或展示真相 |
| 500 | `INTERNAL_ERROR` | 未预期服务端错误；返回 trace_id，不返回堆栈 |
| 503 | `PERSISTENCE_UNAVAILABLE` | 数据库不可用或事务等待超时；客户端按原请求查询，再用原键重试 |

通用 HTTP 路由层还应规范 404 `ROUTE_NOT_FOUND` 和 405 `METHOD_NOT_ALLOWED`，后者带 Allow 头；它们表示未匹配到表中端点，不是游戏状态错误。请求经过受理校验后，错误优先级为：幂等冲突 → 当前入口 → 版本 → 阶段 → 业务目标/引用；已存在正式指控时使用具体的 ACCUSATION_ALREADY_SUBMITTED。

最终表使用以下公共错误组，端点特有错误另列：

- `P`：公开读取通用错误，即 422 VALIDATION_ERROR、429 RATE_LIMITED、500 INTERNAL_ERROR、503 PERSISTENCE_UNAVAILABLE。
- `R`：P 加 401 VISITOR_AUTH_REQUIRED、404 SESSION_NOT_FOUND、409 SAVE_VERSION_UNSUPPORTED、500 CASE_CONFIGURATION_ERROR/SAVE_INTEGRITY_ERROR；适用于会话读取。
- `W`：R 加 400 MALFORMED_JSON/IDEMPOTENCY_KEY_REQUIRED/INVALID_IDEMPOTENCY_KEY/INVALID_STATE_VERSION_HEADER、403 ORIGIN_NOT_ALLOWED、409 IDEMPOTENCY_KEY_CONFLICT/STATE_VERSION_CONFLICT/SESSION_NOT_CURRENT/ACTION_NOT_ALLOWED、413 PAYLOAD_TOO_LARGE、415 UNSUPPORTED_MEDIA_TYPE、428 STATE_VERSION_REQUIRED；适用于已有会话写入。DELETE 不接受 JSON，不适用 400 MALFORMED_JSON、413、415。
- `C`：P 加 400 MALFORMED_JSON/IDEMPOTENCY_KEY_REQUIRED/INVALID_IDEMPOTENCY_KEY/INVALID_STATE_VERSION_HEADER、401 VISITOR_AUTH_REQUIRED、403 ORIGIN_NOT_ALLOWED、409 IDEMPOTENCY_KEY_CONFLICT/STATE_VERSION_CONFLICT、413 PAYLOAD_TOO_LARGE、415 UNSUPPORTED_MEDIA_TYPE、428 STATE_VERSION_REQUIRED、500 CASE_CONFIGURATION_ERROR/SAVE_INTEGRITY_ERROR；适用于创建或重开，428 只在重开生效。

上述分组只是表格缩写，OpenAPI 必须展开为实际 HTTP 状态及错误模型，不把字母 P/R/W/C 返回给客户端。字段结构非法优先由 422 返回；CONFIRMATION_REQUIRED 用于业务确认值不是 true 的情况。

### 9.2 表达降级原因

以下属于 `fallback_reason`，不是已提交操作的 HTTP 错误：

| 原因码 | 含义 |
| --- | --- |
| `GENERATION_DISABLED` | 当前使用固定回复模式 |
| `MODEL_TIMEOUT` | 模型调用超时，已提交业务保留 |
| `MODEL_UNAVAILABLE` | 上游连接失败或服务不可用 |
| `MODEL_RATE_LIMITED` | 上游限流，本轮固定降级 |
| `MODEL_OUTPUT_REJECTED` | 候选未通过表达校验，不把原始内容发给前端 |
| `CONTEXT_BUDGET_EXCEEDED` | 必需授权上下文无法在预算中完整保留 |
| `GENERATION_BUDGET_EXHAUSTED` | 初次表达无剩余额度，业务仍成功 |
| `GENERATION_INTERRUPTED` | 应用中断或派发结果未知，保留固定结果且不自动重发 |
| `CONTEXT_CHANGED` | 阶段、NPC、状态版本或当前入口改变，原轮 STALE |

是否可重试以 `can_retry_reply` 为准，不按原因码擅自自动请求模型。所有迟到响应仍记录可靠用量，但必须通过会话、目标、来源版本、当前入口和尝试身份检查，才可写入有效回复。

## 10. FastAPI 落地与验收要求

按已有 `backend/src/backend/api/`、`application/`、`domain/`、`infrastructure/` 分层落地即可，不现在生成控制器脚手架。

- 路由只解析参数、调用认证依赖和业务用例、映射响应；Game Engine 管理事务、归属、幂等与状态校验。不会出现 `/agents/{id}/run`、`/rules/evaluate` 或通用 `/sessions/{id}/state` 写接口。
- 请求与响应使用不同模型；响应显式声明 `response_model`，在安全投影之后再次限制返回字段，不能依赖前端隐藏秘密。[FastAPI 响应模型文档](https://fastapi.tiangolo.com/tutorial/response-model/)
- 为请求校验错误、业务错误和未知异常统一注册处理器，保证 4xx/5xx 均符合 ApiError。不要把请求模型错误与服务端响应模型错误都映射成 422。[FastAPI 错误处理文档](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- OpenAPI 按第 2.2 节为各业务写接口声明适用的幂等/版本请求头、Cookie 认证、具体 Request/Response、状态码和错误示例；初始化访问者与首次开局保留相应例外。Cookie 认证方案不等于完成 Origin 校验。
- `/sessions/current` 应先于 `/sessions/{session_id}` 注册，避免静态入口被当作 UUID。本文所有 GET 都不得调用模型或执行调查收益规则。
- POST 创建返回 201；进入新的审讯、指控准备或复盘完成单例时 PUT 返回 201，已存在同例或切换当前 NPC 返回 200；DELETE 返回 200 ActionResult 以携带新版本。PUT 草稿已有初始空草稿，统一返回 200。
- `Location`：新局指向会话；调查指向请求结果；聊天/出示指向对话；回复重试指向其请求结果；正式指控指向 accusation。PUT 临时单例返回 201 时 Location 为该单例 URI，表示可写的资源身份，读取其当前状态统一走会话详情。

后续实现应覆盖下列行为检查；本次只交付设计文档，不宣称这些后端检查已经通过。

| 验收场景 | 预期 |
| --- | --- |
| 无凭据、跨访问者、跨会话 NPC/对话引用 | 401 或统一 404，不返回别人的进度与文本 |
| 遍历六个稳定阶段与所有写接口 | 仅允许第 4 节组合；拒绝不改变游戏数据 |
| 同键并发、同键异输入、断线后创建请求查询 | 一次提交、一次生成占用；冲突不覆盖原记录 |
| 两个不同键携带同一旧版本 | 有效状态变更只接受一个，另一请求明确冲突；普通聊天另由生成占位保护 |
| 新键反复出示同一证据、逆序出示后再重查 | 不重复加压；满足新条件时仍可推进下一层 |
| 未持有证据、模型编造证据或认罪 | 不增加持有与承认；原始违规候选不返回 |
| 读取场景、背包、NPC、图、时间线、请求与历史 | 不写业务版本、不生成新证据、不自动调用模型 |
| 表达超时、预算耗尽、阶段切换后迟到 | 固定结果完整；生成独立降级；旧回复不能覆盖当前状态 |
| 指控不完整与合法错误推理 | 前者拒绝，后者正常结案；没有证据也可提交合法指控 |
| 正式提交事务中断、同键重发、新键重提 | 无半份结案；一局只有一份冻结结果 |
| 结案前复盘、结案后调查、旧局新写入 | 均拒绝；旧局只读和已成功旧请求重放仍可用 |
| 重开失败、存档版本不兼容 | 保留旧入口与原始数据，不猜测迁移 |
| 隐藏内容使用唯一标记进行响应检查 | 加载、错误、图表、候选、历史和固定结果均不泄露未授权标记 |

## 11. 完整 API 表

P/R/W/C 的全部 HTTP 与错误码见第 9.1 节，并入各行契约；Status code 列中的组名表示继承该组错误状态，不是额外状态码。表中 Request 的 `—` 表示无请求体，`V` 表示必须带 `X-Expected-State-Version`，`K` 表示必须带 `Idempotency-Key`。所有非访问者初始化写入都带 K，所有已有会话写入都带 V。

`View<T>`、`ActionResult<T>` 和各 DTO 的准确字段见第 2～6 节。`PhaseResult` 为 `SessionSummary`；`DraftResult` 为 `{content: AccusationContent}`；`ChatReceipt` 为 `{conversation_id: UUID}`；`RetryReceipt` 同样只含原 conversation_id。`QuestionResult` 为 `{npc_id, topic_id, fixed_reply, outcome}`；`ContradictionResult` 为 `{npc_id, knowledge_id, evidence_id, fixed_reply, outcome}`。查询形式 `View<{items:T[]}>` 不分页，只有 ConversationPage 使用轮次分页。

| 业务能力 | HTTP Method | Path | Request | Response | Status code | Error code | 合法状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 建立或复用匿名访问者 | POST | `/api/v1/visitors` | `{}`；同源 Origin | VisitorView；首次设置 Cookie | 201 新建 / 200 复用；P、400、403、413、415 | P；MALFORMED_JSON、ORIGIN_NOT_ALLOWED、PAYLOAD_TOO_LARGE、UNSUPPORTED_MEDIA_TYPE | 无需游戏会话 |
| 案件列表 | GET | `/api/v1/cases` | — | CaseList | 200；P | P | 无需游戏会话 |
| 案件公开简介 | GET | `/api/v1/cases/{case_id}` | Path case_id | CaseSummary | 200；P、404 | P；CASE_NOT_FOUND | 无需游戏会话 |
| 开始或确认重开游戏 | POST | `/api/v1/sessions` | K；CreateSessionRequest；重开另带旧局 V | ActionResult&lt;SessionView&gt; | 201；C、404、409、422 | C；CASE_NOT_FOUND、SESSION_NOT_FOUND、CURRENT_SESSION_EXISTS、CURRENT_SESSION_CONFLICT、CASE_UNAVAILABLE、CASE_VERSION_CHANGED、CONFIRMATION_REQUIRED | 无当前局；或自己的当前旧局 S |
| 继续当前游戏 | GET | `/api/v1/sessions/current` | — | CurrentSessionView；无局为 null | 200；R | R | S；无局也可读 |
| 加载指定游戏 | GET | `/api/v1/sessions/{session_id}` | Path session_id | SessionView | 200；R | R | S，允许自己的旧局 |
| 查询原操作结果 | GET | `/api/v1/requests/{request_id}` | Path request_id；Cookie 限定命名空间 | RequestRecord | 200；P、401、404 | P；VISITOR_AUTH_REQUIRED、REQUEST_NOT_FOUND | 无需知道 session_id |
| 查看场景列表 | GET | `/api/v1/sessions/{session_id}/scenes` | Path session_id | View&lt;{items:SceneView[]}&gt; | 200；R | R | S |
| 查看场景详情与动作 | GET | `/api/v1/sessions/{session_id}/scenes/{scene_id}` | Path session_id、scene_id | View&lt;SceneView&gt; | 200；R、404 | R；SCENE_NOT_FOUND | S，仅已开放场景 |
| 执行调查并获得证据 | POST | `/api/v1/sessions/{session_id}/scenes/{scene_id}/investigations` | K、V；InvestigateRequest | ActionResult&lt;InvestigationResult&gt;，含 new_evidence | 201；W、404、409、422 | W；SCENE_NOT_FOUND、ACTION_UNAVAILABLE、INVALID_ACTION_REFERENCE | I、D |
| 查看证据背包 | GET | `/api/v1/sessions/{session_id}/evidence` | Path session_id | View&lt;{items:EvidenceView[]}&gt; | 200；R | R | S |
| 查看持有证据详情 | GET | `/api/v1/sessions/{session_id}/evidence/{evidence_id}` | Path session_id、evidence_id | View&lt;EvidenceView&gt; | 200；R、404 | R；EVIDENCE_NOT_FOUND | S，仅已持有 |
| 查看 NPC 列表 | GET | `/api/v1/sessions/{session_id}/npcs` | Path session_id | View&lt;{items:NpcView[]}&gt; | 200；R | R | S |
| 查看 NPC 公开档案 | GET | `/api/v1/sessions/{session_id}/npcs/{npc_id}` | Path session_id、npc_id | View&lt;NpcView&gt; | 200；R、404 | R；NPC_NOT_FOUND | S |
| 开始审讯或切换 NPC | PUT | `/api/v1/sessions/{session_id}/interrogation` | K、V；SetInterrogationRequest | ActionResult&lt;PhaseResult&gt; | 201 进入 / 200 切换或同目标；W、404、409 | W；NPC_NOT_FOUND、NPC_UNAVAILABLE | I、D、T |
| 结束审讯 | DELETE | `/api/v1/sessions/{session_id}/interrogation` | K、V；无请求体 | ActionResult&lt;PhaseResult&gt; | 200；W，排除请求体错误 | W | T；I/D 为 NOOP |
| 与 NPC 聊天 | POST | `/api/v1/sessions/{session_id}/npcs/{npc_id}/conversations` | K、V；ChatRequest | ActionResult&lt;ChatReceipt&gt;，附 ConversationView | 201；W、404、409 | W；NPC_NOT_FOUND、NPC_UNAVAILABLE、ACTIVE_NPC_MISMATCH、GENERATION_BUSY | T，当前 NPC |
| 查看 NPC 聊天历史 | GET | `/api/v1/sessions/{session_id}/npcs/{npc_id}/conversations` | Query limit=20、before_seq 可选 | View&lt;ConversationPage&gt; | 200；R、404 | R；NPC_NOT_FOUND | S |
| 查询一轮回复 | GET | `/api/v1/sessions/{session_id}/conversations/{conversation_id}` | Path session_id、conversation_id | View&lt;ConversationView&gt; | 200；R、404 | R；CONVERSATION_NOT_FOUND | S |
| 显式重试 NPC 回复 | POST | `/api/v1/sessions/{session_id}/conversations/{conversation_id}/reply-retries` | K、V；`{}` | ActionResult&lt;RetryReceipt&gt;，关联原轮最新状态 | 201；W、404、409、429 | W；CONVERSATION_NOT_FOUND、REPLY_RETRY_NOT_ALLOWED、ACTIVE_NPC_MISMATCH、GENERATION_BUSY、GENERATION_BUDGET_EXHAUSTED | T；原轮仍可重试 |
| 向 NPC 出示证据 | POST | `/api/v1/sessions/{session_id}/npcs/{npc_id}/evidence-presentations` | K、V；PresentEvidenceRequest | ActionResult&lt;PresentationResult&gt;，附固定披露与 ConversationView | 201；W、404、409、422 | W；NPC_NOT_FOUND、NPC_UNAVAILABLE、ACTIVE_NPC_MISMATCH、EVIDENCE_NOT_OWNED、GENERATION_BUSY | T，当前 NPC |
| 追问预设话题 | POST | `/api/v1/sessions/{session_id}/npcs/{npc_id}/questions` | K、V；AskTopicRequest | ActionResult&lt;QuestionResult&gt;，附新登记的证词 | 201；W、404、409、422 | W；NPC_NOT_FOUND、NPC_UNAVAILABLE、ACTIVE_NPC_MISMATCH、INVALID_ACTION_REFERENCE | T，当前 NPC |
| 指出证词与证据的矛盾 | POST | `/api/v1/sessions/{session_id}/npcs/{npc_id}/contradictions` | K、V；PointContradictionRequest | ActionResult&lt;ContradictionResult&gt; | 201；W、404、409、422 | W；NPC_NOT_FOUND、NPC_UNAVAILABLE、ACTIVE_NPC_MISMATCH、INVALID_ACTION_REFERENCE、EVIDENCE_NOT_OWNED | T，当前 NPC |
| 查看人物关系图 | GET | `/api/v1/sessions/{session_id}/relationships` | Path session_id | View&lt;RelationshipGraph&gt; | 200；R | R | S，仅已知节点与边 |
| 查看案件时间线 | GET | `/api/v1/sessions/{session_id}/timeline` | Path session_id | View&lt;TimelineView&gt; | 200；R | R | S，仅已知事件 |
| 进入指控准备 | PUT | `/api/v1/sessions/{session_id}/accusation-preparation` | K、V；`{}` | ActionResult&lt;PhaseResult&gt; | 201 进入 / 200 已在 A；W | W | I、D、T、A |
| 返回调查并保留草稿 | DELETE | `/api/v1/sessions/{session_id}/accusation-preparation` | K、V；无请求体 | ActionResult&lt;PhaseResult&gt; | 200；W，排除请求体错误 | W | A；I/D 为 NOOP |
| 查看推理候选项 | GET | `/api/v1/sessions/{session_id}/accusation-options` | Path session_id | View&lt;AccusationOptions&gt; | 200；R | R | S |
| 查看指控草稿 | GET | `/api/v1/sessions/{session_id}/accusation-draft` | Path session_id | View&lt;DraftResult&gt;；空草稿采用 null 字段和空集合 | 200；R | R | S |
| 保存完整草稿表示 | PUT | `/api/v1/sessions/{session_id}/accusation-draft` | K、V；SaveAccusationDraftRequest | ActionResult&lt;DraftResult&gt; | 200；W、422 | W；INVALID_ACCUSATION_OPTION、EVIDENCE_NOT_OWNED | A |
| 提交最终推理并结案 | POST | `/api/v1/sessions/{session_id}/accusation` | K、V；SubmitAccusationRequest | ActionResult&lt;AccusationView&gt; | 201；W、409、422 | W；ACCUSATION_ALREADY_SUBMITTED、ACCUSATION_INCOMPLETE、INVALID_ACCUSATION_OPTION、EVIDENCE_NOT_OWNED、CONFIRMATION_REQUIRED | A；原成功请求可在 R/F 重放 |
| 查看正式推理与判定 | GET | `/api/v1/sessions/{session_id}/accusation` | Path session_id | View&lt;AccusationView&gt; | 200；R、409 | R；REVIEW_NOT_AVAILABLE | R、F |
| 查看完整案件复盘 | GET | `/api/v1/sessions/{session_id}/review` | Path session_id | View&lt;ReviewView&gt; | 200；R、409 | R；REVIEW_NOT_AVAILABLE | R、F |
| 结束本局体验 | PUT | `/api/v1/sessions/{session_id}/review-completion` | K、V；`{}` | ActionResult&lt;PhaseResult&gt; | 201 完成 / 200 已在 F；W | W | R、F |
