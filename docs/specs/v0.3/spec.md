# v0.3 规格：完整案件，全部固定回复

任务 T10～T14，约 60 小时。依据：路线图 v0.3、第 05、06、08、09、10、11 篇、
[全案草稿](../../../backend/assets/cases/case_001/v1/full-case-draft.md)。

## 1. 目标

把《停电之夜》全案（4 NPC、4 场景、12 证据、3 条谎言链 / 4 层）接入现有 API、数据库和网页，
不调用任何模型就能完整破案。这个版本是接入模型之前的门槛，也是之后出故障时回退的基线。

完成后能演示：

1. 浏览器开局 → 四个场景取证（场景按证据逐步开放）→ 进入深入调查；
2. 审讯四人：追问预设话题、指出矛盾、出示证据；演示“击破但未承认”和沈砚的两层承认；
3. 保存指控草稿 → 返回调查 → 重新进入指控 → 正式结案；
4. 正确、部分正确、错误三类判定，以及**不触发任何承认**也能得 100 分的路径；
5. 查看人物关系与时间线列表（只含已知条目），刷新或重启后端后继续。

### 不做

模型调用、Prompt、Memory、`llm_attempt` 表、ECharts 图表、HTTP 限流、SSE、第二案件、拖拽推理板、
深入调查专属动作（`DEEP_INVESTIGATION` 只是里程碑阶段，不额外开放动作）、证据之间的官方关联
（`EvidenceView.links` 固定为空数组）。

## 2. 案件文件（schema 3）

正式配置已经写好：`backend/assets/cases/case_001/v1/case.json`（版本 `3-full`，规则 `full-1`）。
它是本阶段的**人工预期**，实现时不能改动；发现错误先写 `test-amendments.md` 再改。

`slice.json` 退役：从 `backend/assets` 删除，`pyproject.toml` 的 `force-include` 改为打包 `case.json`，
`default_case_path()` 指向 `case.json`。已发布的 `2-slice` 模板行和旧存档留在数据库里，
它们的 `rule_execution_version` 不再受支持，读取时返回 v0.2 已有的 `SAVE_VERSION_UNSUPPORTED`。

### 2.1 字段

顶层（全部必填，`extra="forbid"`，`strict=True`，沿用 `Definition`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | `Literal[3]` | |
| `scope` | `Literal["full_case"]` | |
| `case_id`、`version`、`rules_version`、`title`、`synopsis`、`introduction` | Text | `synopsis` 写入 `case_template.synopsis`，不再复用 `introduction` |
| `review_status` | `Literal["pending_human_review", "approved"]` | |
| `timeline_origin_label` | Text | |
| `show_key_badges` | bool | false 时所有 `key_badge` 为 false |
| `characters` | `Character[]` | 含不可审讯的死者 |
| `scenes` | `Scene[]` | |
| `evidence` | `Evidence[]` | |
| `knowledge` | `Knowledge[]` | |
| `lies` | `Lie[]` | 一层可独立击破的隐瞒 |
| `lie_chains` | `LieChain[]` | 把层按顺序分组 |
| `interrogation` | `Interrogation` | 与 schema 2 相同结构，话题和矛盾带 `npc_id` |
| `deep_unlock` | `Dependency` | 深入调查的证据分支；两个集合都空表示证据分支永不成立 |
| `relationships` | `Relationship[]` | |
| `timeline` | `TimelineEvent[]` | |
| `suspects`、`weapons`、`motives`、`process_steps` | `Choice[]` | 同 schema 2 |
| `truth`、`scoring` | 同 schema 2 | |

子对象（未列出的字段与 schema 2 相同）：

