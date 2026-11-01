"""v0.3 acceptance: rules of the full case, against hand-written expectations.

Expectations live in tests/data/expected and were computed by hand from the case file.
Never regenerate them from the functions under test.
"""

import json
import random
from dataclasses import replace
from itertools import permutations
from pathlib import Path

import pytest

from backend.application.case import load_case
from backend.domain import rules
from backend.domain.evidence import current_statement
from backend.domain.models import (
    Accusation,
    AccusationDraft,
    GameError,
    LieStage,
    NPCState,
    Phase,
    StepEvidenceLink,
)
from backend.domain.state_machine import admission_progress, display_state, emotion, transition

pytestmark = [pytest.mark.unit, pytest.mark.rule]

EXPECTED = Path(__file__).resolve().parents[1] / "data/expected"
PATHS = json.loads((EXPECTED / "full_case_paths.json").read_text(encoding="utf-8"))
VERDICTS = json.loads((EXPECTED / "full_case_verdicts.json").read_text(encoding="utf-8"))
CATEGORY = {"CORRECT": "正确", "PARTIALLY_CORRECT": "部分正确", "INCORRECT": "错误"}
ALL_ACTIONS = [f"A{i:02d}" for i in range(1, 13)]
NPCS = ("NPC01", "NPC02", "NPC03", "NPC04")


@pytest.fixture(scope="module")
def case():
    return load_case()


def play(case, state, steps):
    for step in steps:
        state = apply_step(case, state, step)
    return state


def apply_step(case, state, step):
    """Runs one path step and checks its hand-written expectation."""
    op, expect, npc = step["op"], step["expect"], state.active_npc_id
    if "error" in expect:
        with pytest.raises(GameError) as caught:
            run(case, state, op, step, npc)
        assert caught.value.code == expect["error"], step
        return state
    after, outcome = run(case, state, op, step, npc)
    if "outcome" in expect:
        assert outcome == expect["outcome"], step
    if "phase" in expect:
        assert after.phase == Phase(expect["phase"]), step
    if "active_npc_id" in expect:
        assert after.active_npc_id == expect["active_npc_id"], step
    if "open_scenes" in expect:
        assert list(rules.open_scenes(case, after)) == expect["open_scenes"], step
    if "evidence" in expect:
        assert after.evidence_ids == frozenset(expect["evidence"]), step
    if "disclosed_add" in expect:
        added = after.disclosed_knowledge - state.disclosed_knowledge
        assert added == frozenset(expect["disclosed_add"]), step
    if "npc" in expect:
        want = expect["npc"]
        got = after.npcs[want["id"]]
        for field in ("pressure", "trust"):
            if field in want:
                assert getattr(got, field) == want[field], (step, field)
        if "streak" in want:
            assert got.irrelevant_streak == want["streak"], step
        for lie_id, stage in want.get("lies", {}).items():
            assert got.lies[lie_id] == LieStage(stage), (step, lie_id)
    speaker = after.active_npc_id or step.get("npc")
    if "display_state" in expect:
        assert display_state(case, after, speaker) == expect["display_state"], step
    if "statement" in expect:
        assert current_statement(case, after, speaker) == expect["statement"], step
    return after


def run(case, state, op, step, npc):
    if op == "inspect":
        return rules.investigate(case, state, step["action"]), None
    if op == "talk":
        return transition(state, "talk", step["npc"]), None
    if op == "back":
        return transition(state, "back"), None
    if op == "present":
        after = rules.present(case, state, npc, step["evidence"])
        return after, rules.present_outcome(case, state, after, npc, step["evidence"])
    if op == "topic":
        after = rules.ask_topic(case, state, npc, step["topic"])
        topic = next(t for t in case.interrogation.topics if t.id == step["topic"])
        return after, rules.topic_outcome(case, state, topic.knowledge_id)
    if op == "contradict":
        knowledge, evidence = step["knowledge"], step["evidence"]
        after = rules.contradict(case, state, npc, knowledge, evidence)
        matched = any(
            (c.npc_id, c.knowledge_id, c.evidence_id) == (npc, knowledge, evidence)
            for c in case.interrogation.contradictions
        )
        return after, rules.contradiction_outcome(case, state, after, matched)
    raise AssertionError(f"unknown op {op}")


