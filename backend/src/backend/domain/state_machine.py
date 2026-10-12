from dataclasses import replace

from backend.domain.models import GameError, GameState, NPCState, Phase

INVESTIGATION = frozenset({Phase.INVESTIGATION, Phase.DEEP_INVESTIGATION})
ACTIVE = INVESTIGATION | {Phase.INTERROGATION}
ALLOWED = {
    "inspect": INVESTIGATION,
    "talk": ACTIVE,
    "ask": {Phase.INTERROGATION},
    "present": {Phase.INTERROGATION},
    "back": {Phase.INTERROGATION, Phase.ACCUSATION},
    "accuse": ACTIVE,
    "submit": {Phase.ACCUSATION},
    "finish": {Phase.REVIEW},
}


def guard(state: GameState, action: str) -> None:
    if state.phase not in ALLOWED.get(action, set()):
        raise GameError(f"当前阶段 {state.phase.value} 不能执行此操作。")


def transition(state: GameState, action: str, npc_id: str | None = None) -> GameState:
    guard(state, action)
    if action == "talk":
        return replace(state, phase=Phase.INTERROGATION, active_npc_id=npc_id)
    if action == "back":
        target = Phase.DEEP_INVESTIGATION if state.deep_unlocked else Phase.INVESTIGATION
        return replace(state, phase=target, active_npc_id=None)
    if action == "accuse":
        return replace(state, phase=Phase.ACCUSATION, active_npc_id=None)
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