```text
Character  {id, name, role, public_identity, personality: Text|null, speech_style: Text|null,
            interrogatable: bool, initial_pressure: Level|null, initial_trust: Level|null,
            core_lie_ids: Text[], default_reply: Text|null}
Scene      {id, name, description, unlock: Dependency, actions: Investigation[]}
Evidence   {id, title, kind: PHYSICAL|DOCUMENT|TESTIMONY|DIGITAL, content, source,
            credibility: VERIFIED|UNVERIFIED, is_key: bool}
Knowledge  {id, content, known_by: Text[], disclosure: PUBLIC|ADMITTED|ASKED}
Lie        {id, npc_id, counterevidence: Dependency, admission_presented: Dependency,
            admission_pressure_min: Level|null, admission_trust_min: Level|null,
            statements {unbroken, broken, admitted}, admitted_knowledge_id,
            effects: {evidence_id, pressure: Delta, trust: Delta}[]}
LieChain   {id, npc_id, lie_ids: Text[]}             # 顺序即层序
Relationship {id, from_id, to_id, type, directed: bool, description,
            assertion_kind: FACT|TESTIMONY, credibility: VERIFIED|UNVERIFIED,
            source_kind: PUBLIC|EVIDENCE|NPC, source_id: Text|null,
            reveal_evidence_ids: Text[], reveal_knowledge_ids: Text[]}
TimelineEvent {id, title, description, scene_id: Text|null, participant_ids: Text[],
            precision: EXACT|RANGE|UNKNOWN, start_minutes: int|null, end_minutes: int|null,
            time_label, assertion_kind, credibility, source_kind, source_id,
            reveal_evidence_ids, reveal_knowledge_ids, conflicts_with: Text[]}
```

### 2.2 发布校验（`validate_case`，失败抛 `ValueError`）

`parse_case` 先拒绝重复 JSON 键，再做结构校验，最后调用 `validate_case`。必须拒绝：

1. 任一类 ID 重复：人物、场景、调查动作（**全案唯一**，不只是场景内）、证据、知识、谎言层、链、话题、矛盾、
   关系、时间线、评分项、四类候选。
2. 任何引用不存在：动作授予的证据、所有 `Dependency`（动作前置、场景开放、反证、承认材料、深入调查）、
   `known_by`、`core_lie_ids`、效果证据、话题/矛盾的人物与知识与证据、关系端点与揭示条件、
   时间线场景/参与者/揭示条件/冲突对象、`truth` 与候选。
3. 有证据不被任何动作授予；或从开局（无证据、无承认）出发，按“场景开放 ∧ 动作前置”求不动点后，
   有证据不可达。**谎言进度不能成为取证前置**，所以这一步同时保证“无招供可收齐全部证据”。
4. 没有开局即开放的场景（`unlock` 两个集合都空）。
5. 可审讯人物缺 `initial_pressure`、`initial_trust`、`personality` 或 `speech_style`；
   嫌疑人候选不是可审讯人物；可审讯且没有任何链的人物缺 `default_reply`。
6. 谎言层：人物不可审讯；不属于恰好一条链；链的 `npc_id` 与层不一致；空链；反证两个集合都空；
   两个心理门槛都为 null；承认知识不是 `ADMITTED`、或说话人不在 `known_by`；
   某条 `ADMITTED` 知识没有被恰好一层引用；层内效果证据重复；效果证据不在本层
   `counterevidence ∪ admission_presented` 中；同一人物的不同层对同一证据都配置了效果；
   `core_lie_ids` 引用了别人的层。
7. 承认不可达：对每条链，从该人物初始压力、**最坏信任 0** 出发，逐层按排序后的
   `counterevidence ∪ admission_presented` 依次出示（使用真实的 `present` 规则函数），
   结束时不是所有层都 `ADMITTED`。
8. 话题：人物不可审讯；知识不是 `ASKED` 或说话人不在 `known_by`；某条 `ASKED` 知识没有恰好一个话题。
9. 矛盾：知识的说话人（见 3.4）不是该人物；知识是 `PUBLIC`；证据不是 `VERIFIED`；`(npc, 知识, 证据)` 重复。
10. 关系：`source_kind=PUBLIC` 却有揭示条件或 `source_id`；`EVIDENCE` 的 `source_id` 不在 `reveal_evidence_ids`；
    `NPC` 的 `source_id` 不是人物。
11. 时间线：`EXACT` 起止不相等或为空；`RANGE` 为空或起点大于终点；`UNKNOWN` 起止不为空；
    冲突引用自身或不对称（A 列 B 则 B 必须列 A）。
12. 评分：沿用 schema 2 全部规则（总分 100、阈值顺序、四类各一项、支持项引用真相步骤与已核验证据、
    无证据最高分低于正确阈值）。

### 2.3 内容一览（便于核对测试）

