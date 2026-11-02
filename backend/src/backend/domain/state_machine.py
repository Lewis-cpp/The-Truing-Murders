from collections.abc import Mapping
from dataclasses import replace

from backend.domain.models import Case, GameError, GameState, LieStage, NPCState, Phase

INVESTIGATION = frozenset({Phase.INVESTIGATION, Phase.DEEP_INVESTIGATION})
ACTIVE = INVESTIGATION | {Phase.INTERROGATION}
ALLOWED = {
    "inspect": INVESTIGATION,
    "talk": ACTIVE,
    "ask": {Phase.INTERROGATION},
    "topic": {Phase.INTERROGATION},
    "present": {Phase.INTERROGATION},
    "contradict": {Phase.INTERROGATION},
    "back": {Phase.INTERROGATION, Phase.ACCUSATION},
    "accuse": ACTIVE,
    "draft": {Phase.ACCUSATION},
    "submit": {Phase.ACCUSATION},
    "finish": {Phase.REVIEW},
}


def guard(state: GameState, action: str) -> None:
    if state.phase not in ALLOWED.get(action, set()):
        raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")


def _calmed(state: GameState) -> Mapping[str, NPCState]:
    """Leaving or switching an interrogation ends any evasion for every character."""
    return {npc_id: replace(npc, irrelevant_streak=0) for npc_id, npc in state.npcs.items()}


def transition(state: GameState, action: str, npc_id: str | None = None) -> GameState:
    guard(state, action)
    if action == "talk":
        if npc_id == state.active_npc_id:
            return state
        return replace(state, phase=Phase.INTERROGATION, active_npc_id=npc_id, npcs=_calmed(state))
    if action == "back":
        target = Phase.DEEP_INVESTIGATION if state.deep_unlocked else Phase.INVESTIGATION
        return replace(state, phase=target, active_npc_id=None, npcs=_calmed(state))
    if action == "accuse":
        return replace(state, phase=Phase.ACCUSATION, active_npc_id=None, npcs=_calmed(state))
    if action == "finish":
        return replace(state, phase=Phase.FINISHED)
    raise GameError("该操作不能直接转换阶段。")


def emotion(npc: NPCState) -> str:
    if npc.pressure >= 70:
        return "PRESSURED"
    if npc.pressure >= 40:
        return "NERVOUS"
    if npc.trust < 30:
        return "DEFENSIVE"
    return "CALM"


def evading(case: Case, npc: NPCState) -> bool:
    """After too many irrelevant moves the NPC only evades until the player leaves."""
    return npc.irrelevant_streak >= case.interrogation.evade_after


def admission_progress(case: Case, state: GameState, npc_id: str) -> str:
    npc = state.npcs[npc_id]
    character = next(c for c in case.characters if c.id == npc_id)
    core = character.core_lie_ids
    if core and all(npc.lies.get(lie_id) == LieStage.ADMITTED for lie_id in core):
        return "CONFESSION"
    if any(stage == LieStage.ADMITTED for stage in npc.lies.values()):
        return "PARTIAL_CONFESSION"
    return "NONE"


def display_state(case: Case, state: GameState, npc_id: str) -> str:
    npc = state.npcs[npc_id]
    if state.active_npc_id == npc_id and evading(case, npc):
        return "EVADING"
    progress = admission_progress(case, state, npc_id)
    if progress in {"CONFESSION", "PARTIAL_CONFESSION"}:
        return progress
    return emotion(npc)
