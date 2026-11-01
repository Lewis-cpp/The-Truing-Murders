import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from backend.domain.evidence import knowledge_speaker
from backend.domain.models import (
    Case,
    GameState,
    LieStage,
    NPCState,
    Phase,
)
from backend.domain.rules import chains_of, lie_by_id, present


def default_case_path() -> Path:
    # Editable checkout and packaged wheel both carry the same versioned resource.
    package = Path(__file__).resolve().parents[1] / "case_data/case_001/v1/case.json"
    if package.is_file():
        return package
    return Path(__file__).resolve().parents[3] / "assets/cases/case_001/v1/case.json"


def _unique(values, label: str) -> set[str]:
    items = list(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{label} 含有重复 ID。")
    return set(items)


def _require_dependency(dep, evidence_ids: set[str], label: str) -> None:
    if not (set(dep.all_of) | set(dep.any_of)) <= evidence_ids:
        raise ValueError(f"{label}引用了不存在的证据。")


def validate_case(case: Case) -> None:
    """Every publication rule of schema 3 (spec 2.2); a failure rejects the whole file."""
    characters = {c.id: c for c in case.characters}
    character_ids = _unique((c.id for c in case.characters), "人物")
    scene_ids = _unique((s.id for s in case.scenes), "场景")
    action_ids = _unique((a.id for s in case.scenes for a in s.actions), "调查动作")
    evidence_ids = _unique((e.id for e in case.evidence), "证据")
    knowledge_map = {k.id: k for k in case.knowledge}
    knowledge_ids = _unique((k.id for k in case.knowledge), "知识")
    lie_map = {lie.id: lie for lie in case.lies}
    lie_ids = _unique((lie.id for lie in case.lies), "谎言层")
    _unique((chain.id for chain in case.lie_chains), "谎言链")
    _unique((t.id for t in case.interrogation.topics), "话题")
    _unique((c.id for c in case.interrogation.contradictions), "矛盾")
    _unique((r.id for r in case.relationships), "关系")
    timeline_map = {t.id: t for t in case.timeline}
    _unique((t.id for t in case.timeline), "时间线")
    _unique((c.id for c in case.scoring.criteria), "评分项")
    suspects = _unique((c.id for c in case.suspects), "嫌疑人")
    weapons = _unique((c.id for c in case.weapons), "凶器")
    motives = _unique((c.id for c in case.motives), "动机")
    steps = _unique((c.id for c in case.process_steps), "步骤")
    del action_ids, knowledge_ids, lie_ids, suspects, weapons, motives

    # 2. Every reference must exist.
    granted: set[str] = set()
    for scene in case.scenes:
        _require_dependency(scene.unlock, evidence_ids, "场景开放条件")
        for action in scene.actions:
            if action.evidence_id not in evidence_ids:
                raise ValueError("调查动作授予的证据不存在。")
            granted.add(action.evidence_id)
            _require_dependency(action.requires, evidence_ids, "调查动作前置")
    if granted != set(evidence_ids):
        raise ValueError("存在不被任何调查动作授予的证据。")
    _require_dependency(case.deep_unlock, evidence_ids, "深入调查条件")
    for lie in case.lies:
        _require_dependency(lie.counterevidence, evidence_ids, "反证")
        _require_dependency(lie.admission_presented, evidence_ids, "承认材料")
    for knowledge in case.knowledge:
        if not knowledge.known_by or not set(knowledge.known_by) <= set(character_ids):
            raise ValueError("知识归属缺失或角色不存在。")
    for character in case.characters:
        if not set(character.core_lie_ids) <= set(lie_map):
            raise ValueError("core_lie_ids 引用了不存在的谎言层。")

    # 3. All evidence reachable from an empty start; lie progress is never a prerequisite.
    reached: frozenset[str] = frozenset()
    while True:
        opened = {s.id for s in case.scenes if s.unlock.satisfied(reached)}
        next_reached = reached | {
            a.evidence_id
            for s in case.scenes
            if s.id in opened
            for a in s.actions
            if a.requires.satisfied(reached)
        }
        if next_reached == reached:
            break
        reached = next_reached
    if reached != set(evidence_ids):
        raise ValueError("存在不可达证据或阻断通关的循环依赖。")

    # 4. At least one scene is open at the start.
    if not any(not scene.unlock.all_of and not scene.unlock.any_of for scene in case.scenes):
        raise ValueError("必须存在开局即开放的场景。")

    # 5. Interrogatable characters and suspects.
    for character in case.characters:
        if not character.interrogatable:
            continue
        if character.initial_pressure is None or character.initial_trust is None:
            raise ValueError("可审讯人物必须配置初始压力与信任。")
        if character.personality is None or character.speech_style is None:
            raise ValueError("可审讯人物必须配置性格与说话风格。")
        if not chains_of(case, character.id) and character.default_reply is None:
            raise ValueError("没有谎言链的可审讯人物必须配置默认回复。")
    for choice in case.suspects:
        if choice.id not in characters or not characters[choice.id].interrogatable:
            raise ValueError("嫌疑人候选必须是可审讯人物。")

    # 6. Lie layers and chains.
    chain_of: dict[str, str] = {}
    for chain in case.lie_chains:
        if not chain.lie_ids:
            raise ValueError("谎言链不能为空。")
        if chain.npc_id not in characters or not characters[chain.npc_id].interrogatable:
            raise ValueError("谎言链必须属于可审讯人物。")
        for lie_id in chain.lie_ids:
            if lie_id not in lie_map:
                raise ValueError("谎言链引用了不存在的谎言层。")
            if lie_id in chain_of:
                raise ValueError("每个谎言层必须恰好属于一条链。")
            if lie_map[lie_id].npc_id != chain.npc_id:
                raise ValueError("谎言链的角色与层不一致。")
            chain_of[lie_id] = chain.id
    if set(chain_of) != set(lie_map):
        raise ValueError("每个谎言层必须恰好属于一条链。")
    admitted_refs: dict[str, str] = {}
    effects_by_npc: dict[str, set[str]] = {}
    for lie in case.lies:
        if not (lie.counterevidence.all_of or lie.counterevidence.any_of):
            raise ValueError("谎言层必须具有反证硬门槛。")
        if lie.admission_pressure_min is None and lie.admission_trust_min is None:
            raise ValueError("谎言层必须显式启用至少一条心理门槛。")
        knowledge = knowledge_map.get(lie.admitted_knowledge_id)
        if knowledge is None or knowledge.disclosure != "ADMITTED":
            raise ValueError("承认必须披露一条 ADMITTED 知识。")
        if lie.npc_id not in knowledge.known_by:
            raise ValueError("承认知识的说话人必须在该知识的 known_by 中。")
        if lie.admitted_knowledge_id in admitted_refs:
            raise ValueError("每条 ADMITTED 知识必须被恰好一层引用。")
        admitted_refs[lie.admitted_knowledge_id] = lie.id
        layer_refs = (
            set(lie.counterevidence.all_of)
            | set(lie.counterevidence.any_of)
            | set(lie.admission_presented.all_of)
            | set(lie.admission_presented.any_of)
        )
        effect_ids = _unique((effect.evidence_id for effect in lie.effects), "层内效果证据")
        if not set(effect_ids) <= layer_refs:
            raise ValueError("效果证据必须是本层反证或承认材料之一。")
        seen = effects_by_npc.setdefault(lie.npc_id, set())
        if seen & set(effect_ids):
            raise ValueError("同一人物的不同层不能对同一证据都配置效果。")
        seen |= set(effect_ids)
    for knowledge in case.knowledge:
        if knowledge.disclosure == "ADMITTED" and knowledge.id not in admitted_refs:
            raise ValueError("存在没有被任何谎言层引用的 ADMITTED 知识。")
    for character in case.characters:
        for lie_id in character.core_lie_ids:
            if lie_map[lie_id].npc_id != character.id:
                raise ValueError("core_lie_ids 只能引用本人物的谎言层。")

    # 7. Every chain must be able to reach a full admission from the worst trust of 0.
    for chain in case.lie_chains:
        character = characters[chain.npc_id]
        npc = NPCState(
            character.initial_pressure,
            0,
            {lie_id: LieStage.UNBROKEN for lie_id in chain.lie_ids},
        )
        state = GameState(
            npcs={chain.npc_id: npc},
            phase=Phase.INTERROGATION,
            active_npc_id=chain.npc_id,
            evidence_ids=frozenset(evidence_ids),
        )
        for lie_id in chain.lie_ids:
            lie = lie_by_id(case, lie_id)
            materials = (
                set(lie.counterevidence.all_of)
                | set(lie.counterevidence.any_of)
                | set(lie.admission_presented.all_of)
                | set(lie.admission_presented.any_of)
            )
            for evidence_id in sorted(materials):
                state = present(case, state, chain.npc_id, evidence_id)
        if not all(
            state.npcs[chain.npc_id].lies[lie_id] == LieStage.ADMITTED for lie_id in chain.lie_ids
        ):
            raise ValueError("承认不可达：反证、可信度或心理门槛使某层无法被承认。")

    # 8. Topics.
    topics_by_knowledge: dict[str, str] = {}
    for topic in case.interrogation.topics:
        character = characters.get(topic.npc_id)
        if character is None or not character.interrogatable:
            raise ValueError("话题必须属于可审讯人物。")
        knowledge = knowledge_map.get(topic.knowledge_id)
        if knowledge is None or knowledge.disclosure != "ASKED":
            raise ValueError("话题必须登记一条 ASKED 知识。")
        if topic.npc_id not in knowledge.known_by:
            raise ValueError("话题的说话人必须在该知识的 known_by 中。")
        if topic.knowledge_id in topics_by_knowledge:
            raise ValueError("每条 ASKED 知识必须恰好有一个话题。")
        topics_by_knowledge[topic.knowledge_id] = topic.id
    for knowledge in case.knowledge:
        if knowledge.disclosure == "ASKED" and knowledge.id not in topics_by_knowledge:
            raise ValueError("存在没有话题的 ASKED 知识。")

    # 9. Contradictions.
    _unique(
        ((c.npc_id, c.knowledge_id, c.evidence_id) for c in case.interrogation.contradictions),
        "矛盾配对",
    )
    verified = {e.id for e in case.evidence if e.credibility == "VERIFIED"}
    for contradiction in case.interrogation.contradictions:
        knowledge = knowledge_map.get(contradiction.knowledge_id)
        if knowledge is None or knowledge.disclosure == "PUBLIC":
            raise ValueError("矛盾必须引用一条私有证词。")
        if knowledge_speaker(case, contradiction.knowledge_id) != contradiction.npc_id:
            raise ValueError("矛盾的证词说话人必须是该人物。")
        if contradiction.evidence_id not in set(evidence_ids):
            raise ValueError("矛盾引用的证据不存在。")
        if contradiction.evidence_id not in verified:
            raise ValueError("矛盾所依据的证据必须有核验来源。")

    # 10. Relationships.
    for relationship in case.relationships:
        if relationship.from_id not in characters or relationship.to_id not in characters:
            raise ValueError("关系端点必须是已定义的人物。")
        if not set(relationship.reveal_evidence_ids) <= set(evidence_ids) or not set(
            relationship.reveal_knowledge_ids
        ) <= set(knowledge_map):
            raise ValueError("关系揭示条件引用不存在。")
        if relationship.source_kind == "PUBLIC":
            if (
                relationship.source_id is not None
                or relationship.reveal_evidence_ids
                or relationship.reveal_knowledge_ids
            ):
                raise ValueError("公开关系不能配置来源或揭示条件。")
        elif relationship.source_kind == "EVIDENCE":
            if relationship.source_id not in relationship.reveal_evidence_ids:
                raise ValueError("证据来源关系必须揭示其来源证据。")
        elif relationship.source_id not in characters:
            raise ValueError("角色来源关系必须指向已定义的人物。")

    # 11. Timeline.
    for event in case.timeline:
        if event.scene_id is not None and event.scene_id not in set(scene_ids):
            raise ValueError("时间线场景不存在。")
        if not set(event.participant_ids) <= set(character_ids):
            raise ValueError("时间线参与者不存在。")
        if not set(event.reveal_evidence_ids) <= set(evidence_ids) or not set(
            event.reveal_knowledge_ids
        ) <= set(knowledge_map):
            raise ValueError("时间线揭示条件引用不存在。")
        if event.precision == "EXACT":
            if event.start_minutes is None or event.start_minutes != event.end_minutes:
                raise ValueError("EXACT 事件的起止必须相等且非空。")
        elif event.precision == "RANGE":
            if (
                event.start_minutes is None
                or event.end_minutes is None
                or event.start_minutes > event.end_minutes
            ):
                raise ValueError("RANGE 事件必须配置合法的起止分钟。")
        elif event.start_minutes is not None or event.end_minutes is not None:
            raise ValueError("UNKNOWN 事件不能配置分钟数。")
        for other in event.conflicts_with:
            counterpart = timeline_map.get(other)
            if (
                other == event.id
                or counterpart is None
                or event.id not in counterpart.conflicts_with
            ):
                raise ValueError("时间线冲突不能指向自身，且必须对称。")

    _validate_scoring(case, evidence_ids, verified, steps)


def _validate_scoring(case: Case, evidence_ids: set[str], verified: set[str], steps) -> None:
    truth_ok = (
        case.truth.culprit in {c.id for c in case.suspects}
        and case.truth.weapon in {c.id for c in case.weapons}
        and case.truth.motive in {c.id for c in case.motives}
        and bool(case.truth.steps)
        and set(case.truth.steps) <= steps
    )
    if not truth_ok:
        raise ValueError("真相必须引用合法的候选项和非空步骤。")
    _unique(case.truth.steps, "真相步骤")
    scoring = case.scoring
    if not 0 < scoring.partial_min < scoring.correct_min <= 100:
        raise ValueError("评分阈值必须满足 0 < 部分正确 < 正确 <= 100。")
    if sum(c.points for c in scoring.criteria) != 100:
        raise ValueError("评分权重总和必须为 100。")
    for kind in ("culprit", "weapon", "motive", "process"):
        if sum(c.kind == kind for c in scoring.criteria) != 1:
            raise ValueError("凶手、凶器、动机和过程必须各有一个评分项。")
    for criterion in scoring.criteria:
        _unique(criterion.evidence_ids, "评分证据")
        if criterion.kind == "support":
            if (
                criterion.step_id not in case.truth.steps
                or not criterion.evidence_ids
                or not set(criterion.evidence_ids) <= evidence_ids
            ):
                raise ValueError("证据评分必须引用正确步骤和非空的有效证据。")
            if not set(criterion.evidence_ids) <= verified:
                raise ValueError("评分所需证据必须有核验来源。")
        elif criterion.step_id is not None or criterion.evidence_ids:
            raise ValueError("答案评分不能夹带证据条件。")
    unsupported_max = sum(c.points for c in scoring.criteria if c.kind != "support")
    if unsupported_max >= scoring.correct_min:
        raise ValueError("无证据的猜测不能达到正确阈值。")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"案件文件含有重复的 JSON 键：{', '.join(duplicates)}")
    return dict(pairs)