| 场景 | 开放条件 | 动作 → 证据（前置） |
| --- | --- | --- |
| S01 档案室 | 开局 | A01→E01；A02→E02；A03→E03（E01、E02）；A04→E04 |
| S02 资料室 | 持有 E01 或 E02 | A05→E05；A06→E06（E05） |
| S03 数据间 | 持有 E03 | A07→E07；A08→E08（E06、E07）；A09→E09（E07） |
| S04 配电值班室 | 持有 E01 或 E05 | A10→E10；A11→E11（E01、E10）；A12→E12（E10） |

| 层 | 人物 | 前置 | 击破 | 承认 | 效果（首次、仅当本层为当前层） |
| --- | --- | --- | --- | --- | --- |
| L01 | NPC01 20/40 | — | 出示 E01 | E01、E03 均出示且压力 ≥65 | E01 +25/−5；E03 +25/0 |
| L02 | NPC01 | L01 已承认 | 出示 E02、E08 | E02、E08 且压力 ≥85 | E08 +20/0 |
| L03 | NPC02 10/35 | — | 出示 E05 | E05、E06 且压力 ≥45 | E05 +20；E06 +20 |
| L04 | NPC03 15/40 | — | 出示 E10 | E10、E11 且压力 ≥60 | E10 +25；E11 +25 |

NPC04 林澄 10/50 没有谎言链，只有话题 Q04、Q05 和矛盾 C03。死者 `VICTIM` 只出现在关系图里。
深入调查的证据条件为持有 E03。

## 3. 领域规则

domain 层保持纯函数，测试直接调用。下面的签名是**对测试的承诺**，名字和参数顺序不能改。

```python
# backend/domain/models.py
@dataclass(frozen=True)
class NPCState:
    pressure: int
    trust: int
    lies: Mapping[str, LieStage]           # 本人物所有层，初始 UNBROKEN
    presented: frozenset[str] = frozenset()
    irrelevant_streak: int = 0

@dataclass(frozen=True)
class GameState:
    npcs: Mapping[str, NPCState]           # 每个可审讯人物一项
    phase: Phase = Phase.INVESTIGATION
    active_npc_id: str | None = None
    evidence_ids: frozenset[str] = frozenset()
    completed_actions: frozenset[str] = frozenset()
    disclosed_knowledge: frozenset[str] = frozenset()
    consumed_effects: frozenset[str] = frozenset()
    deep_unlocked: bool = False
    draft: AccusationDraft | None = None
    verdict: Verdict | None = None
    version: int = 1

class AccusationDraft(Definition):         # 字段同 Accusation，三项选择可为 None，steps 可为空
    culprit: Text | None; weapon: Text | None; motive: Text | None
    steps: tuple[Text, ...]; cited_evidence_ids: tuple[Text, ...]
    evidence_links: tuple[StepEvidenceLink, ...]; explanation: str = ""

# backend/domain/rules.py
RULE_EXECUTION_VERSION = "full-1"
def new_game(case) -> GameState
def open_scenes(case, state) -> tuple[str, ...]            # 按案件顺序
def relevant_evidence(case, state, npc_id) -> frozenset[str]
def investigate(case, state, action_id) -> GameState
def present(case, state, npc_id, evidence_id) -> GameState
def ask_topic(case, state, npc_id, topic_id) -> GameState
def contradict(case, state, npc_id, knowledge_id, evidence_id) -> GameState
def save_draft(case, state, draft: AccusationDraft) -> GameState
def judge(case, state, accusation: Accusation) -> GameState
def topic_outcome(case, before, knowledge_id) -> str
def present_outcome(case, before, after, npc_id, evidence_id) -> str
def contradiction_outcome(case, before, after, matched: bool) -> str

# backend/domain/state_machine.py
def guard(state, action) -> None
def transition(state, action, npc_id=None) -> GameState     # talk / back / accuse / finish
def emotion(npc: NPCState) -> str
def evading(case, npc: NPCState) -> bool
def admission_progress(case, state, npc_id) -> str           # NONE / PARTIAL_CONFESSION / CONFESSION
def display_state(case, state, npc_id) -> str

# backend/domain/evidence.py
def current_statement(case, state, npc_id) -> str
```

