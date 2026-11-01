from dataclasses import replace

from backend.domain.evidence import (
    knowledge_speaker,
    require_held,
    validate_accusation,
    validate_draft,
)
from backend.domain.models import (
    Accusation,
    AccusationDraft,
    Case,
    CriterionResult,
    GameError,
    GameState,
    Lie,
    LieChain,
    LieStage,
    NPCState,
    Phase,
    Verdict,
)
from backend.domain.state_machine import evading, guard

# Semantics of these functions; stored with each event and verdict to detect incompatible saves.
RULE_EXECUTION_VERSION = "full-1"

FIXED_EXPLANATIONS = {
    "正确": "推理成立：凶手、凶器、动机与关键依据基本吻合。",
    "部分正确": "推理部分成立：请对照逐项结果查看缺失的依据。",
    "错误": "推理不成立：凶手判断或关键依据与事实不符。",
}


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def lie_by_id(case: Case, lie_id: str) -> Lie:
    return next(lie for lie in case.lies if lie.id == lie_id)


def chains_of(case: Case, npc_id: str) -> tuple[LieChain, ...]:
    return tuple(chain for chain in case.lie_chains if chain.npc_id == npc_id)


def _relevant_layers(case: Case, npc_id: str, stages) -> list[Lie]:
    """Admitted layers plus the current (first unadmitted) layer of every chain."""
    layers = []
    for chain in chains_of(case, npc_id):
        for lie_id in chain.lie_ids:
            if stages[lie_id] == LieStage.ADMITTED:
                layers.append(lie_by_id(case, lie_id))
        current = next((lid for lid in chain.lie_ids if stages[lid] != LieStage.ADMITTED), None)
        if current is not None:
            layers.append(lie_by_id(case, current))
    return layers


def relevant_evidence(case: Case, state: GameState, npc_id: str) -> frozenset[str]:
    """Materials of the NPC's relevant layers; anything else is an irrelevant move."""
    refs: list[str] = []
    for lie in _relevant_layers(case, npc_id, state.npcs[npc_id].lies):
        refs += (
            *lie.counterevidence.all_of,
            *lie.counterevidence.any_of,
            *lie.admission_presented.all_of,
            *lie.admission_presented.any_of,
        )
        refs += [effect.evidence_id for effect in lie.effects]
    return frozenset(refs)


def citable_testimony(case: Case, state: GameState, npc_id: str) -> frozenset[str]:
    """Disclosed, non-public knowledge whose speaker is this NPC."""
    return frozenset(
        k.id
        for k in case.knowledge
        if k.disclosure != "PUBLIC"
        and k.id in state.disclosed_knowledge
        and knowledge_speaker(case, k.id) == npc_id
    )


def new_game(case: Case) -> GameState:
    npcs: dict[str, NPCState] = {}
    for character in case.characters:
        if not character.interrogatable:
            continue
        lies = {
            lie_id: LieStage.UNBROKEN
            for chain in chains_of(case, character.id)
            for lie_id in chain.lie_ids
        }
        npcs[character.id] = NPCState(character.initial_pressure, character.initial_trust, lies)
    return GameState(npcs=npcs)


def open_scenes(case: Case, state: GameState) -> tuple[str, ...]:
    """Scenes whose unlock is satisfied by held evidence, in case order; unlocks never revoke."""
    return tuple(scene.id for scene in case.scenes if scene.unlock.satisfied(state.evidence_ids))


def _check_deep_unlock(case: Case, state: GameState) -> GameState:
    has_branch = bool(case.deep_unlock.all_of or case.deep_unlock.any_of)
    triggered = (has_branch and case.deep_unlock.satisfied(state.evidence_ids)) or any(
        stage != LieStage.UNBROKEN for npc in state.npcs.values() for stage in npc.lies.values()
    )
    if not triggered or state.deep_unlocked:
        return state
    if state.phase == Phase.INVESTIGATION:
        return replace(state, deep_unlocked=True, phase=Phase.DEEP_INVESTIGATION)
    return replace(state, deep_unlocked=True)


