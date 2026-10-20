from dataclasses import replace

from backend.domain.evidence import require_held, validate_accusation
from backend.domain.models import (
    Accusation,
    Case,
    CriterionResult,
    GameError,
    GameState,
    LieStage,
    NPCState,
    Phase,
    Verdict,
)
from backend.domain.state_machine import evading, guard

# Semantics of these functions; stored with each event and verdict to detect incompatible saves.
RULE_EXECUTION_VERSION = "w1-slice-2"


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def relevant_evidence(case: Case, npc_id: str) -> frozenset[str]:
    """Evidence the NPC's current lie layer refers to; anything else is an irrelevant move."""
    lie = case.lie
    if lie.npc_id != npc_id:
        return frozenset()
    return frozenset(
        (*lie.counterevidence.all_of, *lie.counterevidence.any_of)
        + (*lie.admission_presented.all_of, *lie.admission_presented.any_of)
        + tuple(effect.evidence_id for effect in lie.effects)
    )


def citable_testimony(case: Case, state: GameState, npc_id: str) -> frozenset[str]:
    """Recorded words of this NPC: disclosed, non-public knowledge the NPC holds."""
    return frozenset(
        k.id
        for k in case.knowledge
        if k.disclosure != "PUBLIC" and k.id in state.disclosed_knowledge and npc_id in k.known_by
    )


def _require_active(case: Case, state: GameState, npc_id: str) -> None:
    if npc_id != case.npc.id or state.active_npc_id != npc_id:
        raise GameError("只能对当前审讯的角色操作。", "ACTIVE_NPC_MISMATCH")


def _irrelevant(case: Case, npc: NPCState, consumed: frozenset[str], key: str):
    """The trust cost applies once per key; every irrelevant move still extends the streak."""
    if key not in consumed:
        npc = replace(npc, trust=_clamp(npc.trust + case.interrogation.irrelevant_trust))
        consumed = consumed | {key}
    return replace(npc, irrelevant_streak=npc.irrelevant_streak + 1), consumed


def investigate(case: Case, state: GameState, action_id: str) -> GameState:
    guard(state, "inspect")
    action = next((a for a in case.scene.actions if a.id == action_id), None)
    if action is None:
        raise GameError("调查点不存在，请查看当前场景。", "INVALID_ACTION_REFERENCE")
    if action.id in state.completed_actions:
        return state
    if not action.requires.satisfied(state.evidence_ids):
        raise GameError("核对条件尚不齐全。请检查其他调查点，再回来重试。", "ACTION_UNAVAILABLE")
    return replace(
        state,
        evidence_ids=state.evidence_ids | {action.evidence_id},
        completed_actions=state.completed_actions | {action.id},
    )


def present(case: Case, state: GameState, npc_id: str, evidence_id: str) -> GameState:
    guard(state, "present")
    _require_active(case, state, npc_id)
    require_held(state, evidence_id)
    if evading(case, state.npc):
        return state
    evidence = next(e for e in case.evidence if e.id == evidence_id)
    npc = replace(state.npc, presented=state.npc.presented | {evidence_id})
    consumed = state.consumed_effects
    if evidence_id not in relevant_evidence(case, npc_id):
        npc, consumed = _irrelevant(case, npc, consumed, f"irrelevant:{npc_id}:{evidence_id}")
        return replace(state, npc=npc, consumed_effects=consumed)
    npc = replace(npc, irrelevant_streak=0)
    key = f"present:{npc_id}:{evidence_id}"
    if evidence.credibility == "VERIFIED" and key not in consumed:
        effects = [e for e in case.lie.effects if e.evidence_id == evidence_id]
        if effects:
            npc = replace(
                npc,
                pressure=_clamp(npc.pressure + sum(e.pressure for e in effects)),
                trust=_clamp(npc.trust + sum(e.trust for e in effects)),
            )
            consumed = consumed | {key}
    verified = frozenset(
        e.id for e in case.evidence if e.id in npc.presented and e.credibility == "VERIFIED"
    )
    if npc.lie_stage == LieStage.UNBROKEN and case.lie.counterevidence.satisfied(verified):
        npc = replace(npc, lie_stage=LieStage.BROKEN)
    pressure_min = case.lie.admission_pressure_min
    trust_min = case.lie.admission_trust_min
    ready = (pressure_min is not None and npc.pressure >= pressure_min) or (
        trust_min is not None and npc.trust >= trust_min
    )
    disclosed = state.disclosed_knowledge
    if (
        npc.lie_stage == LieStage.BROKEN
        and case.lie.admission_presented.satisfied(verified)
        and ready
    ):
        npc = replace(npc, lie_stage=LieStage.ADMITTED)
        disclosed = disclosed | {case.lie.admitted_knowledge_id}
    return replace(
        state,
        npc=npc,
        consumed_effects=consumed,
        disclosed_knowledge=disclosed,
        deep_unlocked=state.deep_unlocked or npc.lie_stage != LieStage.UNBROKEN,
    )