`GameError(message, code)` 沿用；所有拒绝都不改变状态。返回值与输入 `==` 相等即为 NOOP。

### 3.1 阶段与动作

| 动作 | I | D | T | A | R | F |
| --- | --- | --- | --- | --- | --- | --- |
| `inspect` | ✓ | ✓ | × | × | × | × |
| `talk`（进入/切换审讯） | ✓ | ✓ | ✓ | × | × | × |
| `ask` / `topic` / `present` / `contradict` | × | × | ✓ | × | × | × |
| `back`（结束审讯或退出指控） | × | × | ✓ | ✓ | × | × |
| `accuse` | ✓ | ✓ | ✓ | × | × | × |
| `draft` / `submit` | × | × | × | ✓ | × | × |
| `finish` | × | × | × | × | ✓ | × |

- `back` 回到 D（`deep_unlocked`）或 I。离开审讯、切换到另一个人物、进入指控时，**所有人物**的
  `irrelevant_streak` 清零。切换到同一个人物是 NOOP。
- API 层沿用 v0.2：在 I/D 结束审讯、在 I/D 退出指控、在 A 重复进入指控、在 F 重复完成复盘都是 NOOP（200），
  不是拒绝。
- 拒绝码：阶段不符 `ACTION_NOT_ALLOWED`；对非当前人物操作 `ACTIVE_NPC_MISMATCH`。

### 3.2 场景与调查

- `open_scenes`：`unlock` 被当前持有证据满足的场景（两个集合都空即开局开放）。证据不会失去，所以开放不会撤销。
- `investigate(action_id)`：动作 ID 不存在 → `INVALID_ACTION_REFERENCE`；所属场景未开放 → `SCENE_NOT_FOUND`；
  已完成 → 原样返回；前置不满足 → `ACTION_UNAVAILABLE`；否则加入证据与完成动作。
- 深入调查：本次之后 `deep_unlock` 非空且被满足，或任一人物任一层不是 `UNBROKEN`，就置 `deep_unlocked=True`；
  若当前是 I 则同时转为 D。T 中解锁只记里程碑，阶段不变。

### 3.3 出示证据（固定求值顺序）

```text
S0  guard("present")；npc_id == active_npc_id；必须持有证据。
    人物正在回避（irrelevant_streak >= evade_after）→ 原样返回。
    current(chain) = 链中第一个不是 ADMITTED 的层（全部承认则无当前层）
    相关层 = 每条链中已 ADMITTED 的层 + 当前层（即排除当前层之后的“未来层”）
    relevant = 本人物所有相关层的 counterevidence ∪ admission_presented ∪ 效果证据
    presented |= {evidence}
    若 evidence ∉ relevant：键 irrelevant:{npc}:{evidence} 首次时信任 + irrelevant_trust（截断），
       irrelevant_streak += 1，结束（不求值谎言）。
    irrelevant_streak = 0
S1  证据为 VERIFIED 且键 present:{npc}:{evidence} 未消费：汇总本人物所有相关层中该证据的效果，
    压力、信任各截断到 0～100 一次，消费该键（即使截断后增量为 0）。
S2  verified = presented ∩ 已核验证据。对本人物每一层：S0 时为 UNBROKEN、前置满足
    （首层，或链中上一层在 S0 时已 ADMITTED）、counterevidence 被 verified 满足 → BROKEN。
S3  对每一层：S2 后为 BROKEN、前置满足（同样按 S0 判断）、admission_presented 被 verified 满足、
    （pressure ≥ pressure_min 或 trust ≥ trust_min，null 的分支视为不满足）→ ADMITTED，
    披露 admitted_knowledge_id。
S4  任一层非 UNBROKEN 时置 deep_unlocked（阶段保持 T）。
```

推论（都有验收测试）：

- 同一层可以在一次出示里 U→B→A；前一层在本次刚承认时，下一层要等**下一次**合法出示才重查。
- 提前出示下一层的材料按无关计（扣一次信任、计入回避次数），但会记入 `presented`，以后满足条件时仍算数。
- 已承认层的材料仍是相关的：再次出示不扣信任，结果为 `ALREADY_PRESENTED`。
- 没有谎言链的人物（林澄）没有相关证据，任何出示都按无关计。
- 提前出示时没有消费 `present:` 键，所以该证据成为当前层材料后再出示仍会产生一次效果。
- 回避期间出示、追问、指矛盾都不改变状态。

