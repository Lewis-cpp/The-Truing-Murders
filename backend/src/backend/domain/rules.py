from dataclasses import replace

from backend.domain.evidence import require_held, validate_accusation
from backend.domain.models import (
    Accusation,
    Case,
    CriterionResult,
    GameError,
    GameState,
    LieStage,
    Phase,
    Verdict,
)
from backend.domain.state_machine import guard

# Semantics of these functions; stored with each event and verdict to detect incompatible saves.
RULE_EXECUTION_VERSION = "w1-slice-1"


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
    if npc_id != case.npc.id or state.active_npc_id != npc_id:
        raise GameError("只能向当前审讯的角色出示证据。", "ACTIVE_NPC_MISMATCH")
    require_held(state, evidence_id)
    evidence = next(e for e in case.evidence if e.id == evidence_id)
    npc = replace(state.npc, presented=state.npc.presented | {evidence_id})
    consumed = state.consumed_effects
    key = f"present:{npc_id}:{evidence_id}"
    if evidence.credibility == "VERIFIED" and key not in consumed:
        effects = [e for e in case.lie.effects if e.evidence_id == evidence_id]
        if effects:
            npc = replace(
                npc,
                pressure=max(0, min(100, npc.pressure + sum(e.pressure for e in effects))),
                trust=max(0, min(100, npc.trust + sum(e.trust for e in effects))),
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