def ask_topic(case: Case, state: GameState, npc_id: str, topic_id: str) -> GameState:
    """Records the fixed answer as testimony. It never moves numbers or the lie stage."""
    guard(state, "topic")
    _require_active(case, state, npc_id)
    topic = next(
        (t for t in case.interrogation.topics if t.id == topic_id and t.npc_id == npc_id), None
    )
    if topic is None:
        raise GameError("该话题不存在。", "INVALID_ACTION_REFERENCE")
    if evading(case, state.npc):
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
    _require_active(case, state, npc_id)
    # One message for unknown, hidden and public entries, so the reply reveals no hidden IDs.
    if knowledge_id not in citable_testimony(case, state, npc_id):
        raise GameError("只能引用已经记录的该角色证词。", "INVALID_ACTION_REFERENCE")
    require_held(state, evidence_id)
    if evading(case, state.npc):
        return state
    consumed = state.consumed_effects
    match = find_contradiction(case, npc_id, knowledge_id, evidence_id)
    if match is None:
        key = f"mismatch:{npc_id}:{knowledge_id}:{evidence_id}"
        npc, consumed = _irrelevant(case, state.npc, consumed, key)
        return replace(state, npc=npc, consumed_effects=consumed)
    npc = replace(state.npc, irrelevant_streak=0)
    key = f"contradiction:{npc_id}:{match.id}"
    if key not in consumed:
        npc = replace(
            npc,
            pressure=_clamp(npc.pressure + match.pressure),
            trust=_clamp(npc.trust + match.trust),
        )
        consumed = consumed | {key}
    return replace(state, npc=npc, consumed_effects=consumed)


# Outcome codes of an interrogation move, decided once for the CLI and the API.


def _setback(case: Case, after: GameState) -> str:
    return "EVASION_STARTED" if evading(case, after.npc) else "IRRELEVANT_MOVE"


def topic_outcome(case: Case, before: GameState, knowledge_id: str) -> str:
    if evading(case, before.npc):
        return "NPC_EVADING"
    if knowledge_id in before.disclosed_knowledge:
        return "TOPIC_ALREADY_ASKED"
    return "TESTIMONY_RECORDED"


def present_outcome(
    case: Case, before: GameState, after: GameState, npc_id: str, evidence_id: str
) -> str:
    if evading(case, before.npc):
        return "NPC_EVADING"
    if evidence_id not in relevant_evidence(case, npc_id):
        return _setback(case, after)
    if after.npc.lie_stage != before.npc.lie_stage:
        return "ADMISSION_RECORDED" if after.npc.lie_stage == LieStage.ADMITTED else "LIE_BROKEN"
    if evidence_id in before.npc.presented:
        return "ALREADY_PRESENTED"
    return "EVIDENCE_RECORDED"


def contradiction_outcome(case: Case, before: GameState, after: GameState, matched: bool) -> str:
    if evading(case, before.npc):
        return "NPC_EVADING"
    if not matched:
        return _setback(case, after)
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
        if criterion.kind == "support":
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
    return replace(
        state,
        phase=Phase.REVIEW,
        active_npc_id=None,
        verdict=Verdict(
            category,
            score,
            tuple(results),
            accusation,
            state.evidence_ids,
            case.version,
            case.rules_version,
        ),
    )