`present_outcome`：回避中 `NPC_EVADING`；无关时 `IRRELEVANT_MOVE`，本次正好开始回避则内部码
`EVASION_STARTED`（对外仍是 `NPC_EVADING`）；有层变成 ADMITTED → `ADMISSION_RECORDED`；
有层变成 BROKEN → `LIE_BROKEN`；之前出示过且本次没有消费效果 → `ALREADY_PRESENTED`；
其余 `EVIDENCE_RECORDED`。

### 3.4 话题、矛盾与证词

- 知识的**说话人**：`ASKED` 为对应话题的 `npc_id`，`ADMITTED` 为引用它的层的 `npc_id`，`PUBLIC` 没有说话人。
- `ask_topic`：话题必须属于该人物，否则 `INVALID_ACTION_REFERENCE`；回避中原样返回；否则披露对应知识。
  不改变数值、谎言和回避计数。
- `contradict`：知识必须已披露、不是 `PUBLIC`、且说话人是该人物，否则统一 `INVALID_ACTION_REFERENCE`
  （不区分未披露、他人的、公开的和不存在的）；证据必须持有；回避中原样返回。
  命中矛盾表：清零回避计数，键 `contradiction:{npc}:{C id}` 首次时按配置改数值；不改变谎言阶段。
  不命中：键 `mismatch:{npc}:{知识}:{证据}` 首次扣信任，回避计数 +1。

### 3.5 说法、情绪与展示状态

- `current_statement`：回避中 → `evade_reply`；否则按链顺序拼接每条链的说法（本案每人至多一条链）。
  一条链的说法：有当前层时取该层当前阶段的固定句；全部承认时取最后一层的 `admitted`。
  没有链的人物返回 `default_reply`。
- `emotion` 沿用：压力 ≥70 `PRESSURED`；≥40 `NERVOUS`；信任 <30 `DEFENSIVE`；否则 `CALM`。
- `admission_progress`：`core_lie_ids` 非空且全部 ADMITTED → `CONFESSION`；否则有任一层 ADMITTED →
  `PARTIAL_CONFESSION`；否则 `NONE`。
- `display_state`：当前审讯对象正在回避 → `EVADING`；否则 `CONFESSION` / `PARTIAL_CONFESSION` 优先；
  否则为 `emotion`。

### 3.6 指控草稿与评分

- `save_draft`：只在 A。已填写的选择必须属于候选；步骤无重复且属于候选；引用证据无重复且已持有；
  关联无重复，步骤在本次步骤中、证据在本次引用中。不合法 → `INVALID_ACCUSATION_OPTION` 或
  `EVIDENCE_NOT_OWNED`。内容相同为 NOOP。
- 草稿在退出、重入指控时保留。`judge` 成功时把草稿替换成本次正式内容（同一次版本递增）。
- `judge` 沿用 v0.2 规则，另外：每个评分结果带 `missing_evidence_ids`（支持项中没有被关联到该步骤的证据，
  按配置顺序；非支持项为空）；`Verdict` 带 `fixed_explanation`，按类别取固定文案：
  `CORRECT`「推理成立：凶手、凶器、动机与关键依据基本吻合。」，
  `PARTIALLY_CORRECT`「推理部分成立：请对照逐项结果查看缺失的依据。」，
  `INCORRECT`「推理不成立：凶手判断或关键依据与事实不符。」。

### 3.7 关系与时间线投影

条目在以下任一情况可见：两个揭示集合都为空；持有任一 `reveal_evidence_ids`；已披露任一
`reveal_knowledge_ids`。关系图节点为全部人物（含死者），边只有可见关系。
时间线排序：有时间的按 `(start, end, id)`，`UNKNOWN` 排最后按 id。`known_conflicts` 只列同样可见的冲突条目。

## 4. 持久化

