"""v0.3 acceptance: six persisted phases × every domain action.

The table below is written independently of state_machine.ALLOWED; do not import it.
"""

from dataclasses import replace

import pytest

from backend.application.case import load_case
from backend.domain import rules
from backend.domain.models import Accusation, GameError, Phase, StepEvidenceLink
from backend.domain.state_machine import guard, transition

pytestmark = [pytest.mark.unit, pytest.mark.state_machine]

INV, DEEP, TALK, ACC, REV, FIN = "I", "D", "T", "A", "R", "F"
ALLOWED = {
    "inspect": {INV, DEEP},
    "talk": {INV, DEEP, TALK},
    "ask": {TALK},
    "topic": {TALK},
    "present": {TALK},
    "contradict": {TALK},
    "back": {TALK, ACC},
    "accuse": {INV, DEEP, TALK},
    "draft": {ACC},
    "submit": {ACC},
    "finish": {REV},
}


@pytest.fixture(scope="module")
def states():
    case = load_case()
    start = rules.new_game(case)
    investigated = rules.investigate(case, start, "A01")
    deep = replace(investigated, phase=Phase.DEEP_INVESTIGATION, deep_unlocked=True)
    talking = transition(investigated, "talk", "NPC01")
    accusing = transition(investigated, "accuse")
    closed = rules.judge(
        case,
        accusing,
        Accusation(
            culprit="NPC01",
            weapon="W01",
            motive="M01",
            steps=("P_ENTER",),
            cited_evidence_ids=("E01",),
            evidence_links=(StepEvidenceLink(step_id="P_ENTER", evidence_id="E01"),),
        ),
    )
    finished = transition(closed, "finish")
    return {INV: investigated, DEEP: deep, TALK: talking, ACC: accusing, REV: closed, FIN: finished}


@pytest.mark.parametrize("phase", [INV, DEEP, TALK, ACC, REV, FIN])
@pytest.mark.parametrize("action", sorted(ALLOWED))
def test_guard_matches_the_independent_table(states, phase, action):
    state = states[phase]
    if phase in ALLOWED[action]:
        guard(state, action)
    else:
        with pytest.raises(GameError) as caught:
            guard(state, action)
        assert caught.value.code == "ACTION_NOT_ALLOWED"


def test_phases_of_the_fixture_states(states):
    expected = {
        INV: Phase.INVESTIGATION,
        DEEP: Phase.DEEP_INVESTIGATION,
        TALK: Phase.INTERROGATION,
        ACC: Phase.ACCUSATION,
        REV: Phase.REVIEW,
        FIN: Phase.FINISHED,
    }
    assert {k: s.phase for k, s in states.items()} == expected


def test_transitions_clear_or_set_the_active_npc(states):
    talking = states[TALK]
    assert talking.active_npc_id == "NPC01"
    switched = transition(talking, "talk", "NPC03")
    assert (switched.phase, switched.active_npc_id) == (Phase.INTERROGATION, "NPC03")
    assert switched.npcs == talking.npcs
    for action in ("back", "accuse"):
        assert transition(talking, action).active_npc_id is None
    assert transition(states[ACC], "back").phase == Phase.INVESTIGATION
    deep_accusing = transition(states[DEEP], "accuse")
    assert transition(deep_accusing, "back").phase == Phase.DEEP_INVESTIGATION
    assert transition(states[REV], "finish").phase == Phase.FINISHED


def test_closed_games_stay_closed(states):
    case = load_case()
    for phase in (REV, FIN):
        state = states[phase]
        with pytest.raises(GameError):
            rules.investigate(case, state, "A02")
        with pytest.raises(GameError):
            transition(state, "talk", "NPC01")
        with pytest.raises(GameError):
            transition(state, "accuse")
        assert state.verdict is not None
