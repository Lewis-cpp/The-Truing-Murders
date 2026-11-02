"""Ported v0.2 rule checks that the v0.3 acceptance suite does not cover.

The slice-specific expectations (week_one_verdicts.json, single-NPC state) were retired once
the full-case acceptance tests covered them.
"""

from dataclasses import replace

import pytest

from backend.application.case import load_case
from backend.domain import rules
from backend.domain.models import LieStage
from backend.domain.state_machine import transition

pytestmark = [pytest.mark.unit, pytest.mark.rule]


def interrogating(case, actions=("A01", "A02", "A03")):
    state = rules.new_game(case)
    for action in actions:
        state = rules.investigate(case, state, action)
    return transition(state, "talk", "NPC01")


def test_unverified_material_cannot_break_or_increase_pressure():
    case = load_case()
    evidence = tuple(
        e.model_copy(update={"credibility": "UNVERIFIED"}) if e.id == "E01" else e
        for e in case.evidence
    )
    case = case.model_copy(update={"evidence": evidence})
    state = interrogating(case, ("A01",))
    after = rules.present(case, state, "NPC01", "E01")
    npc = after.npcs["NPC01"]
    assert npc.pressure == 20
    assert npc.lies["L01"] == LieStage.UNBROKEN
    assert "present:NPC01:E01" not in after.consumed_effects


def test_trust_path_still_requires_evidence():
    case = load_case()
    lie = case.lies[0].model_copy(
        update={"admission_pressure_min": None, "admission_trust_min": 30}
    )
    case = case.model_copy(update={"lies": (lie, *case.lies[1:])})
    state = interrogating(case)
    state = rules.present(case, state, "NPC01", "E01")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.BROKEN
    state = rules.present(case, state, "NPC01", "E03")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.ADMITTED
    npc = replace(state.npcs["NPC01"], pressure=0, trust=0)
    state = replace(state, npcs={**state.npcs, "NPC01": npc})
    after = rules.present(case, state, "NPC01", "E01")
    assert after.npcs["NPC01"].lies["L01"] == LieStage.ADMITTED


def test_costs_are_clamped_and_consumed_even_at_zero_trust():
    case = load_case()
    state = interrogating(case, ("A02", "A04"))
    after = rules.present(case, state, "NPC01", "E02")
    assert after.npcs["NPC01"].trust == 35
    assert after.consumed_effects == {"irrelevant:NPC01:E02"}
    npc = replace(after.npcs["NPC01"], trust=2)
    state = replace(after, npcs={**after.npcs, "NPC01": npc})
    after = rules.present(case, state, "NPC01", "E04")
    assert after.npcs["NPC01"].trust == 0
    assert "irrelevant:NPC01:E04" in after.consumed_effects


def test_maximum_psychology_never_replaces_counterevidence():
    case = load_case()
    state = rules.new_game(case)
    for action in ("A01", "A02", "A03"):
        state = rules.investigate(case, state, action)
    state = transition(state, "talk", "NPC01")
    npc = replace(state.npcs["NPC01"], pressure=100, trust=100)
    state = replace(state, npcs={**state.npcs, "NPC01": npc})
    after = rules.present(case, state, "NPC01", "E03")
    assert after.npcs["NPC01"].lies["L01"] == LieStage.UNBROKEN
    assert "K02" not in after.disclosed_knowledge


def test_admissions_and_evidence_survive_across_interrogations():
    case = load_case()
    state = interrogating(case)
    state = rules.present(case, state, "NPC01", "E01")
    state = rules.present(case, state, "NPC01", "E03")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.ADMITTED
    state = transition(state, "back")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.ADMITTED
    assert "K02" in state.disclosed_knowledge
    state = transition(state, "talk", "NPC01")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.ADMITTED
    assert set(state.npcs["NPC01"].presented) == {"E01", "E03"}