- 新迁移 `0003`：在 0002 基础上加全案需要的静态列/表（至少 `relationship`、`timeline_event`，
  人物性格/风格/默认回复、证据种类/关键标记、场景开放条件、层的链信息）和运行表 `conversation`、
  `conversation_message`（字段按第 09 篇 6.4、6.5，本阶段不建 `llm_attempt`，`active_attempt_id` 可先不加）。
  每个可审讯人物一行 `npc_state`，各层阶段可存 JSON 列；草稿存 `game_session.state_json["accusation_draft"]`。
- 在已有 0002 数据（含切片存档）上升级必须成功且旧行原样保留；降级到 0002 在空库上必须成功；
  `alembic check` 无差异。
- 导入后 `content_hash(load_case_from_db) == content_hash(file)`，否则拒绝发布（沿用 v0.2）。
- 会话快照仍以关系表为准，不新增一份可写的完整 JSON 存档。

## 5. API

沿用 v0.2 的请求头、幂等、版本、错误格式和 `ActionResult`。新增或改动：

| 能力 | 方法与路径 | 说明 |
| --- | --- | --- |
| 场景列表/详情 | `GET /sessions/{id}/scenes`、`/scenes/{scene_id}` | `View<{items: SceneView[]}>` / `View<SceneView>`；未开放场景 404 `SCENE_NOT_FOUND` |
| 调查 | `POST /sessions/{id}/scenes/{scene_id}/investigations` | URL 场景未开放或不存在 → 404 `SCENE_NOT_FOUND`；动作不属于该场景 → 422 `INVALID_ACTION_REFERENCE` |
| 证据背包/详情 | `GET /sessions/{id}/evidence`、`/evidence/{evidence_id}` | 未持有与不存在统一 404 `EVIDENCE_NOT_FOUND` |
| 人物列表/详情 | `GET /sessions/{id}/npcs`、`/npcs/{npc_id}` | 只列四名可审讯人物；未知 404 `NPC_NOT_FOUND` |
| 审讯 | `PUT /sessions/{id}/interrogation` | `VICTIM` → 409 `NPC_UNAVAILABLE`；未知 → 404 |
| 聊天 | `POST /sessions/{id}/npcs/{npc_id}/conversations` | 见 5.2 |
| 历史 | `GET /sessions/{id}/npcs/{npc_id}/conversations?limit=20&before_seq=` | `View<ConversationPage>`，按 `conversation_seq` 倒序，`limit` 1～50 |
| 单轮 | `GET /sessions/{id}/conversations/{conversation_id}` | `View<ConversationView>`；别人的或不存在 404 `CONVERSATION_NOT_FOUND` |
| 出示 | `POST /sessions/{id}/npcs/{npc_id}/evidence-presentations` | 另外创建一轮对话，`conversation` 字段非空 |
| 关系 | `GET /sessions/{id}/relationships` | `View<RelationshipGraph>` |
| 时间线 | `GET /sessions/{id}/timeline` | `View<TimelineView>` |
| 指控候选 | `GET /sessions/{id}/accusation-options` | `View<AccusationOptions>` |
| 草稿 | `GET`、`PUT /sessions/{id}/accusation-draft` | `View<DraftResult>`；PUT 只在 A，返回 200 `ActionResult<DraftResult>` |
| 正式指控 | `POST /sessions/{id}/accusation` | 三项选择缺失或为 null、步骤为空 → 422 `ACCUSATION_INCOMPLETE` |

`View<T>` 形如 `{"session_id", "state_version", "data": T}`，与 v0.2 的 `closed_view` 一致。所有 GET 不写库、不改版本。

- 列表顺序：场景、人物、证据、关系边按案件配置顺序；时间线按 3.7；对话历史按 `conversation_seq` 倒序。
- 历史分页：`limit` 默认 20，取值 1～50；`before_seq` 可选，正整数，只返回更小的序号。
  还有更早的轮次时 `next_before_seq` 为本页最后一项的序号，否则为 null。非法参数 422 `VALIDATION_ERROR`。
- 草稿与正式指控里的步骤重复、证据重复、关联重复都返回 422 `INVALID_ACCUSATION_OPTION`（与 domain 一致）；
  缺字段、类型错误仍是 `VALIDATION_ERROR`。

### 5.1 DTO 变化