@pytest.fixture
def investigated(case):
    return play(case, rules.new_game(case), PATHS["no_confession"])


def interrogate(state, npc_id="NPC01"):
    return transition(state, "talk", npc_id)


# New game and scenes


def test_new_game_starts_with_every_npc_at_configured_values(case):
    state = rules.new_game(case)
    assert state.phase == Phase.INVESTIGATION
    assert state.version == 1
    assert state.evidence_ids == frozenset()
    assert not state.deep_unlocked
    assert rules.open_scenes(case, state) == ("S01",)
    assert set(state.npcs) == set(NPCS)
    initial = {"NPC01": (20, 40), "NPC02": (10, 35), "NPC03": (15, 40), "NPC04": (10, 50)}
    for npc_id, (pressure, trust) in initial.items():
        npc = state.npcs[npc_id]
        assert (npc.pressure, npc.trust, npc.irrelevant_streak) == (pressure, trust, 0)
        assert set(npc.lies.values()) <= {LieStage.UNBROKEN}
    assert set(state.npcs["NPC01"].lies) == {"L01", "L02"}
    assert set(state.npcs["NPC04"].lies) == set()
    assert state.disclosed_knowledge == frozenset()


@pytest.mark.parametrize("name", list(k for k in PATHS if not k.startswith("_")))
def test_hand_written_paths(case, investigated, name):
    start = rules.new_game(case) if name == "no_confession" else investigated
    play(case, start, PATHS[name])


@pytest.mark.parametrize(
    ("before", "action", "code"),
    [
        ([], "A05", "SCENE_NOT_FOUND"),
        (["A01"], "A07", "SCENE_NOT_FOUND"),
        ([], "A03", "ACTION_UNAVAILABLE"),
        (["A01"], "A03", "ACTION_UNAVAILABLE"),
        (["A01", "A05"], "A11", "ACTION_UNAVAILABLE"),
        ([], "A99", "INVALID_ACTION_REFERENCE"),
    ],
)
def test_locked_or_unready_actions_are_rejected_without_side_effects(case, before, action, code):
    state = play(
        case, rules.new_game(case), [{"op": "inspect", "action": a, "expect": {}} for a in before]
    )
    with pytest.raises(GameError) as caught:
        rules.investigate(case, state, action)
    assert caught.value.code == code


def test_scene_any_of_entries(case):
    state = rules.investigate(case, rules.new_game(case), "A02")
    assert rules.open_scenes(case, state) == ("S01", "S02")
    state = rules.investigate(case, state, "A05")
    assert rules.open_scenes(case, state) == ("S01", "S02", "S04")
    state = rules.investigate(case, state, "A10")
    with pytest.raises(GameError) as caught:
        rules.investigate(case, state, "A11")
    assert caught.value.code == "ACTION_UNAVAILABLE"
    state = rules.investigate(case, state, "A12")
    assert "E12" in state.evidence_ids


def test_repeated_investigation_is_a_noop(case):
    state = rules.investigate(case, rules.new_game(case), "A01")
    assert rules.investigate(case, state, "A01") == state


@pytest.mark.parametrize("seed", range(40))
def test_any_legal_investigation_order_collects_all_twelve_without_confession(case, seed):
    chooser = random.Random(seed)
    state = rules.new_game(case)
    remaining = set(ALL_ACTIONS)
    while remaining:
        ready = []
        for action in sorted(remaining):
            try:
                ready.append((action, rules.investigate(case, state, action)))
            except GameError:
                continue
        assert ready, f"stuck with {sorted(remaining)}"
        action, state = chooser.choice(ready)
        remaining.discard(action)
    assert state.evidence_ids == frozenset(f"E{i:02d}" for i in range(1, 13))
    assert state.phase == Phase.DEEP_INVESTIGATION
    assert all(stage == LieStage.UNBROKEN for n in state.npcs.values() for stage in n.lies.values())


