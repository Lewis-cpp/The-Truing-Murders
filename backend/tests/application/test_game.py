import json
from dataclasses import FrozenInstanceError

import pytest

from backend.application.case import load_case
from backend.application.game import Game
from backend.domain.evidence import npc_view
from backend.domain.models import Accusation, GameError, Phase

pytestmark = pytest.mark.unit


@pytest.fixture
def game():
    return Game(load_case())


def accusation(**changes):
    fields = dict(
        culprit="NPC01",
        weapon="W01",
        motive="M01",
        steps=("P_ENTER", "P_ATTACK", "P_STAGE"),
        cited_evidence_ids=(),
        evidence_links=(),
    )
    return Accusation(**(fields | changes))


@pytest.mark.parametrize(
    "action",
    [
        lambda g: g.present("NPC01", "E01"),
        lambda g: g.ask("问题"),
        lambda g: g.inspect("UNKNOWN"),
        lambda g: g.talk("NPC02"),
        lambda g: g.submit(accusation()),
        lambda g: g.review(),
        lambda g: g.back(),
    ],
)
def test_rejected_initial_actions_are_atomic(game, action):
    before = game.state
    with pytest.raises(GameError):
        action(game)
    assert game.state == before


def test_illegal_interrogation_targets_and_unheld_evidence_are_atomic(game):
    game.inspect("A01")
    game.talk("NPC01")
    before = game.state
    for action in (
        lambda: game.inspect("A02"),
        lambda: game.present("NPC02", "E01"),
        lambda: game.present("NPC01", "E03"),
    ):
        with pytest.raises(GameError):
            action()
        assert game.state == before


def test_accusation_can_be_cancelled_without_confession_or_evidence(game):
    game.accuse()
    before = game.state
    for action in (lambda: game.talk("NPC01"), lambda: game.inspect("A01")):
        with pytest.raises(GameError):
            action()
        assert game.state == before
    game.back()
    assert game.state.phase == Phase.INVESTIGATION
    assert not game.state.evidence_ids


@pytest.mark.parametrize(
    "changes",
    [
        {"culprit": "UNKNOWN"},
        {"weapon": "UNKNOWN"},
        {"motive": "UNKNOWN"},
        {"steps": ()},
        {"steps": ("P_ENTER", "P_ENTER")},
        {"cited_evidence_ids": ("E03",)},
        {"cited_evidence_ids": ("E01", "E01")},
    ],
)
def test_invalid_submission_does_not_close_or_change_state(game, changes):
    game.inspect("A01")
    game.accuse()
    before = game.state
    with pytest.raises(GameError):
        game.submit(accusation(**changes))
    assert game.state == before
    assert game.state.verdict is None


@pytest.mark.parametrize("step,evidence", [("P_POISON", "E01"), ("P_ENTER", "E02")])
def test_links_must_belong_to_submitted_steps_and_citations(game, step, evidence):
    from backend.domain.models import StepEvidenceLink

    game.inspect("A01")
    game.inspect("A02")
    game.accuse()
    before = game.state
    with pytest.raises(GameError):
        game.submit(
            accusation(
                cited_evidence_ids=("E01",),
                evidence_links=(StepEvidenceLink(step_id=step, evidence_id=evidence),),
            )
        )
    assert game.state == before


def test_knowledge_requires_disclosure_and_only_presented_material_reaches_npc(game):
    case = load_case()
    initial = json.dumps(game.view(), ensure_ascii=False)
    assert "truth" not in game.view()
    assert "admission_pressure_min" not in initial
    assert case.lie.statements.admitted not in initial
    assert case.evidence[0].content not in initial
    for action in ("A01", "A02", "A03"):
        game.inspect(action)
    game.talk("NPC01")
    view = npc_view(case, game.state, "NPC01")
    assert view["presented"] == []
    assert case.knowledge[1].content not in view["knowledge"]
    game.present("NPC01", "E01")
    assert [e["id"] for e in npc_view(case, game.state, "NPC01")["presented"]] == ["E01"]
    assert len(game.view()["knowledge"]) == 1
    game.present("NPC01", "E03")
    assert game.view()["knowledge"][-1]["credibility"] == "UNVERIFIED"
    assert case.knowledge[1].content in npc_view(case, game.state, "NPC01")["knowledge"]
    with pytest.raises(GameError):
        npc_view(case, game.state, "NPC02")


def test_closure_freezes_input_and_review_does_not_grant_missing_evidence(game):
    game.accuse()
    game.submit(accusation())
    frozen = game.state
    assert game.state.verdict.score == 75
    assert "truth" in game.view()
    for action in (
        lambda: game.inspect("A01"),
        lambda: game.talk("NPC01"),
        lambda: game.back(),
        lambda: game.accuse(),
        lambda: game.submit(accusation()),
        lambda: game.present("NPC01", "E01"),
    ):
        with pytest.raises(GameError):
            action()
        assert game.state == frozen
    first = game.review()
    assert game.review() == first
    assert game.state == frozen
    game.finish()
    assert game.review() == first
    assert not game.state.evidence_ids
    assert game.state.verdict is frozen.verdict
    with pytest.raises(FrozenInstanceError):
        game.state.npc.pressure = 100


def test_separate_games_and_read_only_actions_do_not_share_or_change_state(game):
    other = Game(load_case())
    game.inspect("A01")
    assert not other.state.evidence_ids
    before = game.state
    game.view()
    game.view()
    assert game.state == before


def test_alternate_investigation_source_does_not_duplicate_evidence():
    case = load_case()
    alternate = case.scene.actions[0].model_copy(update={"id": "A04"})
    case = case.model_copy(
        update={
            "scene": case.scene.model_copy(update={"actions": (*case.scene.actions, alternate)})
        }
    )
    game = Game(case)
    game.inspect("A01")
    assert "没有重复发放" in game.inspect("A04")
    assert game.state.evidence_ids == {"E01"}
    assert game.state.completed_actions == {"A01", "A04"}
    before = game.state
    game.inspect("A04")
    assert game.state == before