- `SessionView` 新增 `relationships`、`timeline`、`accusation_draft`（`AccusationContent`，空草稿为
  null 选择和空数组）、`pending_conversations`（本阶段恒为 `[]`）；`scenes` 只含已开放场景；
  `npcs` 为四名可审讯人物。
- `SceneView` 不变；`InvestigationOption.disabled_reason` 只说“核对条件尚不齐全。”或“当前阶段不能调查。”，
  不点名证据。
- `EvidenceView` 新增 `kind`、`key_badge`（`show_key_badges && is_key`）、`known_conflicts: []`、`links: []`；
  `source` 为 `{kind: "SCENE", id: 授予它的动作所在场景, label: 证据来源}`。
- `NpcView` 新增 `known_statements`（本人物为说话人且已披露的 `KnownInformation`）；
  保留 `fixed_statement`（仅当前审讯对象非空）与 `presented_evidence_ids`；
  `admission_progress`、`display_state` 按 3.5。
- `KnownInformation.source`：`PUBLIC` 为 `{kind: "PUBLIC", id: null, label: "案件公开信息"}`，
  其他为 `{kind: "NPC", id: 说话人, label: 姓名}`。
- `PlayerOutcome` 新增 `updated_evidence: []`、`unlocked_scenes: SceneView[]`（本次新开放的场景）、
  `relationships_changed`、`timeline_changed`（本次可见条目集合是否变化）。
- `Verdict` 新增 `fixed_explanation`；`CriterionResult` 新增 `missing_evidence_ids`。
- `AccusationContent` 的三项选择改为可空；正式提交缺失时用 `ACCUSATION_INCOMPLETE`，不再用 `VALIDATION_ERROR`。
- `available_actions` 增加 `SAVE_ACCUSATION_DRAFT`（A 阶段）。
- `RelationshipGraph`、`TimelineView`、`ConversationView`、`ConversationPage` 字段按第 10 篇 5.3、5.4；
  关系边的 `source` 用 `PublicSource`（EVIDENCE 的 label 为证据名，NPC 为姓名，PUBLIC 为“案件公开信息”），
  `discovered_at` 取揭示它的证据或知识的最早登记时间，公开条目为 null。

### 5.2 固定模式的对话

- 聊天：`ChatRequest {message}`，只在 T 且 `npc_id == active_npc_id`。创建一轮 `conversation`
  （`interaction_type=CHAT`）：玩家消息 `origin=PLAYER`，NPC 消息 `origin=FIXED`、内容为 `current_statement`。
  `generation_status=FALLBACK`、`fallback_reason=GENERATION_DISABLED`、`can_retry_reply=false`、
  `completed_at` 非空。返回 201，`business_status=COMMITTED`、`state_changed=false`、版本不变，
  `data={conversation_id}`，`Location` 指向该轮。
- 出示：规则事务内同时创建一轮 `interaction_type=EVIDENCE_PRESENTATION`，玩家消息为
  `出示证据：{证据编号} {证据名}`（有附言时另起一行 `附言：…`），NPC 消息为本次的 `fixed_reply`。
  `data` 为 `{npc_id, evidence_id, fixed_reply, outcome}`，`conversation` 为该轮 `ConversationView`。
  `Location` 指向该轮。回避中的出示同样记一轮。
- `conversation_seq` 在会话锁内按整局递增，从 1 开始。追问话题与指出矛盾不建对话轮次。
- 同键重放返回原结果，不新增轮次。

## 6. 网页（固定模式）

单页即可，不引入 Vue Router。Element Plus 默认样式。用 `data-testid` 作为测试契约：

| `data-testid` | 内容 |
| --- | --- |
| `scene-list` / `scene-{id}` | 已开放场景，每个含动作按钮 `action-{id}`（禁用时显示原因） |
| `evidence-list` / `evidence-{id}` | 背包；点击打开详情 `evidence-detail` |
| `npc-list` / `npc-{id}` | 四名人物；显示 `display_state` 的中文标签，不显示数字 |
| `interrogation-panel` | 当前人物的说法、话题按钮 `topic-{id}`、出示选择、矛盾选择、聊天输入 `chat-input` |
| `conversation-log` | 当前人物的对话轮次（按 seq 升序） |
| `relationship-list` | 已知关系，每条 `relationship-{id}` |
| `timeline-list` | 已知时间线，每条 `timeline-{id}`，`UNKNOWN` 显示 `time_label` |
| `accusation-form` | 指控表单；`save-draft` 保存草稿；`confirm-accusation` 是确认复选框（内含 `input`），勾选前 `submit-accusation` 为 disabled，勾选后点击即以 `confirm: true` 正式提交 |
| `review-panel` | 判定、逐项结果（含缺失证据）、真相、遗漏证据 |
| `evidence-detail` | 点击背包中的 `evidence-{id}` 后显示的详情（正文与来源） |