def test_deep_unlock_during_interrogation_keeps_the_phase(case):
    state = rules.investigate(case, rules.new_game(case), "A01")
    state = interrogate(state)
    state = rules.present(case, state, "NPC01", "E01")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.BROKEN
    assert state.deep_unlocked
    assert state.phase == Phase.INTERROGATION
    assert transition(state, "back").phase == Phase.DEEP_INVESTIGATION


def test_without_deep_unlock_back_returns_to_investigation(case):
    state = interrogate(rules.investigate(case, rules.new_game(case), "A01"))
    assert transition(state, "back").phase == Phase.INVESTIGATION


# Presentations


def test_relevance_follows_the_current_layer(case, investigated):
    assert rules.relevant_evidence(case, investigated, "NPC01") == {"E01", "E03"}
    assert rules.relevant_evidence(case, investigated, "NPC02") == {"E05", "E06"}
    assert rules.relevant_evidence(case, investigated, "NPC03") == {"E10", "E11"}
    assert rules.relevant_evidence(case, investigated, "NPC04") == frozenset()
    state = interrogate(investigated)
    for evidence in ("E01", "E03"):
        state = rules.present(case, state, "NPC01", evidence)
    assert rules.relevant_evidence(case, state, "NPC01") == {"E01", "E02", "E03", "E08"}


@pytest.mark.parametrize("order", list(permutations(["E01", "E02", "E03", "E08"])))
def test_every_order_of_shen_yans_evidence_reaches_both_layers_without_double_gains(
    case, investigated, order
):
    state = interrogate(investigated)
    for _ in range(2):  # the second pass lets L02 re-check what was shown too early
        for evidence in order:
            state = rules.present(case, state, "NPC01", evidence)
            if state.npcs["NPC01"].irrelevant_streak >= case.interrogation.evade_after:
                state = interrogate(transition(state, "back"))
    npc = state.npcs["NPC01"]
    assert npc.lies == {"L01": LieStage.ADMITTED, "L02": LieStage.ADMITTED}
    assert npc.pressure == 90
    assert npc.trust in {25, 30, 35}
    assert state.disclosed_knowledge >= {"K02", "K04"}
    assert admission_progress(case, state, "NPC01") == "CONFESSION"


@pytest.mark.parametrize(("pressure", "trust"), [(0, 0), (64, 100), (100, 100)])
def test_no_counterevidence_means_no_break_whatever_the_numbers(
    case, investigated, pressure, trust
):
    state = interrogate(investigated)
    npc = replace(state.npcs["NPC01"], pressure=pressure, trust=trust)
    state = replace(state, npcs={**state.npcs, "NPC01": npc})
    state = rules.present(case, state, "NPC01", "E03")
    assert state.npcs["NPC01"].lies["L01"] == LieStage.UNBROKEN
    assert "K02" not in state.disclosed_knowledge


def test_broken_but_not_admitted_when_pressure_is_short(case, investigated):
    state = interrogate(investigated, "NPC02")
    state = rules.present(case, state, "NPC02", "E05")
    assert state.npcs["NPC02"].lies["L03"] == LieStage.BROKEN
    npc = replace(state.npcs["NPC02"], pressure=24)  # +20 from E06 gives 44 < 45
    state = rules.present(case, replace(state, npcs={**state.npcs, "NPC02": npc}), "NPC02", "E06")
    assert state.npcs["NPC02"].pressure == 44
    assert state.npcs["NPC02"].lies["L03"] == LieStage.BROKEN
    assert "K05" not in state.disclosed_knowledge


def test_repeated_presentation_never_stacks_effects(case, investigated):
    state = interrogate(investigated)
    for _ in range(3):
        state = rules.present(case, state, "NPC01", "E01")
    assert (state.npcs["NPC01"].pressure, state.npcs["NPC01"].trust) == (45, 35)
    assert len([k for k in state.consumed_effects if k.startswith("present:NPC01:")]) == 1


def test_clamped_effect_is_still_consumed(case, investigated):
    state = interrogate(investigated)
    npc = replace(state.npcs["NPC01"], pressure=95)
    state = rules.present(case, replace(state, npcs={**state.npcs, "NPC01": npc}), "NPC01", "E01")
    assert state.npcs["NPC01"].pressure == 100
    lowered = replace(state.npcs["NPC01"], pressure=50)
    state = rules.present(
        case, replace(state, npcs={**state.npcs, "NPC01": lowered}), "NPC01", "E01"
    )
    assert state.npcs["NPC01"].pressure == 50