def parse_case(text: str) -> Case:
    try:
        # JSON parsers silently keep the last duplicate; a reviewed case must be unambiguous.
        json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        case = Case.model_validate_json(text)
    except (ValidationError, json.JSONDecodeError) as error:
        raise ValueError(f"案件文件结构校验失败：{error}") from error
    validate_case(case)
    return case


def load_case(path: Path | None = None) -> Case:
    try:
        text = (path or default_case_path()).read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"案件文件读取失败：{error}") from error
    return parse_case(text)


# Order-insensitive ID sets, and the collection keys whose element order is not part of the
# definition. Order-sensitive lists (truth steps, chain layer order) are kept as stored.
_SORTED_ID_LISTS = frozenset(
    {
        "all_of",
        "any_of",
        "known_by",
        "reveal_evidence_ids",
        "reveal_knowledge_ids",
        "conflicts_with",
        "participant_ids",
        "core_lie_ids",
        "evidence_ids",
    }
)


def _canonical(value):
    if isinstance(value, dict):
        result = {key: _canonical(item) for key, item in value.items()}
        for key, item in result.items():
            if isinstance(item, list) and item and isinstance(item[0], dict):
                sort_key = "id" if "id" in item[0] else "evidence_id"
                result[key] = sorted(item, key=lambda entry: entry[sort_key])
            elif key in _SORTED_ID_LISTS and isinstance(item, list):
                result[key] = sorted(item)
        return result
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def content_hash(case: Case) -> str:
    """SHA-256 of the canonical definition: sorted keys and ID sets, ordered steps kept."""
    data = _canonical(case.model_dump(mode="json"))
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()