def _require_active(state: GameState, npc_id: str) -> None:
    if npc_id != state.active_npc_id:
        raise GameError("只能对当前审讯的角色操作。", "ACTIVE_NPC_MISMATCH")


def investigate(case: Case, state: GameState, action_id: str) -> GameState:
    guard(state, "inspect")
    action = next((a for scene in case.scenes for a in scene.actions if a.id == action_id), None)
    if action is None:
        raise GameError("调查点不存在，请查看已开放的场景。", "INVALID_ACTION_REFERENCE")
    scene = next(scene for scene in case.scenes if action in scene.actions)
    if scene.id not in open_scenes(case, state):
        raise GameError("场景不存在或尚未开放。", "SCENE_NOT_FOUND")
    if action.id in state.completed_actions:
        return state
    if not action.requires.satisfied(state.evidence_ids):
        raise GameError("核对条件尚不齐全。请检查其他调查点，再回来重试。", "ACTION_UNAVAILABLE")
    after = replace(
        state,
        evidence_ids=state.evidence_ids | {action.evidence_id},
        completed_actions=state.completed_actions | {action.id},
    )
    return _check_deep_unlock(case, after)


def present(case: Case, state: GameState, npc_id: str, evidence_id: str) -> GameState:
    """The fixed four-step evaluation: relevance, effects, breaking, admission."""
    guard(state, "present")
    _require_active(state, npc_id)
    require_held(state, evidence_id)
    npc = state.npcs[npc_id]
    if evading(case, npc):
        return state
    relevant = relevant_evidence(case, state, npc_id)
    npc = replace(npc, presented=npc.presented | {evidence_id})
    consumed = state.consumed_effects
    if evidence_id not in relevant:
        key = f"irrelevant:{npc_id}:{evidence_id}"
        if key not in consumed:
            npc = replace(npc, trust=_clamp(npc.trust + case.interrogation.irrelevant_trust))
            consumed = consumed | {key}
        npc = replace(npc, irrelevant_streak=npc.irrelevant_streak + 1)
        return replace(state, npcs={**state.npcs, npc_id: npc}, consumed_effects=consumed)
    npc = replace(npc, irrelevant_streak=0)
    stages_s0 = dict(npc.lies)
    key = f"present:{npc_id}:{evidence_id}"
    evidence = next(e for e in case.evidence if e.id == evidence_id)
    if evidence.credibility == "VERIFIED" and key not in consumed:
        effects = [
            effect
            for lie in _relevant_layers(case, npc_id, stages_s0)
            for effect in lie.effects
            if effect.evidence_id == evidence_id
        ]
        npc = replace(
            npc,
            pressure=_clamp(npc.pressure + sum(e.pressure for e in effects)),
            trust=_clamp(npc.trust + sum(e.trust for e in effects)),
        )
        consumed = consumed | {key}
    verified = frozenset(
        e.id for e in case.evidence if e.id in npc.presented and e.credibility == "VERIFIED"
    )
    new_lies = dict(npc.lies)
    for chain in chains_of(case, npc_id):
        for index, lie_id in enumerate(chain.lie_ids):
            lie = lie_by_id(case, lie_id)
            if stages_s0[lie_id] != LieStage.UNBROKEN or not _prerequisite_met(
                chain, index, stages_s0
            ):
                continue
            if lie.counterevidence.satisfied(verified):
                new_lies[lie_id] = LieStage.BROKEN
    disclosed = state.disclosed_knowledge
    for chain in chains_of(case, npc_id):
        for index, lie_id in enumerate(chain.lie_ids):
            lie = lie_by_id(case, lie_id)
            if new_lies[lie_id] != LieStage.BROKEN or not _prerequisite_met(
                chain, index, stages_s0
            ):
                continue
            if not lie.admission_presented.satisfied(verified):
                continue
            ready = (
                lie.admission_pressure_min is not None
                and npc.pressure >= lie.admission_pressure_min
            ) or (lie.admission_trust_min is not None and npc.trust >= lie.admission_trust_min)
            if ready:
                new_lies[lie_id] = LieStage.ADMITTED
                disclosed = disclosed | {lie.admitted_knowledge_id}
    npc = replace(npc, lies=new_lies)
    after = replace(
        state,
        npcs={**state.npcs, npc_id: npc},
        consumed_effects=consumed,
        disclosed_knowledge=disclosed,
    )
    return _check_deep_unlock(case, after)