读取约定（测试据此 stub，页面不得发出额外请求）：加载只读 `POST /visitors`、`GET /cases`、`GET /sessions/current`
（`SessionView` 已包含场景、背包、人物、关系、时间线和草稿）；当前处于审讯时再读
`GET /sessions/{id}/npcs/{npc_id}/conversations?limit=20`，按 `conversation_seq` 升序展示；
处于 R/F 时读 `GET /sessions/{id}/review`。写操作成功后按 v0.2 的方式刷新当前会话。

只在服务器确认后显示成功；`ACCUSATION_INCOMPLETE` 在表单内提示，不清空已填内容。
前端源码与构建产物不得包含案件文件或答案标记（沿用 `no-case-data.test.ts`，标记列表补上 `case.json` 的
`L02` 承认句与 `"core_lie_ids"`）。

## 7. 命令行

`truing-play` 改为加载 `case.json`：`look` 列出已开放场景与动作，`inspect <动作>` 不再需要场景，
`talk <人物>`、`topic`、`contradict`、`present`、`back`、`accuse`、`submit`、`review`、`quit` 沿用。
README 中的示例路径同步更新。

## 8. 验收测试

`docs/specs/v0.3/tests/` 下的文件，启用方式见 [README](../README.md)：

| 文件 | 覆盖 |
| --- | --- |
| `backend/tests/data/expected/full_case_verdicts.json` | 13 组人工评分预期（手工计算，不得用评分函数生成） |
| `backend/tests/data/expected/full_case_paths.json` | 无招供路径、全承认路径的逐步预期 |
| `backend/tests/domain/test_case_v3_validation.py` | 2.2 的每条拒绝规则；正式案件通过 |
| `backend/tests/domain/test_full_case_rules.py` | 场景开放、深入调查、四层谎言的正序逆序、无关与回避、话题与矛盾、说法、展示状态、评分预期 |
| `backend/tests/domain/test_phase_matrix.py` | 六阶段 × 全部动作 |
| `backend/tests/player.py` | 替换 v0.2 的测试玩家：自动按动作找场景 |
| `backend/tests/api/test_full_case_flow.py` | 无招供 100 分、含承认路径、三结局、重启续玩 |
| `backend/tests/api/test_read_endpoints.py` | 新 GET 端点、404 隐藏、GET 无副作用 |
| `backend/tests/api/test_conversations.py` | 固定模式聊天与出示的对话轮次、分页、幂等 |
| `backend/tests/api/test_accusation_draft.py` | 草稿保存、保留、校验、提交冻结 |
| `backend/tests/api/test_no_leaks.py` | 结案前所有响应不含秘密标记 |
| `backend/tests/integration/test_migration_0003.py` | 带切片数据升级、旧存档不可继续、降级 |
| `frontend/tests/full-case.test.ts` | `data-testid` 契约与关键交互 |

v0.2 已有测试中依赖 `case.npc`、`case.lie`、`state.npc`、`S01` 固定场景的，移植到新结构；
`week_one_verdicts.json` 与切片专属用例在被上表覆盖后删除，并记入 `test-amendments.md`。

## 9. 交付（T14）

1. 干净克隆按 README 安装、迁移、导入 `case.json`、跑全部检查。
2. 浏览器手动走一遍第 1 节的演示，记录结果。
3. 写 `docs/19-v0.3-delivery.md`：范围、与设计文档的差异、验证记录、已知限制；
   复核 W1 遗留的“预期待真人复核”事项，如实写明仍未完成的部分。
4. README：当前状态、导入命令（`case.json`）、CLI 示例、新增端点说明。
5. 打 `v0.3` 标签。这个标签是之后所有版本的回退基线。