def test_admissions_never_revert_and_stay_with_their_speaker(case, investigated):
    state = play(case, investigated, PATHS["full_confession"][:5])
    admitted = state.npcs["NPC01"].lies
    others = {n: state.npcs[n] for n in ("NPC02", "NPC03", "NPC04")}
    assert others == {n: investigated.npcs[n] for n in others}
    state = interrogate(state)
    state = rules.ask_topic(case, state, "NPC01", "Q01")
    state = rules.contradict(case, state, "NPC01", "K03", "E12")
    state = rules.present(case, state, "NPC01", "E12")
    state = interrogate(transition(state, "back"), "NPC04")
    assert state.npcs["NPC01"].lies == admitted
    assert {"K02", "K04"} <= state.disclosed_knowledge


def test_presentation_guards(case, investigated):
    with pytest.raises(GameError) as caught:
        rules.present(case, investigated, "NPC01", "E01")
    assert caught.value.code == "ACTION_NOT_ALLOWED"
    state = interrogate(investigated)
    with pytest.raises(GameError) as caught:
        rules.present(case, state, "NPC02", "E05")
    assert caught.value.code == "ACTIVE_NPC_MISMATCH"
    fresh = interrogate(rules.investigate(case, rules.new_game(case), "A01"))
    with pytest.raises(GameError) as caught:
        rules.present(case, fresh, "NPC01", "E03")
    assert caught.value.code == "EVIDENCE_NOT_OWNED"


def test_evasion_freezes_topics_and_contradictions_and_ends_on_switch(case, investigated):
    state = interrogate(investigated)
    for evidence in ("E04", "E05"):
        state = rules.present(case, state, "NPC01", evidence)
    assert state.npcs["NPC01"].irrelevant_streak == 2
    assert rules.ask_topic(case, state, "NPC01", "Q01") == state
    state = interrogate(state, "NPC02")
    assert state.npcs["NPC01"].irrelevant_streak == 0
    state = interrogate(state, "NPC01")
    assert current_statement(case, state, "NPC01") == "停电时我一直在休息区，没有去过档案室。"


def test_switching_to_the_same_npc_is_a_noop(case, investigated):
    state = interrogate(investigated)
    assert transition(state, "talk", "NPC01") == state


@pytest.mark.parametrize(
    ("pressure", "trust", "expected"),
    [
        (70, 0, "PRESSURED"),
        (69, 100, "NERVOUS"),
        (40, 0, "NERVOUS"),
        (39, 29, "DEFENSIVE"),
        (39, 30, "CALM"),
    ],
)
def test_emotion_boundaries(pressure, trust, expected):
    assert emotion(NPCState(pressure=pressure, trust=trust, lies={})) == expected


# Judgement and draft


def accuse(case, actions):
    state = play(
        case, rules.new_game(case), [{"op": "inspect", "action": a, "expect": {}} for a in actions]
    )
    return transition(state, "accuse")


def accusation(data, explanation=""):
    return Accusation(
        culprit=data["culprit"],
        weapon=data["weapon"],
        motive=data["motive"],
        steps=tuple(data["steps"]),
        cited_evidence_ids=tuple(data["cited_evidence_ids"]),
        evidence_links=tuple(StepEvidenceLink(**link) for link in data["evidence_links"]),
        explanation=explanation,
    )


@pytest.mark.parametrize("example", VERDICTS, ids=lambda e: e["name"])
def test_hand_written_verdicts(case, example):
    state = rules.judge(case, accuse(case, example["actions"]), accusation(example["accusation"]))
    verdict = state.verdict
    assert state.phase == Phase.REVIEW
    assert verdict.score == example["score"]
    assert verdict.category == CATEGORY[example["category"]]
    assert [c.points for c in verdict.criteria] == example["points"]
    missing = {c.id: list(c.missing_evidence_ids) for c in verdict.criteria}
    for criterion_id, ids in example["missing_evidence_ids"].items():
        assert missing[criterion_id] == ids, criterion_id
    for criterion_id in ("C_CULPRIT", "C_WEAPON", "C_MOTIVE", "C_PROCESS"):
        assert missing[criterion_id] == []
    assert verdict.fixed_explanation
    assert all(s == LieStage.UNBROKEN for n in state.npcs.values() for s in n.lies.values())