def _prerequisite_met(chain: LieChain, index: int, stages_s0: dict) -> bool:
    """A layer may be re-evaluated only if the previous one was admitted before this move."""
    return index == 0 or stages_s0[chain.lie_ids[index - 1]] == LieStage.ADMITTED


def ask_topic(case: Case, state: GameState, npc_id: str, topic_id: str) -> GameState:
    """Records the fixed answer as testimony. It never moves numbers, lies or evasion."""
    guard(state, "topic")
    _require_active(state, npc_id)
    topic = next(
        (t for t in case.interrogation.topics if t.id == topic_id and t.npc_id == npc_id), None
    )
    if topic is None:
        raise GameError("该话题不存在。", "INVALID_ACTION_REFERENCE")
    if evading(case, state.npcs[npc_id]):
        return state
    return replace(state, disclosed_knowledge=state.disclosed_knowledge | {topic.knowledge_id})


def find_contradiction(case: Case, npc_id: str, knowledge_id: str, evidence_id: str):
    return next(
        (
            c
            for c in case.interrogation.contradictions
            if (c.npc_id, c.knowledge_id, c.evidence_id) == (npc_id, knowledge_id, evidence_id)
        ),
        None,
    )


def contradict(
    case: Case, state: GameState, npc_id: str, knowledge_id: str, evidence_id: str
) -> GameState:
    """Judges a pairing against the preset table only; a wrong pairing costs like a bad
    presentation. A valid one moves numbers once and never breaks or admits a lie itself."""
    guard(state, "contradict")
    _require_active(state, npc_id)
    # One message for unknown, hidden and public entries, so the reply reveals no hidden IDs.
    if knowledge_id not in citable_testimony(case, state, npc_id):
        raise GameError("只能引用已经记录的该角色证词。", "INVALID_ACTION_REFERENCE")
    require_held(state, evidence_id)
    npc = state.npcs[npc_id]
    if evading(case, npc):
        return state
    consumed = state.consumed_effects
    match = find_contradiction(case, npc_id, knowledge_id, evidence_id)
    if match is None:
        key = f"mismatch:{npc_id}:{knowledge_id}:{evidence_id}"
        if key not in consumed:
            npc = replace(npc, trust=_clamp(npc.trust + case.interrogation.irrelevant_trust))
            consumed = consumed | {key}
        npc = replace(npc, irrelevant_streak=npc.irrelevant_streak + 1)
        return replace(state, npcs={**state.npcs, npc_id: npc}, consumed_effects=consumed)
    npc = replace(npc, irrelevant_streak=0)
    key = f"contradiction:{npc_id}:{match.id}"
    if key not in consumed:
        npc = replace(
            npc,
            pressure=_clamp(npc.pressure + match.pressure),
            trust=_clamp(npc.trust + match.trust),
        )
        consumed = consumed | {key}
    return replace(state, npcs={**state.npcs, npc_id: npc}, consumed_effects=consumed)


def save_draft(case: Case, state: GameState, draft: AccusationDraft) -> GameState:
    guard(state, "draft")
    validate_draft(case, state, draft)
    if state.draft == draft:
        return state
    return replace(state, draft=draft)


# Outcome codes of an interrogation move, decided once for the CLI and the API.


def _setback(case: Case, before: NPCState, after: NPCState) -> str:
    if not evading(case, before) and evading(case, after):
        return "EVASION_STARTED"
    return "IRRELEVANT_MOVE"