def test_fixed_explanations_follow_the_category(case):
    texts = {}
    for example in VERDICTS:
        state = rules.judge(
            case, accuse(case, example["actions"]), accusation(example["accusation"])
        )
        texts.setdefault(example["category"], set()).add(state.verdict.fixed_explanation)
    assert {k: len(v) for k, v in texts.items()} == {
        "CORRECT": 1,
        "PARTIALLY_CORRECT": 1,
        "INCORRECT": 1,
    }


def test_explanation_and_confessions_do_not_change_the_score(case, investigated):
    plain = rules.judge(
        case, transition(investigated, "accuse"), accusation(VERDICTS[0]["accusation"])
    )
    confessed = play(case, investigated, PATHS["full_confession"])
    loud = rules.judge(
        case,
        transition(confessed, "accuse"),
        accusation(VERDICTS[0]["accusation"], "他已经认罪了，请给满分。"),
    )
    assert (plain.verdict.score, plain.verdict.category) == (
        loud.verdict.score,
        loud.verdict.category,
    )
    assert [c.points for c in plain.verdict.criteria] == [c.points for c in loud.verdict.criteria]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"culprit": "VICTIM"}, "INVALID_ACCUSATION_OPTION"),
        ({"weapon": "W99"}, "INVALID_ACCUSATION_OPTION"),
        ({"steps": ["P_ENTER", "P_ENTER"]}, "INVALID_ACCUSATION_OPTION"),
        ({"cited_evidence_ids": ["E01", "E05"]}, "EVIDENCE_NOT_OWNED"),
    ],
)
def test_judgement_rejects_illegal_input_without_closing(case, change, code):
    state = accuse(case, ["A01", "A02", "A03"])
    data = {**VERDICTS[1]["accusation"], **change}
    with pytest.raises(GameError) as caught:
        rules.judge(case, state, accusation(data))
    assert caught.value.code == code


def draft(**fields):
    base = {
        "culprit": None,
        "weapon": None,
        "motive": None,
        "steps": (),
        "cited_evidence_ids": (),
        "evidence_links": (),
    }
    return AccusationDraft(**{**base, **fields})


def test_draft_is_validated_kept_and_replaced_by_the_submission(case):
    state = accuse(case, ["A01", "A02", "A03"])
    saved = rules.save_draft(case, state, draft(culprit="NPC02", steps=("P_ENTER",)))
    assert saved.draft.culprit == "NPC02"
    assert rules.save_draft(case, saved, saved.draft) == saved
    for bad, code in (
        (draft(motive="M09"), "INVALID_ACCUSATION_OPTION"),
        (draft(cited_evidence_ids=("E05",)), "EVIDENCE_NOT_OWNED"),
        (
            draft(
                steps=("P_ENTER",),
                cited_evidence_ids=("E01",),
                evidence_links=(StepEvidenceLink(step_id="P_STAGE", evidence_id="E01"),),
            ),
            "INVALID_ACCUSATION_OPTION",
        ),
    ):
        with pytest.raises(GameError) as caught:
            rules.save_draft(case, saved, bad)
        assert caught.value.code == code
    back = transition(saved, "back")
    assert back.phase == Phase.DEEP_INVESTIGATION and back.draft == saved.draft
    with pytest.raises(GameError) as caught:
        rules.save_draft(case, back, draft())
    assert caught.value.code == "ACTION_NOT_ALLOWED"
    closed = rules.judge(
        case,
        transition(back, "accuse"),
        accusation(
            VERDICTS[0]["accusation"]
            | {
                "cited_evidence_ids": ["E01", "E02", "E03"],
                "evidence_links": [],
            }
        ),
    )
    assert closed.draft.culprit == "NPC01"
    assert closed.draft.cited_evidence_ids == ("E01", "E02", "E03")