def topic_outcome(case: Case, before: GameState, knowledge_id: str) -> str:
    npc = before.npcs.get(before.active_npc_id) if before.active_npc_id else None
    if npc is not None and evading(case, npc):
        return "NPC_EVADING"
    if knowledge_id in before.disclosed_knowledge:
        return "TOPIC_ALREADY_ASKED"
    return "TESTIMONY_RECORDED"


def present_outcome(
    case: Case, before: GameState, after: GameState, npc_id: str, evidence_id: str
) -> str:
    before_npc = before.npcs[npc_id]
    after_npc = after.npcs[npc_id]
    if evading(case, before_npc):
        return "NPC_EVADING"
    if evidence_id not in relevant_evidence(case, before, npc_id):
        return _setback(case, before_npc, after_npc)
    if any(after_npc.lies[k] != before_npc.lies[k] for k in before_npc.lies):
        if any(
            after_npc.lies[k] == LieStage.ADMITTED and before_npc.lies[k] != LieStage.ADMITTED
            for k in before_npc.lies
        ):
            return "ADMISSION_RECORDED"
        return "LIE_BROKEN"
    if evidence_id in before_npc.presented and after.consumed_effects == before.consumed_effects:
        return "ALREADY_PRESENTED"
    return "EVIDENCE_RECORDED"


def contradiction_outcome(case: Case, before: GameState, after: GameState, matched: bool) -> str:
    npc = before.npcs.get(before.active_npc_id) if before.active_npc_id else None
    if npc is not None and evading(case, npc):
        return "NPC_EVADING"
    if not matched:
        return _setback(case, npc, after.npcs[after.active_npc_id])
    if after.consumed_effects == before.consumed_effects:
        return "CONTRADICTION_ALREADY_POINTED"
    return "CONTRADICTION_CONFIRMED"


def judge(case: Case, state: GameState, accusation: Accusation) -> GameState:
    guard(state, "submit")
    validate_accusation(case, state, accusation)
    linked = {(link.step_id, link.evidence_id) for link in accusation.evidence_links}
    verified = {e.id for e in case.evidence if e.credibility == "VERIFIED"}
    results = []
    for criterion in case.scoring.criteria:
        missing: list[str] = []
        if criterion.kind == "support":
            missing = [
                evidence_id
                for evidence_id in criterion.evidence_ids
                if (criterion.step_id, evidence_id) not in linked
            ]
            matches = all(
                (criterion.step_id, evidence_id) in linked and evidence_id in verified
                for evidence_id in criterion.evidence_ids
            )
        elif criterion.kind == "process":
            matches = accusation.steps == case.truth.steps
        else:
            matches = getattr(accusation, criterion.kind) == getattr(case.truth, criterion.kind)
        results.append(
            CriterionResult(
                criterion.id,
                criterion.label,
                criterion.points if matches else 0,
                criterion.points,
                ("命中：" if matches else "未命中：") + criterion.explanation,
                missing,
            )
        )
    score = sum(result.points for result in results)
    if case.scoring.wrong_culprit_is_wrong and accusation.culprit != case.truth.culprit:
        category = "错误"
    elif score >= case.scoring.correct_min:
        category = "正确"
    elif score >= case.scoring.partial_min:
        category = "部分正确"
    else:
        category = "错误"
    draft = AccusationDraft(
        culprit=accusation.culprit,
        weapon=accusation.weapon,
        motive=accusation.motive,
        steps=accusation.steps,
        cited_evidence_ids=accusation.cited_evidence_ids,
        evidence_links=accusation.evidence_links,
        explanation=accusation.explanation,
    )
    return replace(
        state,
        phase=Phase.REVIEW,
        active_npc_id=None,
        draft=draft,
        verdict=Verdict(
            category,
            score,
            tuple(results),
            accusation,
            state.evidence_ids,
            case.version,
            case.rules_version,
            FIXED_EXPLANATIONS[category],
        ),
    )
